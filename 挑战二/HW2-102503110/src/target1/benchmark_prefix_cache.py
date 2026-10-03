"""Run the two SGLang v0.5.14 prefix-cache workloads from challenge 2."""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import time
from pathlib import Path
from typing import Any

import aiohttp
from transformers import AutoTokenizer


MODEL = "Qwen/Qwen3-0.6B"
SEED = 2026
REQUESTS_PER_GROUP = 32
CONCURRENCY = 8
PREFIX_TOKENS = 2048
SUFFIX_TOKENS = 64
PROMPT_TOKENS = PREFIX_TOKENS + SUFFIX_TOKENS
OUTPUT_TOKENS = 16


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def make_workloads(model: str) -> tuple[dict[str, list[list[int]]], list[int]]:
    tokenizer = AutoTokenizer.from_pretrained(model, trust_remote_code=False)
    special = set(tokenizer.all_special_ids)
    valid_ids = [i for i in range(tokenizer.vocab_size) if i not in special]
    if len(valid_ids) < REQUESTS_PER_GROUP + 1:
        raise RuntimeError("Tokenizer has too few ordinary token IDs")

    rng = random.Random(SEED)
    first_tokens = rng.sample(valid_ids, REQUESTS_PER_GROUP)
    shared_prefix = rng.choices(valid_ids, k=PREFIX_TOKENS)
    suffixes = [rng.choices(valid_ids, k=SUFFIX_TOKENS) for _ in range(REQUESTS_PER_GROUP)]
    shared = [shared_prefix + suffix for suffix in suffixes]
    dispersed = [
        [first_tokens[i]] + rng.choices(valid_ids, k=PREFIX_TOKENS - 1) + suffixes[i]
        for i in range(REQUESTS_PER_GROUP)
    ]
    warmup_suffix = rng.choices(valid_ids, k=SUFFIX_TOKENS)
    warmup = shared_prefix + warmup_suffix
    assert all(len(ids) == PROMPT_TOKENS for ids in shared + dispersed)
    assert len({ids[0] for ids in dispersed}) == REQUESTS_PER_GROUP
    assert all(ids[:PREFIX_TOKENS] == shared_prefix for ids in shared)
    return {"shared_prefix": shared, "dispersed_prefix": dispersed}, warmup


def payload(input_ids: list[int]) -> dict[str, Any]:
    return {
        "input_ids": input_ids,
        "stream": True,
        "sampling_params": {
            "temperature": 0,
            "max_new_tokens": OUTPUT_TOKENS,
            "ignore_eos": True,
            "sampling_seed": SEED,
        },
    }


async def generate(
    session: aiohttp.ClientSession, base_url: str, input_ids: list[int], request_id: str
) -> dict[str, Any]:
    start = time.perf_counter()
    first_token_at: float | None = None
    last_token_at: float | None = None
    observed_tokens = 0
    events: list[dict[str, Any]] = []
    status: int | None = None
    error: str | None = None
    last_meta: dict[str, Any] = {}
    try:
        async with session.post(f"{base_url}/generate", json=payload(input_ids)) as response:
            status = response.status
            async for raw_line in response.content:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line or not line.startswith("data:"):
                    continue
                value = line[5:].strip()
                if value == "[DONE]":
                    continue
                event = json.loads(value)
                if not isinstance(event, dict):
                    raise ValueError(f"Unexpected stream event: {value[:200]}")
                events.append(event)
                meta = event.get("meta_info") or {}
                if isinstance(meta, dict):
                    last_meta = meta
                    count = meta.get("completion_tokens", 0)
                    if isinstance(count, int) and count > observed_tokens:
                        arrival = time.perf_counter()
                        if first_token_at is None:
                            first_token_at = arrival
                        last_token_at = arrival
                        observed_tokens = count
            if status != 200:
                error = f"HTTP {status}: {events[-1] if events else 'no SSE data'}"
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError, json.JSONDecodeError) as exc:
        error = str(exc)
    end = time.perf_counter()

    prompt_count = last_meta.get("prompt_tokens")
    completion_count = last_meta.get("completion_tokens")
    cached_count = last_meta.get("cached_tokens")
    ttft_ms = (first_token_at - start) * 1000 if first_token_at is not None else None
    e2e_ms = (end - start) * 1000
    tpot_ms = (
        (last_token_at - first_token_at) * 1000 / (completion_count - 1)
        if first_token_at is not None and last_token_at is not None
        and isinstance(completion_count, int) and completion_count > 1
        else None
    )
    success = (
        error is None
        and status == 200
        and prompt_count == len(input_ids)
        and completion_count == OUTPUT_TOKENS
        and first_token_at is not None
    )
    return {
        "request_id": request_id,
        "status": status,
        "success": success,
        "input_tokens": len(input_ids),
        "prompt_tokens": prompt_count,
        "completion_tokens": completion_count,
        "cached_tokens": cached_count,
        "actual_prefill_tokens": (
            prompt_count - cached_count
            if isinstance(prompt_count, int) and isinstance(cached_count, int)
            else None
        ),
        "ttft_ms": ttft_ms,
        "tpot_ms": tpot_ms,
        "e2e_ms": e2e_ms,
        "meta_info": last_meta,
        "stream_events": events,
        "error": error or (None if success else "Missing or mismatched token counts in final SSE metadata"),
    }


async def flush_cache(session: aiohttp.ClientSession, base_url: str) -> None:
    async with session.post(f"{base_url}/flush_cache") as response:
        body = await response.text()
        if response.status != 200:
            raise RuntimeError(f"/flush_cache returned HTTP {response.status}: {body[:500]}")
        try:
            result = json.loads(body)
        except json.JSONDecodeError:
            result = body
        if isinstance(result, dict) and (result.get("success") is False or result.get("error")):
            raise RuntimeError(f"/flush_cache did not succeed: {result}")


def summarize(name: str, records: list[dict[str, Any]], elapsed_s: float) -> dict[str, Any]:
    good = [record for record in records if record["success"]]
    cache_known = bool(good) and all(isinstance(record["cached_tokens"], int) for record in good)

    def latency(field: str, fraction: float) -> float | None:
        values = [record[field] for record in good if record[field] is not None]
        return percentile(values, fraction) if values else None

    total_prompt = sum(record["prompt_tokens"] for record in good)
    total_cached = sum(record["cached_tokens"] for record in good) if cache_known else None
    return {
        "group": name,
        "requests": len(records),
        "successful_requests": len(good),
        "success_rate": len(good) / len(records),
        "wall_time_s": elapsed_s,
        "throughput_requests_per_s": len(good) / elapsed_s,
        "throughput_output_tokens_per_s": sum(record["completion_tokens"] for record in good) / elapsed_s,
        "prompt_tokens_total": total_prompt,
        "cached_tokens_total": total_cached,
        "cache_hit_rate": total_cached / total_prompt if total_cached is not None and total_prompt else None,
        "actual_prefill_tokens_total": total_prompt - total_cached if total_cached is not None else None,
        "ttft_ms_p50": latency("ttft_ms", 0.50),
        "ttft_ms_p95": latency("ttft_ms", 0.95),
        "tpot_ms_p50": latency("tpot_ms", 0.50),
        "tpot_ms_p95": latency("tpot_ms", 0.95),
        "e2e_ms_p50": latency("e2e_ms", 0.50),
        "e2e_ms_p95": latency("e2e_ms", 0.95),
        "cache_metrics_available": cache_known,
    }


async def run_group(
    session: aiohttp.ClientSession,
    base_url: str,
    name: str,
    inputs: list[list[int]],
    warmup: list[int] | None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    # The previous group is fully awaited before this function is called.
    await flush_cache(session, base_url)
    if warmup is not None:
        result = await generate(session, base_url, warmup, f"{name}-prefix-warmup")
        if not result["success"]:
            raise RuntimeError(f"Shared-prefix warm-up failed: {result['error']}")

    semaphore = asyncio.Semaphore(CONCURRENCY)

    async def one(index: int) -> dict[str, Any]:
        async with semaphore:
            return await generate(session, base_url, inputs[index], f"{name}-{index:02d}")

    start = time.perf_counter()
    records = await asyncio.gather(*(one(index) for index in range(REQUESTS_PER_GROUP)))
    elapsed_s = time.perf_counter() - start
    return records, summarize(name, records, elapsed_s)


async def main(args: argparse.Namespace) -> None:
    root = Path(args.output_dir)
    results_dir = root / "results" / "target1"
    workload_dir = root / "src" / "target1" / "inputs"
    results_dir.mkdir(parents=True, exist_ok=True)
    workloads, warmup = make_workloads(args.model)
    config = {
        "model": args.model,
        "base_url": args.base_url,
        "seed": SEED,
        "requests_per_group": REQUESTS_PER_GROUP,
        "max_concurrency": CONCURRENCY,
        "shared_prefix_tokens": PREFIX_TOKENS,
        "independent_suffix_tokens": SUFFIX_TOKENS,
        "prompt_tokens": PROMPT_TOKENS,
        "temperature": 0,
        "max_new_tokens": OUTPUT_TOKENS,
        "ignore_eos": True,
        "sampling_seed": SEED,
    }
    (results_dir / "experiment_config.json").write_text(
        json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    for name, inputs in workloads.items():
        destination = workload_dir / name
        destination.mkdir(parents=True, exist_ok=True)
        with (destination / "input_ids.jsonl").open("w", encoding="utf-8") as handle:
            for index, ids in enumerate(inputs):
                handle.write(json.dumps({"request_id": f"{name}-{index:02d}", "input_ids": ids}) + "\n")
    (workload_dir / "shared_prefix" / "warmup_input_ids.json").write_text(
        json.dumps(warmup), encoding="utf-8"
    )

    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=args.timeout)) as session:
        short = await generate(session, args.base_url, [warmup[0], warmup[1]], "service-warmup")
        if not short["success"]:
            raise RuntimeError(f"Short service warm-up failed: {short['error']}")
        for name in ("shared_prefix", "dispersed_prefix"):
            records, summary = await run_group(
                session,
                args.base_url,
                name,
                workloads[name],
                warmup if name == "shared_prefix" else None,
            )
            destination = results_dir / name
            destination.mkdir(parents=True, exist_ok=True)
            with (destination / "requests.jsonl").open("w", encoding="utf-8") as handle:
                for record in records:
                    handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            (destination / "summary.json").write_text(
                json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            print(json.dumps(summary, ensure_ascii=False, indent=2))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:30000")
    parser.add_argument("--model", default=MODEL)
    parser.add_argument("--output-dir", default=".")
    parser.add_argument("--timeout", type=float, default=300)
    return parser.parse_args()


if __name__ == "__main__":
    asyncio.run(main(parse_args()))
