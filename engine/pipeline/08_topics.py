"""Step 8: three ways to find topics, run side by side on the same posts.

python -I src/08_topics.py <labelled.parquet>
 A. BERTopic (bge-m3 embeddings -> UMAP -> HDBSCAN -> c-TF-IDF)      unsupervised, finds what we did not expect
 B. LLM argument codes (topic + polarity per argument, from the codebook)  fixed taxonomy, comparable across cities
 C. Keyness: weighted log-odds with informative Dirichlet prior (Monroe et al. 2008)  transparent "which words are typical for X vs Y"
Writes out/topics_bertopic.csv, out/topic_args.csv, out/keyness_*.csv and prints a comparison.
"""
import sys, re, json, collections
import numpy as np, pandas as pd
sys.path.insert(0, "pipeline")
from embed import embed

df = pd.read_parquet(sys.argv[1])
CC = ["heilbronn_cablecar", "paris_c1", "bonn_cablecar", "other_urban_cablecar"]
d = df[df.project.isin(CC) & ~df.passing.fillna(False).astype(bool) & df.is_first_copy].copy()
print("posts used:", len(d), d.project.value_counts().to_dict())

STOP = set("""der die das und oder aber in im ins zu zum zur mit von vom für fur auf aus an am als auch bei bis durch ein eine einer eines einem einen
es ist sind war waren wird werden wurde wurden hat haben hatte sei sich sie er wir ihr ich du man nicht noch nur schon so wie was wer wo
dass daß den dem des über ueber nach vor um unter soll sollen kann können muss müssen mehr sehr ganz viel viele diese dieser dieses jetzt
dann denn doch hier da ja nein mal immer wieder einen keine kein seit gegen ohne zwischen sowie bereits rund etwa laut heute neue neuen neuer
le la les de des du un une et ou en au aux pour par sur dans avec est sont été être a ont qui que qu ce cette ces se sa son ses leur leurs
il elle ils elles on nous vous pas plus ne y d l s c n j m t comme mais aussi tout tous très fait faire entre sans sous après avant depuis
the of and to in is for on with that this it be are was as by at from or an
seilbahn seilbahnen téléphérique telepherique câble cable stimme stimme.de anzeige www https http com""".split())


def toks(t):
    return [w for w in re.findall(r"[a-zäöüßàâçéèêëîïôûùüÿœ]{3,}", t.lower()) if w not in STOP]


# ---- A. BERTopic ----
try:
    from bertopic import BERTopic
    from umap import UMAP
    from hdbscan import HDBSCAN
    from sklearn.feature_extraction.text import CountVectorizer
    docs = d.snippet.str.slice(0, 1500).tolist()
    E = embed(docs)
    tm = BERTopic(umap_model=UMAP(n_neighbors=12, n_components=5, min_dist=0.0, metric="cosine", random_state=42),
                  hdbscan_model=HDBSCAN(min_cluster_size=12, min_samples=4, prediction_data=True),
                  vectorizer_model=CountVectorizer(stop_words=list(STOP), token_pattern=r"(?u)\b[^\W\d_]{3,}\b", ngram_range=(1, 2), min_df=3),
                  top_n_words=8, calculate_probabilities=False)
    topics, _ = tm.fit_transform(docs, E)
    d["bertopic"] = topics
    info = tm.get_topic_info()
    info["projects"] = [d[d.bertopic == t].project.value_counts().head(3).to_dict() for t in info.Topic]
    info[["Topic", "Count", "Name", "projects"]].to_csv("out/topics_bertopic.csv", index=False)
    print("\n== A. BERTopic:", (info.Topic >= 0).sum(), "topics, outliers:", int((d.bertopic == -1).sum()))
    print(info[["Topic", "Count", "Name", "projects"]].head(25).to_string(index=False))
except Exception as e:
    print("BERTopic failed:", repr(e)[:300])

# ---- B. LLM argument codes ----
ar = []
for r in d.itertuples():
    for a in (r.arguments if isinstance(r.arguments, (list, np.ndarray)) else []):
        if isinstance(a, dict):
            ar.append(dict(id=r.mention_id, project=r.project, channel=r.channel, topic=a.get("topic"), polarity=a.get("polarity"), claim=a.get("claim")))
A = pd.DataFrame(ar)
A.to_csv("out/topic_args.csv", index=False)
if len(A):
    # share of posts per project that raise each topic (a post counts once per topic)
    per = A.drop_duplicates(["id", "topic"]).groupby(["topic", "project"]).size().unstack(fill_value=0)
    per = (per / d.project.value_counts()).round(2).fillna(0)
    print("\n== B. share of posts raising each argument topic, by project ==\n", per.sort_values("heilbronn_cablecar", ascending=False).to_string())
    pol = A.groupby(["project", "topic", "polarity"]).size().unstack(fill_value=0)
    print("\nHeilbronn arguments by polarity:\n", pol.loc["heilbronn_cablecar"].sort_values("contra", ascending=False).to_string() if "heilbronn_cablecar" in pol.index.get_level_values(0) else "-")
    if "bertopic" in d:
        m = A.merge(d[["mention_id", "bertopic"]], left_on="id", right_on="mention_id")
        from sklearn.metrics import normalized_mutual_info_score
        mm = m[m.bertopic >= 0].drop_duplicates("id")
        print("\nNMI(BERTopic cluster, first LLM topic) =", round(normalized_mutual_info_score(mm.bertopic, mm.topic), 3), "(0 = unrelated, 1 = same partition)")


# ---- C. keyness (log-odds with informative Dirichlet prior) ----
def log_odds(a_docs, b_docs, prior_docs, top=25):
    ca, cb, cp = collections.Counter(), collections.Counter(), collections.Counter()
    for t in a_docs: ca.update(set(toks(t)))
    for t in b_docs: cb.update(set(toks(t)))
    for t in prior_docs: cp.update(set(toks(t)))
    na, nb, a0 = sum(ca.values()), sum(cb.values()), sum(cp.values())
    out = []
    for w in set(ca) | set(cb):
        if ca[w] + cb[w] < 4:
            continue
        aw = cp[w] + 0.01
        l1 = np.log((ca[w] + aw) / (na + a0 - ca[w] - aw))
        l2 = np.log((cb[w] + aw) / (nb + a0 - cb[w] - aw))
        var = 1 / (ca[w] + aw) + 1 / (cb[w] + aw)
        out.append((w, (l1 - l2) / np.sqrt(var), ca[w], cb[w]))
    o = pd.DataFrame(out, columns=["word", "z", "n_a", "n_b"]).sort_values("z", ascending=False)
    return o.head(top), o.tail(top).iloc[::-1]


de = d[d.lang == "de"]
hn, others = de[de.project == "heilbronn_cablecar"].text_clean, de[de.project.isin(["bonn_cablecar", "other_urban_cablecar"])].text_clean
a, b = log_odds(hn, others, de.text_clean)
a.to_csv("out/keyness_heilbronn_vs_other_german.csv", index=False)
print("\n== C. words typical for Heilbronn vs other German urban cable cars ==\n", ", ".join(f"{w}({z:.1f})" for w, z in zip(a.word, a.z)))
print("typical for the others:", ", ".join(f"{w}({z:.1f})" for w, z in zip(b.word, b.z)))
soc, news = d[(d.channel == "social") & (d.lang == "de")].text_clean, d[(d.channel == "news") & (d.lang == "de")].text_clean
a, b = log_odds(soc, news, de.text_clean)
a.to_csv("out/keyness_social_vs_news_german.csv", index=False)
print("\nwords typical for social vs news (German):", ", ".join(f"{w}({z:.1f})" for w, z in zip(a.word, a.z)))
print("typical for news:", ", ".join(f"{w}({z:.1f})" for w, z in zip(b.word, b.z)))
