"""Open-loop Poisson replay. Historical results are never overwritten."""
import argparse
import concurrent.futures
import hashlib
import json
import math
import random
import time
import urllib.request
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--trace', required=True)
    parser.add_argument('--model-path', required=True)
    parser.add_argument('--url', default='http://127.0.0.1:30000')
    parser.add_argument('--out', required=True)
    parser.add_argument('--count', type=int, default=10)
    parser.add_argument('--rate', type=float, default=0.5)
    parser.add_argument('--seed', type=int, default=20261008)
    parser.add_argument('--context-length', type=int, default=4096)
    parser.add_argument('--input-budget', type=int, default=3000)
    parser.add_argument('--output-budget', type=int, default=512)
    args = parser.parse_args()
    if not 10 <= args.count <= 30 or not math.isfinite(args.rate) or args.rate <= 0:
        parser.error('count must be 10-30; rate must be finite and positive')
    if min(args.input_budget, args.output_budget) < 1:
        parser.error('token budgets must be positive')
    from transformers import AutoTokenizer
    import importlib.metadata
    tok = AutoTokenizer.from_pretrained(args.model_path, trust_remote_code=False)
    trace = [json.loads(x) for x in Path(args.trace).read_text(encoding='utf-8').splitlines() if x.strip()]
    if len(trace) < args.count:
        parser.error('not enough trace records')
    rng = random.Random(args.seed)
    eligible = [i for i, x in enumerate(trace)
                if 1 <= int(x['input_length']) <= args.input_budget
                and 1 <= int(x['output_length']) <= args.output_budget]
    if len(eligible) < args.count:
        parser.error('not enough records within context budgets')
    indices = sorted(rng.sample(eligible, args.count))
    chosen = [trace[i] for i in indices]
    if any(int(x['input_length']) < 1 or int(x['output_length']) < 1 for x in chosen):
        parser.error('trace lengths must be positive')
    input_scale = output_scale = 1.0
    tasks = []
    arrival = 0.0
    for rid, (idx, row) in enumerate(zip(indices, chosen), 1):
        target = max(1, math.floor(int(row['input_length']) * input_scale))
        output = max(1, math.floor(int(row['output_length']) * output_scale))
        # Measure final text after decode/re-encode; never assume the length survives decoding.
        text = '安全测试文本。' * (target + 1)
        prompt = tok.decode(tok.encode(text, add_special_tokens=False)[:target])
        client_tokens = len(tok.encode(prompt, add_special_tokens=False))
        if client_tokens != target:
            parser.error('synthetic input does not round-trip to requested token length')
        messages = [{'role': 'user', 'content': prompt}]
        templated = tok.apply_chat_template(messages, tokenize=True, add_generation_prompt=True)
        template_tokens = len(templated['input_ids']) if isinstance(templated, dict) or hasattr(templated, 'keys') else len(templated)
        if template_tokens + output > args.context_length:
            parser.error('chat-template input plus output exceeds configured context length')
        arrival += rng.expovariate(args.rate)
        tasks.append(dict(request_id=rid, trace_index=idx,
                          trace_input_length=int(row['input_length']), trace_output_length=int(row['output_length']),
                          target_input_tokens=target, client_input_tokens=client_tokens,
                          client_chat_template_tokens=template_tokens, max_output_tokens=output,
                          planned_send_seconds=arrival, messages=messages))
    with urllib.request.urlopen(args.url.rstrip('/') + '/v1/models', timeout=10) as response:
        models = json.load(response)
    ids = [x['id'] for x in models.get('data', [])]
    model = 'Qwen/Qwen3-0.6B' if 'Qwen/Qwen3-0.6B' in ids else str(args.model_path)
    if model not in ids:
        parser.error('required model is not exposed by /v1/models')
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=False)
    config = vars(args) | dict(trace_sha256=hashlib.sha256(Path(args.trace).read_bytes()).hexdigest(),
                               sampled_indices=indices, input_scale=input_scale, output_scale=output_scale,
                               eligible_records=len(eligible), sampling='seeded random sample within declared length budgets; lengths unchanged',
                               models_response=models, model=model,
                               versions={p: importlib.metadata.version(p) for p in ['transformers']},
                               arrival_process='independent cumulative exponential intervals; open loop',
                               results_status='planned; no experimental conclusion yet')
    (out / 'config.json').write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding='utf-8')
    (out / 'plan.json').write_text(json.dumps(tasks, ensure_ascii=False, indent=2), encoding='utf-8')
    origin = time.perf_counter()

    def send(task):
        payload = dict(model=model, messages=task['messages'], max_tokens=task['max_output_tokens'], stream=False)
        request = urllib.request.Request(args.url.rstrip('/') + '/v1/chat/completions',
                                         data=json.dumps(payload).encode(),
                                         headers={'Content-Type': 'application/json'})
        record = {k: v for k, v in task.items() if k != 'messages'}
        start = time.perf_counter()
        record['actual_send_seconds'] = start - origin
        record['dispatch_lateness_seconds'] = start - origin - task['planned_send_seconds']
        try:
            with urllib.request.urlopen(request, timeout=300) as response:
                body = json.load(response)
                record['http_status'] = response.status
            usage = body.get('usage', {})
            record.update(status='ok', prompt_tokens=usage.get('prompt_tokens'),
                          completion_tokens=usage.get('completion_tokens'),
                          finish_reason=body.get('choices', [{}])[0].get('finish_reason'))
        except Exception as exc:
            record.update(status='error', error=str(exc))
            if hasattr(exc, 'read'):
                record['error_detail'] = exc.read().decode(errors='replace')[:2000]
            if hasattr(exc, 'code'):
                record['http_status'] = exc.code
        record['latency_seconds'] = time.perf_counter() - start
        record['complete_seconds'] = time.perf_counter() - origin
        return record

    futures = []
    # One available worker per request prevents response times from controlling dispatch.
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.count) as pool:
        for task in tasks:
            delay = origin + task['planned_send_seconds'] - time.perf_counter()
            if delay > 0:
                time.sleep(delay)
            futures.append(pool.submit(send, task))
        with (out / 'results.jsonl').open('w', encoding='utf-8') as f:
            for future in concurrent.futures.as_completed(futures):
                record = future.result()
                f.write(json.dumps(record, ensure_ascii=False) + '\n')
                f.flush()
                print(json.dumps(record, ensure_ascii=False), flush=True)
    records = [json.loads(x) for x in (out / 'results.jsonl').read_text(encoding='utf-8').splitlines()]
    ok = [x for x in records if x['status'] == 'ok']
    summary = dict(count=len(records), successes=len(ok), errors=len(records)-len(ok),
                   mean_success_latency_seconds=sum(x['latency_seconds'] for x in ok)/len(ok) if ok else None,
                   max_dispatch_lateness_seconds=max(x['dispatch_lateness_seconds'] for x in records),
                   successful_token_counts_present=bool(ok) and all(isinstance(x['prompt_tokens'], int) and isinstance(x['completion_tokens'], int) for x in ok),
                   note='length-filtered synthetic workload, original lengths retained; no cache-performance or TTFT conclusion')
    (out / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    config['results_status'] = 'completed; see results.jsonl and summary.json'
    (out / 'config.json').write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
