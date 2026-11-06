"""Small static checks only: no project imports, tests, training, or downloads."""
from __future__ import annotations

import argparse
import ast
from datetime import datetime, timezone
import hashlib
import json
import re
import sys
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "project" / "empirical_core"
IGNORED_DIRS = {".git", ".venv", "venv", "__pycache__", ".pytest_cache", "build", "dist"}
FORBIDDEN_SUFFIXES = {".pt", ".pth", ".sqlite", ".sqlite3", ".db", ".bin", ".u16", ".parquet", ".npz", ".npy", ".jsonl", ".pem", ".pfx", ".key"}
TEXT_SUFFIXES = {".py", ".md", ".json", ".toml", ".txt", ".ps1", ".yml", ".yaml"}
SECRET_PATTERN = re.compile(
    r"sk-[A-Za-z0-9_-]{20,}|ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}"
    r"|AKIA[A-Z0-9]{16}|BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY"
)
LOCAL_PATH = re.compile(r"(?<![A-Za-z0-9])[CDE]:[\\/]")
PRIVATE_HISTORY = re.compile("用户原话|亲爱的|小修女|大小姐|小女巫|执政官")


def relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def check() -> dict:
    problems: list[dict] = []
    counts = {"python": 0, "json": 0, "toml": 0, "text_scanned": 0, "local_markdown_links": 0}
    source_modules: dict[str, Path] = {}
    parsed: dict[Path, ast.Module] = {}
    manifest: list[dict] = []

    def issue(path: Path, kind: str, line: int | None = None, detail: str | None = None):
        item = {"path": relative(path), "kind": kind}
        if line is not None:
            item["line"] = line
        if detail is not None:
            item["detail"] = detail
        problems.append(item)

    files = sorted(p for p in ROOT.rglob("*") if p.is_file()
                   and not any(part in IGNORED_DIRS for part in p.relative_to(ROOT).parts))
    for path in files:
        rel = relative(path)
        if rel in {"STATIC_CHECKS.json", "RELEASE_MANIFEST.json"}:
            continue
        if path.is_symlink():
            issue(path, "symlink_requires_review")
            continue
        if path.suffix.lower() in FORBIDDEN_SUFFIXES or path.name == ".env" or path.name.startswith(".env."):
            issue(path, "excluded_material_or_credential_filename")
            continue
        if path.stat().st_size > 2_000_000:
            issue(path, "unexpected_large_file")
            continue
        data = path.read_bytes()
        manifest.append({"path": rel, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
        if path.suffix.lower() not in TEXT_SUFFIXES and path.name != ".gitignore":
            issue(path, "unclassified_file")
            continue
        try:
            content = data.decode("utf-8-sig")
        except UnicodeError:
            issue(path, "non_utf8_text")
            continue
        counts["text_scanned"] += 1
        if path.suffix == ".md":
            for match in re.finditer(r"\[[^\]]+\]\(([^\s)]+)\)", content):
                target = match.group(1).split("#", 1)[0]
                if not target or re.match(r"[A-Za-z][A-Za-z0-9+.-]*:", target):
                    continue
                counts["local_markdown_links"] += 1
                resolved = (path.parent / target).resolve()
                if not resolved.is_relative_to(ROOT) or not resolved.exists():
                    issue(path, "missing_or_external_local_link", content.count("\n", 0, match.start()) + 1, target)
        # This file defines scanner signatures, not credentials or user history.
        if path != Path(__file__).resolve():
            for line_no, line in enumerate(content.splitlines(), 1):
                for label, pattern in (("credential_pattern", SECRET_PATTERN),
                                       ("original_machine_absolute_path", LOCAL_PATH),
                                       ("private_conversation_marker", PRIVATE_HISTORY)):
                    if pattern.search(line):
                        issue(path, label, line_no)
        try:
            if path.suffix == ".py":
                tree = ast.parse(content, filename=rel)
                parsed[path] = tree
                counts["python"] += 1
                if path.is_relative_to(CORE):
                    parts = list(path.relative_to(CORE.parent).with_suffix("").parts)
                    if parts[-1] == "__init__":
                        parts.pop()
                    source_modules[".".join(parts)] = path
            elif path.suffix == ".json":
                json.loads(content)
                counts["json"] += 1
            elif path.suffix == ".toml":
                tomllib.loads(content)
                counts["toml"] += 1
        except (SyntaxError, ValueError) as exc:
            issue(path, "parse_error", getattr(exc, "lineno", None), str(exc))

    for path, tree in parsed.items():
        if not path.is_relative_to(CORE):
            continue
        package = ["empirical_core", *path.relative_to(CORE).parent.parts]
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.level:
                    base = package[:len(package) - node.level + 1]
                    module = ".".join(base + (node.module.split(".") if node.module else []))
                else:
                    module = node.module or ""
                if module.startswith("empirical_core") and module not in source_modules:
                    issue(path, "missing_internal_module", node.lineno, module)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("empirical_core") and alias.name not in source_modules:
                        issue(path, "missing_internal_module", node.lineno, alias.name)

    required = [
        "README.md", "README.en.md", "pyproject.toml", "LICENSE-STATUS.md", "NOTICES.md",
        "docs/REPRODUCIBILITY.zh.md", "docs/REPRODUCIBILITY.en.md",
        "docs/DATA_SOURCES.zh.md", "docs/DATA_SOURCES.en.md",
        "docs/CORE_CHANGES.md", "docs/EXPERIMENT_CHANGES.md",
        "historical/RESULTS.zh.md", "historical/RESULTS.en.md",
        "historical/SOURCE_SNAPSHOT.json",
        "project/tests/_helpers.py", "project/conftest.py",
        "experiments/t4_survival_20261103/live_t4.py",
    ]
    for name in required:
        path = ROOT / name
        if not path.is_file():
            issue(path, "missing_required_file")
    for name in ("README.md", "README.en.md"):
        path = ROOT / name
        if path.is_file():
            content = path.read_text(encoding="utf-8-sig")
            if "深渊 / The Abyss" not in content:
                issue(path, "missing_entrance_marker")
            if "逻辑是知识的可达路径" not in content or "Logic is the path that makes knowledge reachable" not in content:
                issue(path, "missing_bilingual_first_principle")
    return {
        "schema_version": 1,
        "checked_utc": datetime.now(timezone.utc).isoformat(),
        "validator_python": sys.version.split()[0],
        "scope": "Static parsing, internal module lookup, required files, bounded text/filename scan and SHA256 only",
        "not_performed": ["project imports", "dependency installation", "unit tests", "training", "model loading", "network requests", "independent historical replication"],
        "status": "passed" if not problems else "needs_attention",
        "counts": counts,
        "problems": problems,
        "files": manifest,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", help="Optional JSON output path inside this candidate")
    args = parser.parse_args()
    report = check()
    if args.report:
        destination = (ROOT / args.report).resolve()
        if not destination.is_relative_to(ROOT):
            parser.error("report must stay inside the candidate")
        if destination.name != "STATIC_CHECKS.json":
            parser.error("use STATIC_CHECKS.json to avoid overwriting source or provenance")
        destination.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "files"}, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
