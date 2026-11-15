"""Build the reliability pilot sample. Run: python -I -X utf8 build_sample.py
Seed is fixed (SEED). Reads pickles from ../deep_stadt. Writes into this folder."""
import pandas as pd, re, html, json, csv, random, os
SEED = 20261114
HERE = os.path.dirname(os.path.abspath(__file__))
D = os.path.join(HERE, '..', 'deep_stadt')
rng = random.Random(SEED)
ld = lambda f: pd.read_pickle(os.path.join(D, f + '.pkl'))
df = ld('df2'); hn = ld('hn_final'); bonn = ld('bonn_dedup'); paris = ld('paris_dedup'); ipai = ld('ipai_core')
paris = paris[paris.language_code.str.startswith('fr')]
used_ids = set(); used_nt = set()

KW_HN = r'seilbahn|gondel|kabinenbahn|ropeway|cable car|cablecar|seilschwebebahn|schwebebahn|stadtseilbahn'
KW_PARIS = r'téléphérique|telepherique|câble c1|cable c1|c1\b|câble'
KW_IPAI = r'\bipai\b|innovation park|innovationspark'


def nt(r):
    t = r['title'] if isinstance(r['title'], str) else ''
    return re.sub(r'\W+', ' ', t.lower()).strip() + '|' + str(r['source_name'])


def pick(cand, n_news, n_other):
    """round-robin over media types; random within; skip used ids / duplicate title+source"""
    cand = cand[~cand.mention_id.isin(used_ids)]

    def take(sub, n):
        groups = {k: g.sample(frac=1, random_state=rng.randint(0, 10**6)).to_dict('records')
                  for k, g in sub.groupby('media_type_name')}
        keys = sorted(groups); got = []
        while len(got) < n and any(groups.values()):
            for k in keys:
                while groups[k]:
                    r = groups[k].pop()
                    key = nt(r)
                    if key in used_nt or r['mention_id'] in used_ids:
                        continue
                    used_nt.add(key); used_ids.add(r['mention_id']); got.append(r); break
                if len(got) >= n:
                    break
        return got
    news = cand[cand.media_type_name == 'News']; other = cand[cand.media_type_name != 'News']
    out = take(news, n_news)
    out += take(other, n_other)
    if len(out) < n_news + n_other:
        rest = cand[~cand.mention_id.isin(used_ids)]
        out += take(rest, n_news + n_other - len(out))
    return out


def clean(s, authors):
    s = html.unescape(s or '')
    s = re.sub(r'<br\s*/?>', ' ', s); s = re.sub(r'<[^>]+>', ' ', s)
    s = re.sub(r'https?://\s?\S+|www\.\S+|[\w-]+\.(?:google|com|de|fr|ch|at)/\S+', '[URL]', s)
    s = re.sub(r'[\w.+-]+@[\w-]+\.[\w.-]+', '[EMAIL]', s)
    s = re.sub(r'@[\w.]+', '[USER]', s)
    for a in (authors if isinstance(authors, (list, tuple)) or hasattr(authors, 'tolist') else []):
        if isinstance(a, str) and len(a.strip()) >= 4:
            s = re.sub(re.escape(a.strip().lstrip('@')), '[USER]', s, flags=re.I)
    return re.sub(r'\s+', ' ', s).strip()


def snippet(r, kw, n=700):
    title = clean(r['title'] if isinstance(r['title'], str) else '', r['authors'])
    body = clean(r['content'] if isinstance(r['content'], str) else '', r['authors'])
    if len(body) > n:
        m = re.search(kw, body, flags=re.I)
        pos = m.start() if m else 0
        a = max(0, pos - n // 2); b = min(len(body), a + n); a = max(0, b - n)
        body = ('...' if a > 0 else '') + body[a:b] + ('...' if b < len(body) else '')
    return (title + '\n\n' + body).strip()


rows = []


def add(recs, stratum, kw):
    for r in recs:
        rows.append(dict(project_hint=stratum, date=str(pd.Timestamp(r['ts']).date()), media_type=r['media_type_name'],
                         vendor_sentiment=int(r['sentiment']), text=snippet(r, kw), _id=r['mention_id'],
                         _url=r['url'], _src=r['source_name']))


add(pick(hn, 34, 36), 'heilbronn', KW_HN)
add(pick(bonn, 25, 25), 'bonn', KW_HN)
add(pick(paris, 15, 25), 'paris', KW_PARIS)
add(pick(ipai, 14, 26), 'ipai', KW_IPAI)

# hard negatives from Seilbahn-type records outside every candidate set
excl = set(hn.mention_id) | set(bonn.mention_id) | set(paris.mention_id) | set(ipai.mention_id)
pool = df[df.seil & ~df.mention_id.isin(excl)].copy()
T = pool.txt
has = lambda p: T.str.contains(p, regex=True)


def nearkw(p, w=250):
    """Seilbahn keyword within w chars of a category keyword"""
    def f(t):
        for m in re.finditer(KW_HN, t):
            if re.search(p, t[max(0, m.start() - w):m.end() + w]):
                return True
        return False
    return T.map(f)


no_proj = ~has(r'heilbronn|bonn|ipai|câble c1|créteil')
cats = {
    'ski_mountain': (no_proj & nearkw(r'skigebiet|skilift|piste|bergbahn|gipfel|zugspitze|skifahren|talstation|bergstation'), 11),
    'toy_playground': (no_proj & nearkw(r'spielplatz|spielzeug|lego|playmobil|modellbahn|klettergerüst|kita|kinder'), 5),
    'other_city': (no_proj & has(r'öpnv|nahverkehr|stadtseilbahn|urban') & has(r'stuttgart|münchen|berlin|köln|koblenz|wuppertal|hamburg|dresden|mannheim|buga|la paz|medell|london|salzburg|graz|innsbruck|ankara|mexiko|bogot'), 9),
    'job_ad': (nearkw(r'stellenangebot|m/w/d|w/m/d|bewerbung|wir suchen|stellenanzeige', 400), 5),
    'near_miss': (has(r'heilbronn') & ~has(r'heilbronner kreuz|krippenstein|dachstein|obertraun|bergrettung'), 10),
}
for name, (mask, n) in cats.items():
    sub = pool[mask.values & ~pool.mention_id.isin(used_ids).values]
    recs = pick(sub, n // 2, n - n // 2)
    print('hardneg', name, 'pool', len(sub), 'got', len(recs))
    add(recs, 'hardneg_' + name, KW_HN)

rng.shuffle(rows)
for i, r in enumerate(rows, 1):
    r['pid'] = f'P{i:03d}'
assert len(rows) == 240, len(rows)
pub = ['pid', 'project_hint', 'date', 'media_type', 'vendor_sentiment', 'text']
with open(os.path.join(HERE, 'sample.jsonl'), 'w', encoding='utf-8') as f:
    for r in rows:
        f.write(json.dumps({k: r[k] for k in pub}, ensure_ascii=False) + '\n')
with open(os.path.join(HERE, 'sample_key.csv'), 'w', encoding='utf-8-sig', newline='') as f:
    w = csv.writer(f); w.writerow(['pid', 'mention_id', 'url', 'source_name', 'project_hint'])
    for r in rows:
        w.writerow([r['pid'], r['_id'], r['_url'], r['_src'], r['project_hint']])

# batches: deal strata round-robin so each batch mixes strata, then shuffle inside
bystrat = {}
for r in rows:
    bystrat.setdefault(r['project_hint'].split('_')[0], []).append(r)
for k in sorted(bystrat):
    rng.shuffle(bystrat[k])
deal = [r for k in sorted(bystrat) for r in bystrat[k]]
batches = [[] for _ in range(6)]
for i, r in enumerate(deal):
    batches[i % 6].append(r)
for b in batches:
    rng.shuffle(b)
for i, b in enumerate(batches, 1):
    with open(os.path.join(HERE, f'batch_{i:02d}.jsonl'), 'w', encoding='utf-8') as f, \
         open(os.path.join(HERE, f'batch_{i:02d}_blind.jsonl'), 'w', encoding='utf-8') as g:
        for r in b:
            f.write(json.dumps({k: r[k] for k in pub}, ensure_ascii=False) + '\n')
            g.write(json.dumps({k: r[k] for k in ['pid', 'date', 'media_type', 'text']}, ensure_ascii=False) + '\n')
    print('batch', i, len(b), pd.Series([r['project_hint'].split('_')[0] for r in b]).value_counts().to_dict())

# human review: 60 stratified (18/12/10/10/10), blind, shuffled
quota = {'heilbronn': 18, 'bonn': 12, 'paris': 10, 'ipai': 10, 'hardneg': 10}
hr = []
for k, n in quota.items():
    pool_k = bystrat[k][:]
    rng.shuffle(pool_k)
    pool_k.sort(key=lambda r: r['media_type'] == 'News')  # non-news first so social voices are covered
    hr += pool_k[:n]
rng.shuffle(hr)
with open(os.path.join(HERE, 'human_review.csv'), 'w', encoding='utf-8-sig', newline='') as f:
    w = csv.writer(f); w.writerow(['pid', 'text', 'project', 'stance', 'arguments', 'voice', 'evidence'])
    for r in hr:
        w.writerow([r['pid'], r['text'], '', '', '', '', ''])
print('human_review', len(hr))
tab = pd.DataFrame(rows).groupby(['project_hint', 'media_type']).size().unstack(fill_value=0)
print(tab.to_string()); print(tab.sum(axis=1).to_string())
print(f'SEED={SEED}')
