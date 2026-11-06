"""G1: fixed T1 data, shared-score granularity; no torch, GPU, or network."""
from __future__ import annotations
import argparse
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import random
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parent

def utc(): return datetime.now(timezone.utc).isoformat()
def encoded(value): return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
def digest(data): return hashlib.sha256(data).hexdigest()
def put(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encoded(value))
def read(path): return json.loads(path.read_text(encoding="utf-8"))
def rng_for(seed, tag): return random.Random(int.from_bytes(hashlib.sha256(f"{seed}|{tag}".encode()).digest()[:8], "big"))
def source_manifest():
    return {name: digest((ROOT / name).read_bytes()) for name in ["PLAN.json", "PREREG.md", "README.md", "ATTEMPT_NOTE.md", "pilot.py", "report.py", "vendor/t1_task.py"]}

class ResourceStop(RuntimeError): pass

class Guard:
    """Cooperative limits, applied only to this newly started process."""
    def __init__(self, config):
        import psutil
        self.psutil = psutil
        self.config = config
        self.proc = psutil.Process()  # no external PID is ever selected
        self.start_wall = time.monotonic()
        self.start_cpu = sum(self.proc.cpu_times()[:2])
        self.check_wall = self.start_wall
        self.samples = []

    def start(self):
        allowed = self.proc.cpu_affinity()
        core = self.config["cpu_id"]
        if core not in allowed:
            raise ResourceStop("Configured CPU is not in this process's allowed set")
        self.original = {"allowed_cpus": allowed, "priority": self.proc.nice()}
        try:
            self.proc.cpu_affinity([core])
            self.proc.nice(self.psutil.IDLE_PRIORITY_CLASS)
        except self.psutil.Error as exc:
            raise ResourceStop("Own process controls unavailable: " + type(exc).__name__) from exc
        for _ in range(3):
            self.sample(self.psutil.cpu_percent(interval=0.4, percpu=True))
        self.proc.cpu_percent(None)

    def sample(self, cpus=None):
        # Pause our computation during resource sampling. The previous short
        # nonblocking window counted our own generation burst as external load.
        cpus = cpus if cpus is not None else self.psutil.cpu_percent(interval=0.4, percpu=True)
        vm = self.psutil.virtual_memory()
        item = {"utc": utc(), "host_mean_cpu": statistics.mean(cpus), "selected_cpu": cpus[self.config["cpu_id"]], "available_memory_mb": vm.available / 1048576}
        self.samples.append(item)
        if item["host_mean_cpu"] > self.config["max_mean_host_cpu_percent"] or item["selected_cpu"] > self.config["max_selected_cpu_percent"] or item["available_memory_mb"] < self.config["min_available_memory_mb"]:
            raise ResourceStop("Resource gate exceeded; no other process was changed")

    def checkpoint(self):
        now = time.monotonic()
        cpu = sum(self.proc.cpu_times()[:2]) - self.start_cpu
        if cpu > self.config["max_cpu_seconds"] or now - self.start_wall > self.config["max_wall_seconds"]:
            raise ResourceStop("Own process budget reached")
        # Soft duty cycle: accounting includes preparation, evaluation and I/O.
        while cpu / self.config["duty_fraction"] > now - self.start_wall:
            time.sleep(min(0.2, cpu / self.config["duty_fraction"] - (now - self.start_wall)))
            now = time.monotonic()
            if now - self.start_wall > self.config["max_wall_seconds"]:
                raise ResourceStop("Own process wall budget reached while throttling")
            if now - self.check_wall >= 1:
                self.sample()
                self.check_wall = now
            cpu = sum(self.proc.cpu_times()[:2]) - self.start_cpu
        if now - self.check_wall >= 1:
            self.sample()
            self.check_wall = now

    def report(self):
        return {"wall_seconds": time.monotonic() - self.start_wall, "cpu_seconds": sum(self.proc.cpu_times()[:2]) - self.start_cpu, "rss_mb": self.proc.memory_info().rss / 1048576, "cpu_affinity": self.proc.cpu_affinity(), "priority": self.proc.nice(), "cooperative_not_hard_limit": True, "gpu_used": False, "samples": self.samples}

def generator():
    spec = importlib.util.spec_from_file_location("g1_t1_task", ROOT / "vendor/t1_task.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module

def group_maps(seed, plan):
    n = plan["learner"]["allocated_scalar_slots"]
    members = plan["generator"]["n_members"]
    family_order = []
    for p in range(plan["generator"]["n_packages"]):
        ids = list(range(p * members, (p + 1) * members))
        rng_for(seed, f"family partition {p}").shuffle(ids)
        family_order += ids
    random_order = list(range(n))
    rng_for(seed, "random partition").shuffle(random_order)
    result = {}
    for arm in plan["arms"]:
        order = family_order if arm["kind"] == "family" else random_order
        mapping = list(range(n))
        for start in range(0, n, arm["size"]):
            block = order[start:start + arm["size"]]
            representative = min(block)
            for atom in block:
                mapping[atom] = representative
        counts = defaultdict(int)
        for g in mapping: counts[g] += 1
        assert set(counts.values()) == {arm["size"]}
        result[arm["name"]] = mapping
    assert result["atomic"] == list(range(n))
    return result

def prepare(plan, guard):
    if (ROOT / "FROZEN.json").exists() or (ROOT / "data").exists():
        raise RuntimeError("Preparation requires a fresh output directory; existing evidence is retained")
    (ROOT / "data").mkdir()
    t1 = generator()
    hashes = {}
    audits = []
    n_members = plan["generator"]["n_members"]
    for seed in plan["seeds"]:
        raw = t1.build_t1(t1.T1Spec(seed=seed, **plan["generator"]))
        rows = []
        split_pairs = defaultdict(set)
        for e in raw["episodes"]:
            a, b = t1.resolve(t1.visible(e))
            va, vb = (raw["hidden_values"][f"{o[0]},{o[1]}"] for o in (a, b))
            assert t1.label_of(e["world"], va, vb) == e["label"]
            aa, bb = a[0] * n_members + a[1], b[0] * n_members + b[1]
            split_pairs[e["split"]].add(tuple(sorted((aa, bb))))
            row = {"id": e["id"], "split": e["split"], **t1.visible(e), "a": aa, "b": bb, "sign": 1 if e["world"] == "physical" else -1, "label": e["label"], "winner_atom": aa if e["label"] else bb, "reference_same_package": a[0] == b[0], "pair_kind": e["hidden"]["pair_kind"]}
            rows.append(row)
        assert not (split_pairs["train"] & split_pairs["test"] or split_pairs["train"] & split_pairs["dev"] or split_pairs["dev"] & split_pairs["test"])
        by_pair = defaultdict(list)
        for i, r in enumerate(rows):
            if r["split"] == "train": by_pair[tuple(sorted((r["a"], r["b"])))].append(i)
        selection_rng = rng_for(seed, "training selection")
        choices = [selection_rng.choice(by_pair[p]) for p in sorted(by_pair)]
        selection_rng.shuffle(choices)
        assert len(choices) >= max(plan["train_pairs"])
        selections, orders = {}, {}
        for budget in plan["train_pairs"]:
            selected = choices[:budget]
            selections[str(budget)] = selected
            sample_rng = rng_for(seed, f"update order {budget}")
            orders[str(budget)] = [sample_rng.randrange(budget) for _ in range(plan["learner"]["steps"])]
        mappings = group_maps(seed, plan)
        value = {"seed": seed, "rows": rows, "selections": selections, "orders": orders, "group_maps": mappings, "oracle_values_not_for_learner": raw["hidden_values"]}
        name = f"data/seed-{seed}.json"
        put(ROOT / name, value)
        hashes[name] = digest((ROOT / name).read_bytes())
        audit = {"seed": seed, "episodes": len(rows), "unique_pairs_by_split": {k: len(v) for k, v in split_pairs.items()}, "cross_split_pair_overlap": 0, "test_within_reference": sum(r["split"] == "test" and r["reference_same_package"] for r in rows), "selection_hashes": {k: digest(encoded(v)) for k, v in selections.items()}, "order_hashes": {k: digest(encoded(v)) for k, v in orders.items()}, "mapping_hashes": {k: digest(encoded(v)) for k, v in mappings.items()}}
        audits.append(audit)
        print(json.dumps({"phase": "prepared_seed", "seed": seed, "episodes": len(rows)}), flush=True)
        guard.checkpoint()
    put(ROOT / "DATA_AUDIT.json", {"status": "passed", "audits": audits, "hidden_values_used_only_to_audit_generated_labels": True})
    hashes["DATA_AUDIT.json"] = digest((ROOT / "DATA_AUDIT.json").read_bytes())
    put(ROOT / "FROZEN.json", {"created_utc": utc(), "training_started": False, "sources": source_manifest(), "data": hashes, "all_arms_share_frozen_data_and_orders": True})

def observations(rows, selection):
    # The learning boundary contains exactly endpoints, known world sign and label.
    return [(rows[i]["a"], rows[i]["b"], rows[i]["sign"], rows[i]["label"]) for i in selection]

def sigmoid(z):
    return 1 / (1 + math.exp(-max(-35.0, min(35.0, z))))

def fit(obs, order, mapping, config, guard):
    weights = [0.0] * config["allocated_scalar_slots"]
    curve, collapsed_steps = [], 0
    total_loss = 0.0
    for step, index in enumerate(order, 1):
        a, b, sign, label = obs[index]
        ga, gb = mapping[a], mapping[b]
        prob = sigmoid(sign * (weights[ga] - weights[gb]))
        total_loss -= math.log(max(1e-15, prob if label else 1 - prob))
        if ga == gb:
            collapsed_steps += 1
        else:
            gradient = config["learning_rate"] * (label - prob) * sign
            weights[ga] += gradient
            weights[gb] -= gradient
        if step in config["checkpoints"]:
            curve.append({"step": step, "mean_online_loss": total_loss / step, "noncollapsed_updates": step - collapsed_steps})
        if step % 128 == 0: guard.checkpoint()
    assert len(order) == config["steps"]
    return weights, {"curve": curve, "presentations": len(order), "collapsed_steps": collapsed_steps, "noncollapsed_updates": len(order) - collapsed_steps}

def graph_info(obs, n):
    parent = list(range(n))
    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    seen = set()
    for a, b, _, _ in obs:
        seen.update((a, b))
        parent[find(a)] = find(b)
    components = [find(i) for i in range(n)]
    counts = defaultdict(int)
    for c in components: counts[c] += 1
    return seen, components, {"seen_atoms": len(seen), "unseen_atoms": n - len(seen), "components_including_isolated": len(counts), "largest_component": max(counts.values()), "distinct_training_pairs": len({tuple(sorted((a, b))) for a, b, _, _ in obs})}

def metrics(rows, weights, mapping, seen, components, seed):
    buckets = defaultdict(lambda: {"n": 0, "expected_correct": 0.0, "deterministic_correct": 0, "tie_count": 0})
    conflicts = defaultdict(lambda: [0, 0])
    collapsed = 0
    fixed_errors = {"within_reference": 0.0, "cross_reference": 0.0}
    tie_rng = rng_for(seed, "evaluation ties")
    for r in rows:
        a, b, label = r["a"], r["b"], r["label"]
        ga, gb = mapping[a], mapping[b]
        score = r["sign"] * (weights[ga] - weights[gb])
        tie = abs(score) < 1e-12
        tie_choice = tie_rng.randrange(2)  # consume for every row, in every arm
        decision = tie_choice if tie else int(score > 0)
        correct = 0.5 if tie else float(decision == label)
        tags = ["all", "within_reference" if r["reference_same_package"] else "cross_reference", "shared_slot" if ga == gb else "distinct_slots", "both_atoms_seen" if a in seen and b in seen else "has_unseen_atom", "same_atomic_component" if components[a] == components[b] else "different_atomic_components"]
        for tag in tags:
            q = buckets[tag]
            q["n"] += 1
            q["expected_correct"] += correct
            q["deterministic_correct"] += decision == label
            q["tie_count"] += tie
        fixed_errors["within_reference" if r["reference_same_package"] else "cross_reference"] += 1 - correct
        if ga == gb:
            collapsed += 1
        else:
            physical_a_wins = label if r["sign"] == 1 else 1 - label
            winner_group = ga if physical_a_wins else gb
            key = tuple(sorted((ga, gb)))
            conflicts[key][int(winner_group == key[1])] += 1
    for q in buckets.values():
        q["expected_accuracy"] = q["expected_correct"] / q["n"]
        q["deterministic_accuracy"] = q["deterministic_correct"] / q["n"]
    n = len(rows)
    conflict_rows = sum(sum(c) for c in conflicts.values() if min(c) > 0)
    lookup = (sum(max(c) for c in conflicts.values()) + 0.5 * collapsed) / n
    assert buckets["all"]["expected_accuracy"] <= lookup + 1e-12
    assert abs(buckets["all"]["expected_accuracy"] + sum(fixed_errors.values()) / n - 1) < 1e-12
    return {"strata": dict(buckets), "test_unique_unordered_pairs": len({tuple(sorted((r['a'], r['b']))) for r in rows}), "error_mass": {k: v / n for k, v in fixed_errors.items()}, "shared_slot_fraction": collapsed / n, "correct_group_random_tie_reference": 1 - 0.5 * collapsed / n, "group_pair_conflicts": {"distinct_noncollapsed_group_pairs": len(conflicts), "conflicting_group_pairs": sum(min(c) > 0 for c in conflicts.values()), "conflicting_rows": conflict_rows, "conflicting_fraction_of_all_rows": conflict_rows / n, "posthoc_test_label_majority_lookup_reference": lookup, "not_used_for_training_or_arm_selection": True}}

def run(plan, guard):
    frozen = read(ROOT / "FROZEN.json")
    assert frozen["sources"] == source_manifest(), "Frozen sources changed"
    for name, expected in frozen["data"].items():
        assert digest((ROOT / name).read_bytes()) == expected, f"Frozen data changed: {name}"
    if (ROOT / "receipts").exists(): raise RuntimeError("Existing run retained; automatic resume/overwrite is disabled")
    (ROOT / "receipts").mkdir()
    completed_seeds = []
    put(ROOT / "RUN_STATUS.json", {"status": "RUNNING", "started_utc": utc(), "complete_seeds": []})
    for seed in plan["seeds"]:
        data = read(ROOT / f"data/seed-{seed}.json")
        test = [r for r in data["rows"] if r["split"] in plan["evaluation_splits"]]
        for budget in plan["train_pairs"]:
            obs = observations(data["rows"], data["selections"][str(budget)])
            order = data["orders"][str(budget)]
            presented = [obs[i] for i in sorted(set(order))]
            seen, components, graph = graph_info(presented, plan["learner"]["allocated_scalar_slots"])
            graph["selected_unique_pairs"] = len(obs)
            graph["presented_unique_pairs"] = len(presented)
            for arm in plan["arms"]:
                mapping = data["group_maps"][arm["name"]]
                weights, training = fit(obs, order, mapping, plan["learner"], guard)
                result = metrics(test, weights, mapping, seen, components, seed)
                receipt = {"seed": seed, "train_pairs": budget, "arm": arm, "dataset_sha256": frozen["data"][f"data/seed-{seed}.json"], "learner_observations_sha256": digest(encoded(obs)), "update_order_sha256": digest(encoded(order)), "mapping_sha256": digest(encoded(mapping)), "allocated_slots": len(weights), "active_shared_scores": len(set(mapping)), "graph": graph, "training": training, "metrics": result, "weights": weights, "completed_utc": utc()}
                put(ROOT / "receipts" / f"s{seed}-n{budget}-{arm['name']}.json", receipt)
                guard.checkpoint()
        completed_seeds.append(seed)
        put(ROOT / "RUN_STATUS.json", {"status": "RUNNING", "complete_seeds": completed_seeds, "receipts": len(list((ROOT / 'receipts').glob('*.json')))})
        print(json.dumps({"phase": "completed_balanced_seed", "seed": seed, "of": len(plan["seeds"])}), flush=True)
    assert frozen["sources"] == source_manifest()
    put(ROOT / "RUN_STATUS.json", {"status": "COMPLETED", "complete_seeds": completed_seeds, "receipts": len(list((ROOT / 'receipts').glob('*.json'))), "finished_utc": utc()})

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=["prepare", "run"])
    args = parser.parse_args()
    plan = read(ROOT / "PLAN.json")
    guard = None
    try:
        guard = Guard(plan["resource"])
        guard.start()
        (prepare if args.phase == "prepare" else run)(plan, guard)
    except ResourceStop as exc:
        path = ROOT / ("PREPARE_STATUS.json" if args.phase == "prepare" else "RUN_STATUS.json")
        prior = read(path) if path.exists() else {}
        put(path, {**prior, "status": "INCOMPLETE_RESOURCE_STOP", "reason": str(exc), "utc": utc()})
        print(json.dumps({"status": "INCOMPLETE_RESOURCE_STOP", "reason": str(exc)}), flush=True)
        return 2
    finally:
        if guard is not None: put(ROOT / f"RESOURCES_{args.phase}.json", guard.report())
    print(json.dumps({"phase": args.phase, "status": "COMPLETED"}), flush=True)
    return 0

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
