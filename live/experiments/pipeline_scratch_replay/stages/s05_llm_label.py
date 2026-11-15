"""Stage 5: stance, voice and arguments with an LLM and the frozen codebook (teacher labels).

Nothing here runs by default in run_all: it costs money (cloud) or needs a GPU (local).

Commands
  python stages/s05_llm_label.py batches [--project heilbronn_cablecar] [--size 40]
      Writes blind batches (post_id + snippet only, no vendor sentiment, no authors) to data/llm_batches/.
      Same format as the pilot, so the batches can be labelled by any model, including Claude Code agents.
  python stages/s05_llm_label.py prompt
      Prints the exact system prompt (codebook v1 + output rules). Its hash goes into the run header.
  python stages/s05_llm_label.py run --provider openai_compat --base-url http://localhost:8000/v1 --model Qwen/Qwen3.5-9B-Instruct --runs 3
      Local model served by vLLM or Ollama (OpenAI-compatible API). Runs fully offline in the city.
  python stages/s05_llm_label.py run --provider anthropic --model claude-sonnet-5-5 --runs 3
      Cloud teacher. Needs the `anthropic` package and ANTHROPIC_API_KEY (or use Bedrock / Vertex EU, see README).
  python stages/s05_llm_label.py import --run-id 2026-11-15_agents_a --labeller "claude agent" --kind llm_cloud --files data/llm_batches/out_*.jsonl
      Wraps label lines produced elsewhere (pilot style) into a run file with a header.

Multi-run voting: each of the --runs uses a different order of the examples and a different seed.
Stage 4 votes across runs and abstains when there is no majority on stance.
Invalid JSON or values outside the codebook -> abstain=true for that post (never guessed).
"""
import argparse
import glob
import hashlib
import json
import os
import random
import re
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common import ARGS, DATA, PROJECTS, RUNS, STANCES, VOICES, codebook_sha, log, path, read_table  # noqa: E402

BATCHES = os.path.join(DATA, 'llm_batches')
PROMPT_VERSION = 'p1'

OUTPUT_RULES = """
Return exactly one JSON object for the post, nothing else:
{"post_id": "...", "project": "...", "stance": "...", "voice": "...", "arguments": ["..."], "evidence": "..."}
Use only the values from the codebook. If you cannot decide the stance, use "unclear".
"""


def system_prompt():
    cb = open(path('codebook'), encoding='utf-8').read()
    return cb + '\n' + OUTPUT_RULES


def prompt_sha():
    return hashlib.sha256(system_prompt().encode()).hexdigest()[:12]


def todo(project=None):
    c = read_table('candidates')
    f = read_table('labels_final')
    done = set(f[f.label_source.isin(['vote', 'human'])].post_id) if f is not None else set()
    c = c[~c.post_id.isin(done)]
    if project:
        c = c[c.project_hint == project]
    return c


def cmd_batches(a):
    os.makedirs(BATCHES, exist_ok=True)
    c = todo(a.project)
    posts = read_table('posts', columns=['post_id', 'published_at', 'media_type'])
    c = c.merge(posts, on='post_id')
    rows = [{'post_id': r.post_id, 'date': str(r.published_at)[:10], 'media_type': r.media_type, 'text': r.snippet}
            for r in c.itertuples()]
    random.Random(42).shuffle(rows)
    n = 0
    for i in range(0, len(rows), a.size):
        p = os.path.join(BATCHES, f"batch_{a.project or 'all'}_{i // a.size + 1:03d}_blind.jsonl")
        with open(p, 'w', encoding='utf-8') as f:
            for r in rows[i:i + a.size]:
                f.write(json.dumps(r, ensure_ascii=False) + '\n')
        n += 1
    log('llm', f'{len(rows)} unlabelled candidates -> {n} batches in {BATCHES}')


def validate(obj, pid):
    if not isinstance(obj, dict):
        return {'post_id': pid, 'abstain': True}
    ok = obj.get('project') in PROJECTS and obj.get('stance') in STANCES and obj.get('voice') in VOICES
    args = [x for x in (obj.get('arguments') or []) if x in ARGS]
    out = {'post_id': pid, 'project': obj.get('project'), 'stance': obj.get('stance'), 'voice': obj.get('voice'),
           'arguments': args, 'evidence': (obj.get('evidence') or '')[:200], 'abstain': not ok}
    return out


def parse_json(text):
    m = re.search(r'\{.*\}', text or '', re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def call_openai_compat(base_url, model, system, user, seed, api_key=None):
    body = {'model': model, 'temperature': 0, 'seed': seed, 'max_tokens': 400,
            'messages': [{'role': 'system', 'content': system}, {'role': 'user', 'content': user}],
            'response_format': {'type': 'json_object'}}
    req = urllib.request.Request(base_url.rstrip('/') + '/chat/completions', data=json.dumps(body).encode(),
                                 headers={'Content-Type': 'application/json',
                                          **({'Authorization': f'Bearer {api_key}'} if api_key else {})})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())['choices'][0]['message']['content']


def call_anthropic(model, system, user, seed):
    import anthropic  # pip install anthropic; key from ANTHROPIC_API_KEY. For EU: anthropic.AnthropicBedrock / AnthropicVertex
    client = anthropic.Anthropic()
    msg = client.messages.create(model=model, max_tokens=400, temperature=0, system=system,
                                 messages=[{'role': 'user', 'content': user}])
    return msg.content[0].text


def cmd_run(a):
    c = todo(a.project)
    if a.limit:
        c = c.head(a.limit)
    system = system_prompt()
    stamp = time.strftime('%Y-%m-%d')
    for k in range(a.runs):
        run_id = f"{stamp}_{re.sub(r'[^a-z0-9]+', '', a.model.lower())[-20:]}_r{k + 1}_cb1"
        rows = list(c.itertuples())
        random.Random(k).shuffle(rows)  # different order per run
        out = [{'_run': {'run_id': run_id, 'labeller': a.model,
                         'kind': 'llm_local' if a.provider == 'openai_compat' else 'llm_cloud',
                         'runs_where': a.where, 'task': 'all', 'prompt_version': f'{PROMPT_VERSION}:{prompt_sha()}',
                         'codebook_version': 'v1', 'codebook_sha': codebook_sha(),
                         'params': {'temperature': 0, 'seed': k, 'provider': a.provider}}}]
        for i, r in enumerate(rows):
            user = f'post_id: {r.post_id}\ntext: {r.snippet}'
            try:
                if a.provider == 'openai_compat':
                    txt = call_openai_compat(a.base_url, a.model, system, user, seed=k, api_key=os.environ.get('LLM_API_KEY'))
                else:
                    txt = call_anthropic(a.model, system, user, seed=k)
                out.append(validate(parse_json(txt), r.post_id))
            except Exception as e:  # network or server error -> abstain, keep going
                out.append({'post_id': r.post_id, 'abstain': True, 'error': str(e)[:200]})
            if (i + 1) % 50 == 0:
                log('llm', f'{run_id}: {i + 1}/{len(rows)}')
        p = os.path.join(RUNS, f'{run_id}.jsonl')
        with open(p, 'w', encoding='utf-8') as f:
            for o in out:
                f.write(json.dumps(o, ensure_ascii=False) + '\n')
        n_abs = sum(1 for o in out[1:] if o.get('abstain'))
        log('llm', f'wrote {p}: {len(out) - 1} posts, {n_abs} abstained')


def cmd_import(a):
    import pandas as pd
    key = pd.read_csv(os.path.join(path('pilot_dir'), 'sample_key.csv'), encoding='utf-8-sig', dtype=str)
    pid_map = dict(zip(key.pid, key.mention_id))  # pilot files use P001-style ids
    rows = []
    for pat in a.files:
        for p in glob.glob(pat):
            for line in open(p, encoding='utf-8'):
                if line.strip():
                    r = json.loads(line)
                    pid = r.get('post_id') or r.get('pid')
                    rows.append(validate(r, pid_map.get(str(pid), str(pid))))
    header = {'_run': {'run_id': a.run_id, 'labeller': a.labeller, 'kind': a.kind, 'runs_where': a.where,
                       'task': 'all', 'prompt_version': a.prompt_version, 'codebook_version': 'v1',
                       'codebook_sha': codebook_sha(), 'params': {}}}
    p = os.path.join(RUNS, f'{a.run_id}.jsonl')
    with open(p, 'w', encoding='utf-8') as f:
        for o in [header] + rows:
            f.write(json.dumps(o, ensure_ascii=False) + '\n')
    log('llm', f'imported {len(rows)} labels into {p}')


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest='cmd', required=True)
    b = sp.add_parser('batches'); b.add_argument('--project'); b.add_argument('--size', type=int, default=40)
    sp.add_parser('prompt')
    r = sp.add_parser('run')
    r.add_argument('--provider', choices=['openai_compat', 'anthropic'], required=True)
    r.add_argument('--model', required=True)
    r.add_argument('--base-url', default='http://localhost:8000/v1')
    r.add_argument('--runs', type=int, default=3)
    r.add_argument('--project')
    r.add_argument('--limit', type=int)
    r.add_argument('--where', default='local_laptop', help='cloud_eu, cloud_us, local_laptop, local_hamburg, city_server')
    i = sp.add_parser('import')
    i.add_argument('--run-id', required=True); i.add_argument('--labeller', required=True)
    i.add_argument('--kind', default='llm_cloud'); i.add_argument('--where', default='cloud_us')
    i.add_argument('--prompt-version', default='pilot'); i.add_argument('--files', nargs='+', required=True)
    a = ap.parse_args()
    if a.cmd == 'prompt':
        print(system_prompt()); print(f'# prompt sha {prompt_sha()}, codebook sha {codebook_sha()}')
    else:
        {'batches': cmd_batches, 'run': cmd_run, 'import': cmd_import}[a.cmd](a)
