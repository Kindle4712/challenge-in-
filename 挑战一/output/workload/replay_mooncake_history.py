# Restored from shell history entries 232-283; original behavior preserved.
# WARNING: overwrites mooncake_workload_results_retry.jsonl in the working directory.
# Run only in a separate directory with a COPY of mooncake_trace.jsonl.
import json, random, time, urllib.request, urllib.error
from transformers import AutoTokenizer
model_path = f"{__import__('os').path.expanduser('~')}/models/Qwen3-0.6B"
tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=False)
url = "http://127.0.0.1:30000/v1/chat/completions"
result_file = "mooncake_workload_results_retry.jsonl"
with open("mooncake_trace.jsonl", encoding="utf-8") as f:
    traces = [json.loads(line) for line in f if line.strip()][:10]
with open(result_file, "w", encoding="utf-8") as out:
    for request_id, item in enumerate(traces, 1):
        original_input = int(item["input_length"])
        original_output = int(item["output_length"])
        text = "请分析下面的安全测试文本并给出简短结论。\n" + "安全测试文本。" * 5000
        token_ids = tokenizer.encode(text, add_special_tokens=False)[:3000]
        prompt = tokenizer.decode(token_ids)
        output_limit = min(max(original_output, 8), 32)
        payload = {
            "model": "Qwen/Qwen3-0.6B",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": output_limit,
        }
        start = time.time()
        record = {
            "request_id": request_id,
            "trace_input_length": original_input,
            "trace_output_length": original_output,
            "actual_prompt_tokens": len(token_ids),
            "max_output_tokens": output_limit,
        }
        try:
            req = urllib.request.Request(
                url, data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"}, method="POST"
            )
            with urllib.request.urlopen(req, timeout=120) as response:
                data = json.loads(response.read().decode())
            record["status"] = "ok"
            record["prompt_tokens"] = data.get("usage", {}).get("prompt_tokens")
            record["completion_tokens"] = data.get("usage", {}).get("completion_tokens")
        except urllib.error.HTTPError as e:
            record["status"] = "error"
            record["http_status"] = e.code
            record["error_detail"] = e.read().decode("utf-8", errors="replace")[:1000]
        except Exception as e:
            record["status"] = "error"
            record["error_detail"] = str(e)
        record["latency_seconds"] = round(time.time() - start, 3)
        out.write(json.dumps(record, ensure_ascii=False) + "\n")
        out.flush()
        print(json.dumps(record, ensure_ascii=False))
        time.sleep(random.expovariate(2.0))
print(f"结果已保存到: {result_file}")
