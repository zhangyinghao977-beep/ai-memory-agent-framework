"""Portable experiment plumbing. Importing this module does not run an experiment.

Runtime controls are cooperative settings, not CPU/GPU utilization guarantees.
All configured input/output paths stay inside this independent release copy.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import warnings
from pathlib import Path, PureWindowsPath

RELEASE_ROOT = Path(__file__).resolve().parents[1]


def root_path(value: str | Path, *, must_exist: bool = False) -> Path:
    """Resolve a root-relative path, rejecting escapes and external absolute paths."""
    path = Path(value)
    path = (path if path.is_absolute() else RELEASE_ROOT / path).resolve()
    if not path.is_relative_to(RELEASE_ROOT):
        raise ValueError(f"Path must remain inside the release copy: {value}")
    if must_exist and not path.exists():
        raise FileNotFoundError(f"Required release input is missing: {path.relative_to(RELEASE_ROOT)}")
    return path


def load_plan(path: str | Path) -> dict:
    path = root_path(path, must_exist=True)
    plan = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(plan, dict):
        raise ValueError("The reproduction plan must be a JSON object")
    return plan


def source_hashes(files) -> dict:
    """Freeze source bytes with portable keys, including this helper itself."""
    paths = {root_path(p, must_exist=True) for p in files}
    paths.add(Path(__file__).resolve())
    return {p.relative_to(RELEASE_ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(paths)}


def freeze_plan_metadata(plan_path: str | Path) -> dict:
    path = root_path(plan_path, must_exist=True)
    return {"plan_path": path.relative_to(RELEASE_ROOT).as_posix(),
            "reproduction_config": True}


def load_run_plan(run: str | Path, plan_path: str | Path) -> dict:
    """Use this copy's plan only when its bytes match this run's frozen plan."""
    run = root_path(run, must_exist=True)
    path = root_path(plan_path, must_exist=True)
    frozen = json.loads((run / "FROZEN.json").read_text(encoding="utf-8"))
    relative = path.relative_to(RELEASE_ROOT).as_posix()
    if frozen.get("plan_path") != relative or not frozen.get("reproduction_config"):
        raise ValueError("This run does not have the new relative reproduction-plan metadata; historical FROZEN files are not supported")
    expected = frozen.get("sources", {}).get(relative)
    if expected != hashlib.sha256(path.read_bytes()).hexdigest():
        raise ValueError("PLAN.json differs from this run's frozen plan; refusing to relabel results with a different configuration")
    return load_plan(path)


def dependency_run(plan: dict, name: str, default=None) -> Path:
    """Require a completed local reproduction of the named predecessor stage.

    Validate metadata and JSON receipts only; do not load models or execute code.
    This establishes artifact identity/completeness, not scientific equivalence.
    """
    value = plan.get("dependency_runs", {}).get(name, default)
    if not value:
        raise ValueError(f"Set dependency_runs.{name} in PLAN.json to a completed local run")
    path = Path(value)
    if path.is_absolute() or PureWindowsPath(str(value)).is_absolute():
        raise ValueError(f"dependency_runs.{name} must be relative to the release root")
    try:
        result = root_path(path, must_exist=True)
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"Dependency {name} has not been generated: {value}. "
                                "Run the prerequisite experiment first or configure its local run directory.") from exc
    if not result.is_dir():
        raise ValueError(f"dependency_runs.{name} must name a run directory")

    def object_file(path: Path) -> dict:
        path = root_path(path, must_exist=True)
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, UnicodeError) as exc:
            raise ValueError(f"Dependency {name} has invalid JSON: {path.relative_to(RELEASE_ROOT)}") from exc
        if not isinstance(value, dict):
            raise ValueError(f"Dependency {name} requires a JSON object: {path.relative_to(RELEASE_ROOT)}")
        return value

    frozen = object_file(result / "FROZEN.json")
    if frozen.get("reproduction_config") is not True:
        raise ValueError(f"Dependency {name} is not a new reproduction run; historical metadata is unsupported")
    plan_value = frozen.get("plan_path")
    if (not isinstance(plan_value, str) or not plan_value
            or Path(plan_value).is_absolute() or PureWindowsPath(plan_value).is_absolute()):
        raise ValueError(f"Dependency {name} must record a relative plan_path")
    dependency_plan = root_path(plan_value, must_exist=True)
    if not dependency_plan.parent.name.startswith(name + "_"):
        raise ValueError(f"Dependency {name} points to another experiment's plan: {plan_value}")
    object_file(dependency_plan)
    relative = dependency_plan.relative_to(RELEASE_ROOT).as_posix()
    expected = frozen.get("plan_sha256", frozen.get("plan_sha"))
    if expected is None:
        sources = frozen.get("sources", {})
        expected = sources.get(relative) if isinstance(sources, dict) else None
    actual = hashlib.sha256(dependency_plan.read_bytes()).hexdigest()
    if not isinstance(expected, str) or expected != actual:
        raise ValueError(f"Dependency {name} plan differs from its frozen hash")

    if "jobs" in frozen:
        jobs = frozen["jobs"]
        if type(jobs) is not int or jobs <= 0:
            raise ValueError(f"Dependency {name} has an invalid frozen job count")
        gate = object_file(result / "gate.json")
        if "problems" not in gate or gate["problems"] != []:
            raise ValueError(f"Dependency {name} gate did not pass: {gate.get('problems')}")
        receipts = root_path(result / "receipts", must_exist=True)
        files = sorted(receipts.glob("*.json"))
        if len(files) != jobs:
            raise ValueError(f"Dependency {name} is incomplete: {len(files)}/{jobs} receipts")
        for receipt in files:
            object_file(receipt)
    else:
        status = object_file(result / "STATUS.json")
        pipeline = object_file(result / "PIPELINE_EXIT.json")
        if status.get("state") != "COMPLETED" or pipeline.get("status") != "completed":
            raise ValueError(f"Dependency {name} pipeline has not completed")
    return result


def configure_runtime(threads=None, cpus=None) -> dict:
    """Default to one thread; affinity is optional and restricted to available CPUs."""
    threads = int(threads if threads is not None else os.environ.get("ABYSS_THREADS", "1"))
    if threads < 1:
        raise ValueError("ABYSS_THREADS/threads must be positive")
    os.environ["OMP_NUM_THREADS"] = os.environ["MKL_NUM_THREADS"] = str(threads)
    import torch
    torch.set_num_threads(threads)
    requested = cpus if cpus is not None else os.environ.get("ABYSS_CPU_AFFINITY", "")
    result = {"threads": threads, "cpu_affinity": None, "hard_utilization_limit": False}
    if not requested:
        return result
    if isinstance(requested, str):
        requested = [int(x.strip()) for x in requested.split(",") if x.strip()]
    import psutil
    proc = psutil.Process()
    if not hasattr(proc, "cpu_affinity"):
        warnings.warn("CPU affinity is unavailable on this platform; continuing without affinity")
        return result
    try:
        available = set(proc.cpu_affinity())
    except (NotImplementedError, psutil.Error) as exc:
        warnings.warn(f"Cannot query CPU affinity; continuing without affinity: {exc}")
        return result
    selected = sorted(set(map(int, requested)))
    if not selected or not set(selected).issubset(available):
        raise ValueError(f"Requested affinity must be a nonempty subset of allowed CPUs {sorted(available)}")
    proc.cpu_affinity(selected)
    result["cpu_affinity"] = selected
    return result


def runner_arguments(description: str, *, gate_trains: bool = False):
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("output", help="Run directory relative to the release root")
    sub = parser.add_subparsers(dest="command", required=True)
    gate = sub.add_parser("gate", help="Prepare and validate a fresh run" + (" (trains models)" if gate_trains else ""))
    if gate_trains:
        gate.add_argument("--allow-training", action="store_true", help="Explicitly enable the training performed by this gate")
    worker = sub.add_parser("worker", help="Train one explicitly requested worker")
    worker.add_argument("index", nargs="?", default=0, type=int)
    worker.add_argument("count", nargs="?", default=1, type=int)
    args = parser.parse_args()
    args.output = root_path(args.output)
    if args.command == "gate" and gate_trains and not args.allow_training:
        parser.error("This gate trains models. Re-run explicitly with gate --allow-training.")
    if args.command == "worker" and (args.count < 1 or not 0 <= args.index < args.count):
        parser.error("Worker indices must satisfy 0 <= index < count; count defaults to 1")
    return args


def require_successful_gate(out: Path) -> None:
    gate = json.loads((out / "gate.json").read_text(encoding="utf-8"))
    if gate.get("problems"):
        raise RuntimeError(f"The run gate failed; do not train this run: {gate['problems']}")

