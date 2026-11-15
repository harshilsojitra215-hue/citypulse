"""Experiment 6: end to end, one real item, in a SCRATCH COPY of the team's pipeline. Nothing is written into pipeline/.
Steps:
  1. copy pipeline code (common.py, stages/, reference/, config.toml) to experiments/pipeline_scratch/ ; config points the data dir
     to pipeline_scratch/data and the raw input to a copy of live/out/raw_live.json ; read-only inputs (codebook, pilot, gold) stay in place
  2. stage 1 ingest on the collector export (the real s01_ingest.normalise through its run())
  3. merge with a SUBSET of the historical posts (the 3,3xx rule-net candidates, read-only copy) like s12_live does, so dedup has something to compare with
  4. stages 2 (candidates), 3 (dedup), 4 (labels: vote over existing label files; live items get no LLM label), 11 (export)
  5. report the chosen item at every stage, and what did NOT run
Run: python -X utf8 exp6_end_to_end.py   -> logs/exp6_end_to_end.log
"""
import glob, hashlib, json, os, re, shutil, subprocess, sys
from exp_common import Tee, LIVE, HERE, ROOT

out = Tee('exp6_end_to_end.log')
PIPE = os.path.join(ROOT, 'pipeline')
S = os.path.join(HERE, 'pipeline_scratch')
RAW_SRC = sys.argv[1] if len(sys.argv) > 1 else os.path.join(LIVE, 'out', 'raw_live.json')
PICK = 'Câble C1 : une cavité'


def tree_fingerprint(d):
    """name, size, mtime of every file under pipeline/data: proves we did not write there."""
    h = hashlib.sha1()
    for p in sorted(glob.glob(os.path.join(d, '**', '*'), recursive=True)):
        if os.path.isfile(p):
            st = os.stat(p)
            h.update(f'{os.path.relpath(p, d)}|{st.st_size}|{int(st.st_mtime)}'.encode())
    return h.hexdigest()[:12]


fp_before = tree_fingerprint(os.path.join(PIPE, 'data'))
out(f'fingerprint of pipeline/data before: {fp_before}')

# ---- 1. scratch copy
if os.path.exists(S):
    shutil.rmtree(S)
os.makedirs(S)
for name in ('common.py', 'config.toml', 'requirements.txt'):
    shutil.copy(os.path.join(PIPE, name), S)
shutil.copytree(os.path.join(PIPE, 'stages'), os.path.join(S, 'stages'), ignore=shutil.ignore_patterns('__pycache__'))
shutil.copytree(os.path.join(PIPE, 'reference'), os.path.join(S, 'reference'))
os.makedirs(os.path.join(S, 'inputs'))
shutil.copy(RAW_SRC, os.path.join(S, 'inputs', 'raw_live.json'))
open(os.path.join(S, '.gitignore'), 'w').write('data/\n__pycache__/\n')
cfg = open(os.path.join(S, 'config.toml'), encoding='utf-8').read()
A = lambda *p: os.path.normpath(os.path.join(ROOT, *p)).replace(os.sep, '/')   # noqa: E731
cfg = re.sub(r'^raw_json\s*=.*$', f'raw_json  = "{S.replace(os.sep, "/")}/inputs/raw_live.json"', cfg, flags=re.M)
cfg = re.sub(r'^codebook\s*=.*$', f'codebook  = "{A("scripts", "pilot", "codebook.md")}"', cfg, flags=re.M)
cfg = re.sub(r'^pilot_dir\s*=.*$', f'pilot_dir = "{A("scripts", "pilot")}"', cfg, flags=re.M)
cfg = re.sub(r'^gold_dir\s*=.*$', f'gold_dir  = "{A("eval", "gold")}"', cfg, flags=re.M)
cfg = re.sub(r'^eval_lib\s*=.*$', f'eval_lib  = "{A("eval")}"', cfg, flags=re.M)
open(os.path.join(S, 'config.toml'), 'w', encoding='utf-8').write(cfg)
out('scratch copy built in live/experiments/pipeline_scratch (config paths rewritten; data dir = pipeline_scratch/data; raw input = copy of live/out/raw_live.json)')

# ---- the driver runs inside the scratch folder so that `common` is the scratch copy
driver = r'''
import json, os, sys
import pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from common import DATA, PARQUET, log, read_table, write_table
from stages import s01_ingest, s02_candidates, s03_dedup, s04_labels, s11_export
ORIG = sys.argv[1]
log('scratch', 'DATA dir is ' + DATA)
assert os.path.abspath(DATA).startswith(HERE), 'data dir is not inside the scratch folder'
posts = s01_ingest.run()                                   # stage 1 on the collector export (live items only)
orig = pd.read_parquet(os.path.join(ORIG, 'posts.parquet'))
cand = pd.read_parquet(os.path.join(ORIG, 'candidates.parquet'), columns=['post_id'])
ds = orig[(orig.origin == 'dataset') & orig.post_id.isin(cand.post_id)]
posts['origin'] = 'live'
merged = pd.concat([ds, posts], ignore_index=True).drop_duplicates('post_id')
write_table('posts', merged)
log('scratch', f'posts = {len(ds):,} historical rule-net posts (read-only subset) + {len(posts)} live items from the collector')
for t in ('faq', 'faq_matches', 'events', 'peaks', 'placebo', 'metrics', 'metrics_calibration'):
    pq = os.path.join(ORIG, t + '.parquet')
    if os.path.exists(pq):
        write_table(t, pd.read_parquet(pq))                # copied as they are: stages 5-10 are NOT re-run
s02_candidates.run()
s03_dedup.run()
s04_labels.run()
s11_export.run()
'''
open(os.path.join(S, 'run_scratch.py'), 'w', encoding='utf-8').write(driver)
r = subprocess.run([sys.executable, '-X', 'utf8', 'run_scratch.py', os.path.join(PIPE, 'data', 'parquet')], cwd=S,
                   capture_output=True, text=True, encoding='utf-8')
out('\n--- stage log lines (real, from the scratch run) ---')
for ln in (r.stdout + r.stderr).strip().splitlines():
    out(ln)
if r.returncode:
    out(f'SCRATCH RUN FAILED with exit code {r.returncode}')
    sys.exit(1)

# ---- inspect
import pandas as pd
PQ = os.path.join(S, 'data', 'parquet')
posts = pd.read_parquet(os.path.join(PQ, 'posts.parquet'))
live = posts[posts.origin == 'live']
cands = pd.read_parquet(os.path.join(PQ, 'candidates.parquet'))
cl = pd.read_parquet(os.path.join(PQ, 'clusters.parquet'))
lf = pd.read_parquet(os.path.join(PQ, 'labels_final.parquet'))
exp = json.load(open(os.path.join(S, 'data', 'export', 'data.json'), encoding='utf-8'))
raw = json.load(open(RAW_SRC, encoding='utf-8'))
pick = live[live.title.str.contains(PICK, regex=False)]
assert len(pick), 'chosen item not in the export'
pid = pick.iloc[0].post_id
r0 = pick.iloc[0]
rr = next(x for x in raw if x['mention_id'] == pid)
out(f'\n=== THE ITEM: {pid}')
out(f'collector export : {rr["title"]} | outlet={rr["source_name"]} | kind={rr["kind"]} | published_at={rr["published_at"]} | discovered_at={rr["discovered_at"]} '
    f'| sentiment={rr["sentiment"]} authors={rr["authors"]} | replay={rr["replay"]} published={rr["published"]}')
out(f'stage 1 ingest   : posts row origin={r0.origin} platform={r0.platform} source={r0.source} language={r0.language} new_since_dataset={r0.new_since_dataset} '
    f'has_author={r0.has_author} text_len={r0.text_len} ingested_at={r0.ingested_at}')
out(f'                   dropped by ingest (extra collector fields): discovered_at, kind, modified_at, replay, published, project_hint, content_hash, title_hit, source_terms')
c = cands[cands.post_id == pid]
out('stage 2 rules    : ' + (f'IN candidates: project_hint={c.iloc[0].project_hint} rule_hits={c.iloc[0].rule_hits} n_mentions={c.iloc[0].n_mentions} snippet={c.iloc[0].snippet[:120]!r}' if len(c) else 'NOT in candidates'))
k = cl[cl.post_id == pid].iloc[0]
out(f'stage 3 dedup    : cluster_id={k.cluster_id} cluster_size={k.cluster_size} n_outlets={k.n_outlets} is_representative={k.is_representative}')
f = lf[lf.post_id == pid]
out('stage 4 labels   : ' + (f'label_source={f.iloc[0].label_source} project={f.iloc[0].project} stance={f.iloc[0].stance} confidence={f.iloc[0].confidence} abstain={f.iloc[0].abstain} (no LLM run exists for this item)' if len(f) else 'no row'))
lv = [x for x in exp['live'] if x['id'] == pid]
out('stage 11 export  : data.json "live" entry: ' + (json.dumps(lv[0], ensure_ascii=False) if lv else 'MISSING'))
in_posts = [x for x in exp['posts'] if x['id'] == pid]
out(f'                   in data.json "posts" (counted, evidence list): {bool(in_posts)}  <- needs a human or LLM label first (label_source human, vote or rules_curated)')
out(f'                   funnel_live = {exp["funnel_live"]}')

out('\n=== all live items through the same stages (counts)')
ids = set(live.post_id)
cc = cands[cands.post_id.isin(ids)]
out(f'live items in: {len(ids)}; in the wide net (stage 2): {len(cc)}; by hint: {cc.project_hint.value_counts().to_dict()}')
cls = cl[cl.post_id.isin(ids)]
out(f'stage 3: live items form {cls.cluster_id.nunique()} clusters; clusters with more than one live item: {(cls.groupby("cluster_id").size() > 1).sum()}')
out(f'stage 4: label_source of live items: {lf[lf.post_id.isin(ids)].label_source.value_counts().to_dict()}')
out(f'export "live" section: {len(exp["live"])} entries, in_wide_net true for {sum(x["in_wide_net"] for x in exp["live"])}, verified false for {sum(not x["verified"] for x in exp["live"])}')
og = live[live.title.str.contains('Île-de-France à l’arrêt', regex=False)]
if len(og):
    g = og.iloc[0]
    out(f'\nRULE GAP found by this test: {g.post_id} "{g.title[:90]}" ({g.source}) was collected (title filter hit via the place word Ile-de-France) '
        f'but stage 2 rules did NOT take it: in candidates = {bool(cands.post_id.eq(g.post_id).any())}. '
        'Reason: stage 2 place words for paris_c1 are creteil|limeil|villeneuve-saint-georges|val-de-marne|c1, none is in the headline.')
out('\nthe other collector items that the stage 2 rules did NOT take (sample), to compare with the collector title filter:')
miss = live[~live.post_id.isin(cands.post_id)]
for t in miss.title.head(6):
    out('   not a candidate: ' + t[:100])
out('\nParis C1 live items and their dedup clusters (same cluster id = merged as one story):')
pc = live.merge(cands[['post_id', 'project_hint']], on='post_id').merge(cl, on='post_id')
pc = pc[pc.project_hint == 'paris_c1']
for _, x in pc.sort_values('published_at').iterrows():
    out(f'   {str(x.published_at)[:10]} cluster={x.cluster_id[:12]} size={x.cluster_size} source={x.source:22} {x.title[:80]}')

fp_after = tree_fingerprint(os.path.join(PIPE, 'data'))
out(f'\nfingerprint of pipeline/data after : {fp_after}  -> {"UNCHANGED (nothing written into pipeline/data)" if fp_after == fp_before else "CHANGED !!"}')
out('\nSTAGES RUN in the scratch copy : 1 ingest, 2 candidates (rules; embedding net off), 3 dedup, 4 labels (vote over existing label files; live items get none), 11 export.')
out('STAGES NOT RUN                : 5 LLM labelling (cloud, costs money), 6 student, 7 calibrate, 8 measure, 9 FAQ match, 10 events, embeddings. Tables faq, faq_matches, events, peaks, placebo, metrics were copied unchanged.')
out('So: the item reached the export "live" list as an UNVERIFIED wide-net hit. It has no stance. It would enter "posts" (the counted evidence) only after a labelling run.')
