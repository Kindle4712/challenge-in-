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

## 仍缺少的实验方法证据

归档未找到对应的采样或回放 Python/Shell 脚本；归档内的 build_literature_notes.py 仅用于文档生成。结果没有计划/实际发送时间，也没有 Poisson 到达率和随机种子，无法验证 Poisson 请求到达过程；trace 自带 timestamp 不能替代回放的到达记录。

没有 prompt 构造、tokenizer 或截断代码，无法确认长度如何统一为 3000，以及服务计数为何为 3008。不能将观察到的固定长度描述为已验证的截断规则。原始 JSONL 缺失的问题已补齐，但采样、回放和长度转换的可复现性仍有限；如找回 shell 历史或脚本，应再核验后补充。

截图恢复来源：挑战一/截图操作保存/截图2Mooncake负载测试.png。完整备份仅用于本地溯源，含重复仓库、.git 和文档缓存，不应将整个备份直接作为提交材料；提交用原始证据采用本目录精选文件。
