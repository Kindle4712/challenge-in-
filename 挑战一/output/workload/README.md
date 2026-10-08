# Mooncake 工作负载原始数据与核验

2026-10-08 从用户提供的 Linux 目录 ~/llm-challenge 备份 challenge1-original-evidence.tar.gz 找回原始文件。original/ 中的文件从归档直接读取并按原字节保存；SHA256 和核验结果见 原始数据核验.json。

## 文件说明

- original/mooncake_trace.jsonl：23608 条 trace 记录，包含 timestamp、input_length、output_length、hash_ids；归档未包含下载命令、来源 URL 或版本，无法仅据此确认具体 trace 子集。
- original/mooncake_workload_results_retry.jsonl：10 条重试成功记录，作为该轮主要原始结果。
- original/mooncake_workload_results.jsonl：10 条 HTTP 400 失败记录，保留失败证据，不与成功重试混合统计。
- original/workload_results.jsonl：另一次 10 条成功请求记录，不作为 Mooncake 重试轮结果。
- 本目录 mooncake_workload_results_retry.jsonl：此前从终端截图恢复的版本，保留恢复来源；与找回的原始重试文件在全部 10 条记录、全部字段上相同。两文件序列化格式不同，字节校验值不必相同。

## 已确认的观察

重试轮的输入/输出 trace 长度对与 trace 前 10 条顺序一致；这说明数据对应关系，但不证明具体采样算法。10 条请求均标注 actual_prompt_tokens=3000，服务返回 prompt_tokens=3008，completion_tokens=32。3008 与 3000 的差值来源无法确认。trace_output_length 未被原样作为实际输出长度。

## 从命令历史找回的方法

2026-10-08 用户复制了 Linux shell 历史。已从历史条目 232–283 原样提取 replay_mooncake_history.py，完整 Python 语法解析通过，未重新运行。相关命令摘录见 original/相关命令历史.txt；历史只证明命令被记录，不能单独证明每次执行成功。脚本字段、前 10 条长度对及结果文件名与找回的重试结果一致。

trace 下载命令指向 Mooncake 仓库 FAST25-release/arxiv-trace/mooncake_trace.jsonl；另有使用 gh-proxy.com 下载同一目标 URL 的记录。未记录上游 commit，当前归档字节由 SHA256 固定。

采样是读取非空 JSONL 后取前 10 条，不是随机采样。每个请求都使用“请分析下面的安全测试文本并给出简短结论。\n”加“安全测试文本。”重复 5000 次；用本地 Qwen3-0.6B tokenizer，add_special_tokens=False 编码，截取前 3000 个 ID，再 decode 为 user 消息。因此 trace_input_length 仅记录原长度，不用于构造该重试轮输入。输出上限为 min(max(trace_output_length, 8), 32)。

代码同步调用 /v1/chat/completions，等待响应后才执行 time.sleep(random.expovariate(2.0))。指数等待间隔的均值为 0.5 秒，但真实发送间隔还包含上一请求处理时长；这是串行闭环回放，不是独立 Poisson 请求到达过程。未设置随机种子，未保存计划/实际发送时间，不能重建原到达序列，不能将该轮标为已满足 Poisson 到达要求。

服务计数 3008 与客户端编码长度 3000 的差值，可能涉及 chat template、特殊 token 或 decode 后重新编码；历史没有保存服务模板、tokenizer 版本和最终请求 token ID，仍不能确定额外 8 个 token 的来源。

## 还原脚本使用与限制

脚本保留历史行为，会覆盖当前目录同名结果；仅在新目录运行，先复制 trace，且需本地模型 ~/models/Qwen3-0.6B、transformers 和正在服务的后端。不要在 original/ 或历史结果目录执行。此次提取未启动模型、未发送请求，不能作为新实验结果，也没有修正旧轮次的 Poisson 方法问题。

截图恢复来源：挑战一/截图操作保存/截图2Mooncake负载测试.png。完整备份和完整 shell 历史仅作本地溯源；提交精选原始文件和相关命令摘录，避免包含重复 .git、缓存或不相关历史。
