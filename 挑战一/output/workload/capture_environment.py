import json
import platform
import subprocess
import importlib.metadata
from pathlib import Path
import urllib.request

out = Path(__file__).parent / 'runs/poisson-20261008-pytorch'
data = {'python': platform.python_version(), 'platform': platform.platform(),
        'packages': {x: importlib.metadata.version(x) for x in ['sglang','ray','torch','transformers']},
        'gpu': subprocess.check_output(['nvidia-smi','--query-gpu=name,memory.total,driver_version','--format=csv,noheader'],text=True).strip(),
        'launch_arguments': '--model-path /home/kindl/models/Qwen3-0.6B --served-model-name Qwen/Qwen3-0.6B --host 127.0.0.1 --port 30000 --context-length 4096 --mem-fraction-static 0.65 --max-running-requests 4 --attention-backend triton --sampling-backend pytorch --cuda-graph-backend-prefill disabled'}
with urllib.request.urlopen('http://127.0.0.1:30000/v1/models') as r:
    data['models_response'] = json.load(r)
payload = {'model':'Qwen/Qwen3-0.6B','messages':[{'role':'user','content':'请用一句话介绍 SGLang。'}],'max_tokens':32,'temperature':0}
req = urllib.request.Request('http://127.0.0.1:30000/v1/chat/completions', data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
with urllib.request.urlopen(req, timeout=60) as r:
    data['single_request_status'] = r.status
    data['single_request_response'] = json.load(r)
(out/'environment.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(data,ensure_ascii=False,indent=2))
