"""Experiment 7: replay mode, tested in a SCRATCH pipeline copy (a second copy, patched with the proposed flag changes).
 1. live/replay.py builds replay_raw.json (12 held-out historical records, replay=true) and a replay receipt.
 2. A copy of the scratch pipeline gets the PROPOSED small patch (data/proposal_replay_flags.patch.txt): ingest keeps replay, kind,
    discovered_at; origin becomes 'replay'; new_since_dataset is false for replay; export gets a separate 'replay' list.
 3. Ingest + export run on the replay file. We check that the flag survives every stage and that replay never lands in 'live'.
Run exp6 first (it builds pipeline_scratch). Run: python -X utf8 exp7_replay.py -> logs/exp7_replay.log
"""
import glob, json, os, re, shutil, subprocess, sys
from exp_common import Tee, LIVE, HERE, ROOT

out = Tee('exp7_replay.log')
S0 = os.path.join(HERE, 'pipeline_scratch')
S = os.path.join(HERE, 'pipeline_scratch_replay')
OD = os.path.join(HERE, 'out_replay')
assert os.path.exists(S0), 'run exp6_end_to_end.py first'

r = subprocess.run([sys.executable, '-X', 'utf8', os.path.join(LIVE, 'replay.py'), '--out-dir', OD], capture_output=True, text=True, encoding='utf-8')
out(r.stdout.strip())
recs = json.load(open(os.path.join(OD, 'replay_raw.json'), encoding='utf-8'))
out(f'replay_raw.json: {len(recs)} records; all replay=true: {all(x["replay"] for x in recs)}; ids start with replay: {all(x["mention_id"].startswith("replay:") for x in recs)}; '
    f'published false: {all(x["published"] is False for x in recs)}')

if os.path.exists(S):
    shutil.rmtree(S)
shutil.copytree(S0, S, ignore=shutil.ignore_patterns('data', '__pycache__', 'inputs'))
os.makedirs(os.path.join(S, 'inputs'))
shutil.copy(os.path.join(OD, 'replay_raw.json'), os.path.join(S, 'inputs', 'replay_raw.json'))
cfg = open(os.path.join(S, 'config.toml'), encoding='utf-8').read()
cfg = re.sub(r'^raw_json\s*=.*$', 'raw_json  = "' + S.replace(os.sep, '/') + '/inputs/replay_raw.json"', cfg, flags=re.M)
open(os.path.join(S, 'config.toml'), 'w', encoding='utf-8').write(cfg)

# ---- the PROPOSED patch, applied to the scratch copy only
patch_log = []


def patch(path, old, new, why):
    t = open(path, encoding='utf-8').read()
    assert old in t, f'patch anchor not found in {path}'
    open(path, 'w', encoding='utf-8').write(t.replace(old, new, 1))
    patch_log.append(f'--- {os.path.relpath(path, S)}  ({why})\n- {old.strip()}\n+ ' + new.strip().replace('\n', '\n+ '))


s01 = os.path.join(S, 'stages', 's01_ingest.py')
patch(s01, "    out['origin'] = origin\n    out['new_since_dataset'] = ts > pd.Timestamp(DATASET_END)\n",
      "    rep = df['replay'].fillna(False).astype(bool) if 'replay' in df.columns else pd.Series(False, index=df.index)\n"
      "    out['replay'] = rep.values\n"
      "    out['origin'] = ['replay' if x else origin for x in rep]\n"
      "    out['new_since_dataset'] = (ts > pd.Timestamp(DATASET_END)) & ~rep\n"
      "    for c in ('kind', 'discovered_at', 'modified_at', 'content_hash'):\n"
      "        out[c] = df[c] if c in df.columns else None\n",
      'keep replay, kind, discovered_at, modified_at, content_hash; origin=replay; replay is never "new"')
s11 = os.path.join(S, 'stages', 's11_export.py')
patch(s11, "    p = os.path.join(EXPORT, 'data.json')\n",
      "    rp = posts[posts.origin == 'replay'].merge(f[['post_id', 'project', 'label_source']], on='post_id', how='left')\n"
      "    out['replay'] = [{'id': r.post_id, 'date': str(r.published_at)[:10], 'source': r.source, 'url': r.url, 'title': r.title,\n"
      "                      'project_hint': nn(r.project), 'replay': True, 'kind': nn(r.kind), 'discovered_at': nn(r.discovered_at)}\n"
      "                     for r in rp.sort_values('published_at').itertuples()]\n"
      "    p = os.path.join(EXPORT, 'data.json')\n",
      'separate "replay" list in data.json, never mixed into "live"')
open(os.path.join(HERE, 'data', 'proposal_replay_flags.patch.txt'), 'w', encoding='utf-8').write('\n\n'.join(patch_log))
out('applied the proposed patch to the scratch copy only (pipeline/ is untouched), see data/proposal_replay_flags.patch.txt')

driver = r'''
import os, sys
import pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from common import DATA, log, write_table
from stages import s01_ingest, s02_candidates, s03_dedup, s04_labels, s11_export
assert os.path.abspath(DATA).startswith(HERE)
posts = s01_ingest.run()
ORIG = sys.argv[1]
orig = pd.read_parquet(os.path.join(ORIG, 'posts.parquet'))
cand = pd.read_parquet(os.path.join(ORIG, 'candidates.parquet'), columns=['post_id'])
rep_orig = set(posts.post_id.str.replace('replay:', '', regex=False))
ds = orig[(orig.origin == 'dataset') & orig.post_id.isin(cand.post_id) & ~orig.post_id.isin(rep_orig)]   # baseline WITHOUT the replayed originals
write_table('posts', pd.concat([ds, posts], ignore_index=True))
log('scratch', f'baseline {len(ds):,} historical posts (the {len(rep_orig)} replayed originals removed) + {len(posts)} replay records')
for t in ('faq', 'faq_matches', 'events', 'peaks', 'placebo', 'metrics', 'metrics_calibration'):
    pq = os.path.join(ORIG, t + '.parquet')
    if os.path.exists(pq):
        write_table(t, pd.read_parquet(pq))
s02_candidates.run(); s03_dedup.run(); s04_labels.run(); s11_export.run()
'''
open(os.path.join(S, 'run_scratch.py'), 'w', encoding='utf-8').write(driver)
r = subprocess.run([sys.executable, '-X', 'utf8', 'run_scratch.py', os.path.join(ROOT, 'pipeline', 'data', 'parquet')], cwd=S,
                   capture_output=True, text=True, encoding='utf-8')
for ln in (r.stdout + r.stderr).strip().splitlines():
    out(ln)
if r.returncode:
    sys.exit('replay scratch run failed')
import pandas as pd
posts = pd.read_parquet(os.path.join(S, 'data', 'parquet', 'posts.parquet'))
rp = posts[posts.origin == 'replay']
out(f'\nposts table: replay rows={len(rp)}  origin values={posts.origin.value_counts().to_dict()}  new_since_dataset among replay={int(rp.new_since_dataset.sum())} (must be 0)')
exp = json.load(open(os.path.join(S, 'data', 'export', 'data.json'), encoding='utf-8'))
out(f'export: replay list={len(exp["replay"])}  live list={len(exp["live"])} (must be 0)  funnel_live={exp["funnel_live"]}')
out('replay entries in the export (first 4):')
for x in exp['replay'][:4]:
    out('   ' + json.dumps(x, ensure_ascii=False)[:260])
bad = [x for x in exp['posts'] if str(x['id']).startswith('replay:')]
out(f'replay records inside the counted "posts" evidence list: {len(bad)}  (0 expected: they have no label run in the baseline, and the originals were removed)')
ok = len(rp) == len(recs) and int(rp.new_since_dataset.sum()) == 0 and len(exp['live']) == 0 and len(exp['replay']) == len(recs)
out('CHECK replay flag survives ingest and export, never appears as live, never counts as new -> ' + ('PASS' if ok else 'FAIL'))
