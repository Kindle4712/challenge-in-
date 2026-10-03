"""Check the saved challenge-2 data against the task requirements."""

from __future__ import annotations

import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "results" / "target1"
INPUTS = ROOT / "src" / "target1" / "inputs"
GROUPS = ("shared_prefix", "dispersed_prefix")


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    summaries = {}
    inputs = {}
    for group in GROUPS:
        input_path = INPUTS / group / "input_ids.jsonl"
        result_path = RESULTS / group / "requests.jsonl"
        inputs[group] = [json.loads(line)["input_ids"] for line in input_path.read_text(encoding="utf-8").splitlines()]
        records = [json.loads(line) for line in result_path.read_text(encoding="utf-8").splitlines()]
        summary = read_json(RESULTS / group / "summary.json")
        assert len(inputs[group]) == len(records) == summary["requests"] == 32
        assert all(len(ids) == 2112 for ids in inputs[group])
        assert all(record["success"] and record["error"] is None for record in records)
        assert all(record["prompt_tokens"] == 2112 and record["completion_tokens"] == 16 for record in records)
        assert all(isinstance(record["cached_tokens"], int) for record in records)
        assert summary["successful_requests"] == 32 and summary["success_rate"] == 1
        prompt_total = sum(record["prompt_tokens"] for record in records)
        cached_total = sum(record["cached_tokens"] for record in records)
        assert summary["prompt_tokens_total"] == prompt_total
        assert summary["cached_tokens_total"] == cached_total
        assert summary["actual_prefill_tokens_total"] == prompt_total - cached_total
        assert math.isclose(summary["cache_hit_rate"], cached_total / prompt_total)
        assert all(record["ttft_ms"] is not None and record["tpot_ms"] is not None for record in records)
        summaries[group] = summary
        print("{}: 32/32 success; cached={}, prefill={}".format(group, cached_total, prompt_total - cached_total))

    shared = inputs["shared_prefix"]
    dispersed = inputs["dispersed_prefix"]
    warmup = read_json(INPUTS / "shared_prefix" / "warmup_input_ids.json")
    assert len(warmup) == 2112
    assert all(ids[:2048] == warmup[:2048] for ids in shared)
    assert len({ids[0] for ids in dispersed}) == 32
    assert summaries["shared_prefix"]["cache_hit_rate"] > summaries["dispersed_prefix"]["cache_hit_rate"]
    assert summaries["shared_prefix"]["actual_prefill_tokens_total"] < summaries["dispersed_prefix"]["actual_prefill_tokens_total"]
    print("All task-1 acceptance checks passed")


if __name__ == "__main__":
    main()
