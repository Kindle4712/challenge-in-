"""Locate challenge-2 symbols in the installed SGLang source tree."""

from __future__ import annotations

import ast
import argparse
import importlib.util
import json
from pathlib import Path


SYMBOLS = {
    "TokenizerManager",
    "generate_request",
    "Scheduler",
    "event_loop_normal",
    "get_new_batch_prefill",
    "match_prefix_for_req",
    "RadixCache",
    "match_prefix",
    "PrefillAdder",
    "ScheduleBatch",
    "cache_finished_req",
    "cache_unfinished_req",
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", type=Path, help="Path to a v0.5.14 sglang package")
    args = parser.parse_args()
    if args.source_dir:
        package_dir = args.source_dir.resolve()
    else:
        spec = importlib.util.find_spec("sglang")
        if spec is None or not spec.submodule_search_locations:
            raise SystemExit("SGLang is not installed in this Python environment")
        package_dir = Path(next(iter(spec.submodule_search_locations)))
    if not (package_dir / "srt").is_dir():
        raise SystemExit("Source directory must be the sglang package directory")
    found: dict[str, list[dict[str, object]]] = {symbol: [] for symbol in sorted(SYMBOLS)}
    for path in package_dir.rglob("*.py"):
        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(path))
        except (OSError, SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in SYMBOLS:
                found[node.name].append({
                    "file": str(path.relative_to(package_dir.parent)).replace("\\", "/"),
                    "line": node.lineno,
                    "kind": type(node).__name__,
                })
    output = Path("results/target2/source_locations.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(found, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"SGLang source: {package_dir}")
    print(f"Symbol locations: {output.resolve()}")
    for symbol, locations in found.items():
        labels = ["{}:{}".format(item["file"], item["line"]) for item in locations]
        print("{}: {}".format(symbol, ", ".join(labels) or "NOT FOUND"))


if __name__ == "__main__":
    main()
