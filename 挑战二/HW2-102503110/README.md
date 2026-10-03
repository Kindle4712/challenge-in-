# 第二次挑战（HW2-102503110）

> `src/docs/` 保留两份可编辑 Markdown，根目录放置对应的交付 PDF。

## 环境

| 项目 | 要求 / 当前确认值 |
|---|---|
| GPU | NVIDIA GeForce RTX 5060，8151 MiB 显存（来自 `nvidia-smi`） |
| 系统 | Ubuntu 22.04，WSL 2 |
| Python | 服务端使用 `sglang310` Conda 环境（Python 3.10）；本次测量客户端为 Windows Python 3.11.9 |
| SGLang | 0.5.14（已确认） |
| Ray | 2.56.0（已确认） |
| 模型 | `Qwen/Qwen3-0.6B` |

本机实验依赖已安装在 `/home/kindl/conda-envs/sglang310`。在新的 Ubuntu/WSL 环境中可按以下命令安装固定版本：

```bash
conda create -n sglang310 python=3.10 -y
conda activate sglang310
python -m pip install 'sglang[all]==0.5.14' 'ray==2.56.0' aiohttp transformers
```

请先用 `python -c 'import sglang, ray; print(sglang.__version__, ray.__version__)'` 确认实际版本，并记录 `nvidia-smi` 输出。Windows 下的 `.venv311` 与此 Linux 实验环境无关。

## 启动服务

在 Ubuntu 终端进入挑战二目录：

```bash
cd '/mnt/c/Users/kindl/Desktop/训练营/挑战二/HW2-102503110'
conda activate sglang310
python -m sglang.launch_server \
  --model-path /home/kindl/models/Qwen3-0.6B \
  --host 127.0.0.1 \
  --port 30000 \
  --mem-fraction-static 0.65 \
  --attention-backend triton \
  --cuda-graph-backend-prefill disabled
```

保持 Radix Cache 开启，不加 `--disable-radix-cache`。本机 WSL 中没有 CUDA Toolkit 的 `nvcc`，FlashInfer Prefill CUDA Graph 初始化会失败，因此使用 Triton 后端并关闭 Prefill CUDA Graph；两组实验在同一个服务进程中运行，配置完全一致。等待服务输出就绪后再执行实验。若模型文件尚未存在，需先取得 `Qwen/Qwen3-0.6B` 的本地副本。

## 回放实验

保持上述 WSL 服务终端运行，在另一个 **Windows PowerShell** 终端执行本次正式测量所用客户端：

```powershell
cd 'C:\Users\kindl\Desktop\训练营\挑战二\HW2-102503110'
python src/target1/benchmark_prefix_cache_windows.py
python src/target1/validate_results.py
```

重新运行会覆盖当前目录内的输入和结果文件，需保留原始结果时先复制整个 `HW2-102503110` 目录。本客户端使用 Python 标准库，不需要在 Windows 安装 SGLang；它绕过本机 HTTP 代理，通过本地端口访问 WSL 服务。`src/target1/benchmark_prefix_cache.py` 是依赖 `aiohttp` 和 `transformers` 的 Linux 备用实现，生成同配置但不同随机输入序列，不用于复现本报告的逐请求原始数据。

正式客户端固定使用原生流式 `/generate` + `input_ids`，每组 32 条测量请求，最大并发 8。请求参数为 `temperature=0`、`max_new_tokens=16`、`ignore_eos=true`、`sampling_seed=2026`。先发短请求预热服务；每组开始前等待上一组全部结束并调用 `POST /flush_cache`；共享组另发一条包含 2048 token 公共前缀的预热请求，预热不计入结果。

共享组的测量输入是 2048 token 公共前缀加 64 token 独立后缀。分散组各有 2112 token，且 32 条请求的首 token 均不同。两组按相同编号顺序发送，输出均要求 16 token。

## 文件与报告对应关系

| 路径 | 用途 |
|---|---|
| `src/target1/benchmark_prefix_cache_windows.py` | 本次正式测量与回放所用 Windows 标准库客户端 |
| `src/target1/benchmark_prefix_cache.py` | Linux 备用客户端，按同配置生成另一组输入 |
| `src/locate_sglang_flow.py` | 扫描已安装 v0.5.14 源码，记录关键符号文件与行号 |
| `src/draw_flow.py`、`src/figures/request_flow.png` | 可复现的请求主流程图及报告插图 |
| `src/target1/validate_results.py` | 根据逐请求原始文件检查两组 32/32 成功、长度、指标汇总及缓存差异 |
| `src/render_pdfs.js` | 从两份 Markdown 生成对应的 PDF（Windows Edge、Node.js、`marked` 与 `playwright`） |
| `src/target1/inputs/shared_prefix/input_ids.jsonl` | 共享组 32 条原始输入 |
| `src/target1/inputs/shared_prefix/warmup_input_ids.json` | 不计入测量的共享前缀预热输入 |
| `src/target1/inputs/dispersed_prefix/input_ids.jsonl` | 分散组 32 条原始输入 |
| `results/target1/experiment_config.json` | 固定实验配置 |
| `results/target1/shared_prefix/requests.jsonl` | 共享组逐请求指标与原始 SSE 事件 |
| `results/target1/shared_prefix/summary.json` | 报告表格的共享组列 |
| `results/target1/dispersed_prefix/requests.jsonl` | 分散组逐请求指标与原始 SSE 事件 |
| `results/target1/dispersed_prefix/summary.json` | 报告表格的分散组列 |
| `src/docs/report.md` | 报告可编辑源文件，结果表与上述 JSON 对应 |

缓存命中率严格按 `sum(cached_tokens) / sum(prompt_tokens)` 计算；实际 Prefill token 数严格按 `sum(prompt_tokens - cached_tokens)` 计算。若服务不提供 `cached_tokens`，脚本将其留空，不会伪造数据。TTFT 从发送请求到收到首个输出 token；TPOT 按首 token 后的生成耗时除以剩余输出 token 数；端到端延迟从请求发送到流结束。p50/p95 使用线性插值分位数。

## 验收

两组 `summary.json` 应分别满足 `successful_requests == 32`、`cache_metrics_available == true`；每条记录的 `prompt_tokens == 2112`、`completion_tokens == 16`。共享组应有更高的 `cache_hit_rate` 和更低的 `actual_prefill_tokens_total`。未达到条件时保留原始结果并排查，不应修改数据。

本次正式结果由 Windows 侧标准库客户端产生；请求计时包含 Windows 到 WSL 的本地转发耗时，报告已注明。原始结果只包含一轮正式对照，没有 `run-2/`。

任务二源码位置在同一环境下采集：

```bash
python src/locate_sglang_flow.py
```

脚本生成 `results/target2/source_locations.json`。本报告已使用官方 `v0.5.14` 标签源码核对调用关系；同名符号可能有多个定义，不能只凭名称选一个。

## 交付

修改 `src/docs/report.md` 和 `src/docs/AI 使用说明情况（第二次挑战）.md` 后，可重新导出对应 PDF。Windows 中安装 Node.js、`marked`、`playwright` 后运行 `node src/render_pdfs.js`（需本机 Microsoft Edge）；也可用 Word/WPS 从 Markdown 导出。当前报告正文为 4 页，任务二的流程图和说明位于第 2、3 页。最终 ZIP 解压后最外层只有同名 `HW2-102503110/` 目录。
