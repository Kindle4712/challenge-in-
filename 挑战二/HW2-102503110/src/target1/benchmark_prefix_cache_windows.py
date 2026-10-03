"""Run the challenge-2 SGLang workload with only Python's standard library.

This client can run on Windows against the SGLang server hosted in WSL. It
disables HTTP proxies for localhost, which is necessary on this machine.
"""

from __future__ import annotations

import json
import random
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "results" / "target1"
INPUTS = ROOT / "src" / "target1" / "inputs"
BASE_URL = "http://127.0.0.1:30000"
MODEL = "Qwen/Qwen3-0.6B"
SEED = 2026
REQUEST_COUNT = 32
CONCURRENCY = 8
PREFIX_LENGTH = 2048
SUFFIX_LENGTH = 64
PROMPT_LENGTH = PREFIX_LENGTH + SUFFIX_LENGTH
OUTPUT_LENGTH = 16
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def make_workloads() -> tuple[dict[str, list[list[int]]], list[int]]:
    # Qwen3 ordinary vocabulary IDs lie below its high-valued special-token IDs.
    # This narrow range is valid for Qwen3-0.6B and keeps all prompts token-native.
    ordinary_ids = range(1000, 100000)
    rng = random.Random(SEED)
    first_tokens = rng.sample(ordinary_ids, REQUEST_COUNT)
    shared_prefix = rng.choices(ordinary_ids, k=PREFIX_LENGTH)
    suffixes = [rng.choices(ordinary_ids, k=SUFFIX_LENGTH) for _ in range(REQUEST_COUNT)]
    workloads = {
        "shared_prefix": [shared_prefix + suffix for suffix in suffixes],
        "dispersed_prefix": [
            [first_tokens[i]] + rng.choices(ordinary_ids, k=PREFIX_LENGTH - 1) + suffixes[i]
            for i in range(REQUEST_COUNT)
        ],
    }
    warmup = shared_prefix + rng.choices(ordinary_ids, k=SUFFIX_LENGTH)
    assert all(len(ids) == PROMPT_LENGTH for group in workloads.values() for ids in group)
    assert len({ids[0] for ids in workloads["dispersed_prefix"]}) == REQUEST_COUNT
    return workloads, warmup


def request_json(path: str, payload: dict[str, Any] | None = None) -> tuple[int, bytes]:
    body = json.dumps(payload).encode("utf-8") if payload is not None else b""
    request = urllib.request.Request(
        BASE_URL + path,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with OPENER.open(request, timeout=300) as response:
        return response.status, response.read()


def generate(input_ids: list[int], request_id: str) -> dict[str, Any]:
    body = {
        "input_ids": input_ids,
        "stream": True,
        "sampling_params": {
            "temperature": 0,
            "max_new_tokens": OUTPUT_LENGTH,
            "ignore_eos": True,
            "sampling_seed": SEED,
        },
    }
    request = urllib.request.Request(
        BASE_URL + "/generate",
        data=json.dumps(body).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    start = time.perf_counter()
    first_token_at = None
    last_token_at = None
    last_count = 0
    events = []
    meta = {}
    status = None
    error = None
    try:
        with OPENER.open(request, timeout=300) as response:
            status = response.status
            for raw_line in response:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    continue
                event = json.loads(data)
                events.append(event)
                current_meta = event.get("meta_info") or {}
                if isinstance(current_meta, dict):
                    meta = current_meta
                    count = meta.get("completion_tokens", 0)
                    if isinstance(count, int) and count > last_count:
                        now = time.perf_counter()
                        if first_token_at is None:
                            first_token_at = now
                        last_token_at = now
                        last_count = count
    except (urllib.error.URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
        error = str(exc)
    end = time.perf_counter()
    prompt_tokens = meta.get("prompt_tokens")
    completion_tokens = meta.get("completion_tokens")
    cached_tokens = meta.get("cached_tokens")
    success = (
        error is None
        and status == 200
        and prompt_tokens == len(input_ids)
        and completion_tokens == OUTPUT_LENGTH
        and first_token_at is not None
    )
    return {
        "request_id": request_id,
        "status": status,
        "success": success,
        "input_tokens": len(input_ids),
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "cached_tokens": cached_tokens,
        "actual_prefill_tokens": (
            prompt_tokens - cached_tokens
            if isinstance(prompt_tokens, int) and isinstance(cached_tokens, int)
            else None
        ),
        "ttft_ms": (first_token_at - start) * 1000 if first_token_at is not None else None,
        "tpot_ms": (
            (last_token_at - first_token_at) * 1000 / (completion_tokens - 1)
            if first_token_at is not None and last_token_at is not None
            and isinstance(completion_tokens, int) and completion_tokens > 1
            else None
        ),
        "e2e_ms": (end - start) * 1000,
        "meta_info": meta,
        "stream_events": events,
        "error": error or (None if success else "Missing or mismatched final token counts"),
    }


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    values = sorted(values)
    position = (len(values) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(values) - 1)
    return values[lower] + (values[upper] - values[lower]) * (position - lower)


def summarize(name: str, records: list[dict[str, Any]], elapsed: float) -> dict[str, Any]:
    good = [record for record in records if record["success"]]
    cache_known = bool(good) and all(isinstance(record["cached_tokens"], int) for record in good)
    prompt_total = sum(record["prompt_tokens"] for record in good)
    cached_total = sum(record["cached_tokens"] for record in good) if cache_known else None
    summary = {
        "group": name,
        "requests": len(records),
        "successful_requests": len(good),
        "success_rate": len(good) / len(records),
        "wall_time_s": elapsed,
        "throughput_requests_per_s": len(good) / elapsed,
        "throughput_output_tokens_per_s": sum(record["completion_tokens"] for record in good) / elapsed,
        "prompt_tokens_total": prompt_total,
        "cached_tokens_total": cached_total,
        "cache_hit_rate": cached_total / prompt_total if cached_total is not None and prompt_total else None,
        "actual_prefill_tokens_total": prompt_total - cached_total if cached_total is not None else None,
        "cache_metrics_available": cache_known,
    }
    for field in ("ttft_ms", "tpot_ms", "e2e_ms"):
        values = [record[field] for record in good if record[field] is not None]
        summary[field + "_p50"] = percentile(values, 0.50)
        summary[field + "_p95"] = percentile(values, 0.95)
    return summary


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def run_group(name: str, inputs: list[list[int]], warmup: list[int] | None) -> dict[str, Any]:
    status, raw = request_json("/flush_cache")
    if status != 200:
        raise RuntimeError("/flush_cache returned HTTP {}: {}".format(status, raw[:300]))
    try:
        flush_result = json.loads(raw)
    except json.JSONDecodeError:
        flush_result = raw.decode("utf-8", errors="replace")
    if isinstance(flush_result, dict) and (flush_result.get("success") is False or flush_result.get("error")):
        raise RuntimeError("/flush_cache failed: {}".format(flush_result))
    if warmup is not None:
        warmed = generate(warmup, name + "-prefix-warmup")
        if not warmed["success"]:
            raise RuntimeError("Shared-prefix warm-up failed: {}".format(warmed["error"]))

    start = time.perf_counter()
    with ThreadPoolExecutor(max_workers=CONCURRENCY) as pool:
        records = list(pool.map(lambda item: generate(item[1], "{}-{:02d}".format(name, item[0])), enumerate(inputs)))
    elapsed = time.perf_counter() - start
    destination = RESULTS / name
    destination.mkdir(parents=True, exist_ok=True)
    with (destination / "requests.jsonl").open("w", encoding="utf-8") as output:
        for record in records:
            output.write(json.dumps(record, ensure_ascii=False) + "\n")
    summary = summarize(name, records, elapsed)
    write_json(destination / "summary.json", summary)
    return summary


def main() -> None:
    workloads, warmup = make_workloads()
    write_json(RESULTS / "experiment_config.json", {
        "model": MODEL,
        "client": "Windows Python standard library, HTTP proxy disabled",
        "base_url": BASE_URL,
        "seed": SEED,
        "requests_per_group": REQUEST_COUNT,
        "max_concurrency": CONCURRENCY,
        "shared_prefix_tokens": PREFIX_LENGTH,
        "independent_suffix_tokens": SUFFIX_LENGTH,
        "prompt_tokens": PROMPT_LENGTH,
        "temperature": 0,
        "max_new_tokens": OUTPUT_LENGTH,
        "ignore_eos": True,
        "sampling_seed": SEED,
    })
    for name, inputs in workloads.items():
        destination = INPUTS / name
        destination.mkdir(parents=True, exist_ok=True)
        with (destination / "input_ids.jsonl").open("w", encoding="utf-8") as output:
            for index, ids in enumerate(inputs):
                output.write(json.dumps({"request_id": "{}-{:02d}".format(name, index), "input_ids": ids}) + "\n")
    write_json(INPUTS / "shared_prefix" / "warmup_input_ids.json", warmup)
    short = generate([100, 101, 102, 103], "service-warmup")
    if not short["success"]:
        raise RuntimeError("Short service warm-up failed: {}".format(short["error"]))
    for name in ("shared_prefix", "dispersed_prefix"):
        summary = run_group(name, workloads[name], warmup if name == "shared_prefix" else None)
        print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
