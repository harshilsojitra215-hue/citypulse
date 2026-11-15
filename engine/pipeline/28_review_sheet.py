"""Step 28 (CityPulse): human review sheet for the TEST pairs (blind: no model labels shown).

Picks 120 TEST pairs the way an active-learning loop would: 60 where the annotator models disagree (the uncertain
ones, where a human label is worth most) and 60 at random from the rest. Open the HTML, press 1-4, download the CSV
to out/citypulse/human_labels.csv, then:  python -I src/23_match_eval.py human
"""
import json, html
import numpy as np, pandas as pd
OUT = "out/citypulse"
rng = np.random.default_rng(5)
P = pd.read_parquet(f"{OUT}/pairs.parquet")
P = P[P.split == "test"]
for n in ["opus", "sonnet", "qwen27"]:
    L = pd.DataFrame([json.loads(l) for l in open(f"{OUT}/pairlabels_{n}.jsonl")]).drop_duplicates("pid").set_index("pid").label
    P[n] = P.pid.map(L)
dis = P[(P.opus != P.sonnet) | (P.opus != P.qwen27)]
agr = P.drop(dis.index)
pick = pd.concat([dis.sample(60, random_state=5), agr[agr.opus == "same"].sample(20, random_state=5), agr[agr.opus != "same"].sample(40, random_state=5)]).sample(frac=1, random_state=5)
pick.assign(why=np.where(pick.index.isin(dis.index), "models disagree", "random"))[["pid", "why"]].to_csv(f"{OUT}/review_sample.csv", index=False)
items = [dict(pid=r.pid, a=r.q_claim, ap=r.q_project, b=r.c_claim, bp=r.c_project) for r in pick.itertuples()]
rules = html.escape(open("prompts/pair_codebook_v1.md", encoding="utf-8").read().split("Output:")[0])
page = """<!doctype html><meta charset="utf-8"><title>CityPulse pair review</title>
<style>body{font:17px/1.5 system-ui;max-width:820px;margin:40px auto;padding:0 16px;background:#f6f5f1;color:#1c1c1a}
.c{background:#fff;border:1px solid #ddd;border-radius:10px;padding:18px;margin:12px 0}.p{font-size:13px;color:#666}
button{font:16px system-ui;padding:12px 18px;margin:6px 6px 0 0;border-radius:8px;border:1px solid #999;background:#fff;cursor:pointer}
button:hover{background:#eee}pre{white-space:pre-wrap;font:13px/1.45 system-ui;color:#444}input{font:16px system-ui;padding:6px}</style>
<h2>Do these two claims make the same argument?</h2>
<p>Your name: <input id="who" placeholder="team"> &nbsp; <span id="prog"></span></p>
<div class="c"><div class="p" id="ap"></div><div id="a"></div></div>
<div class="c"><div class="p" id="bp"></div><div id="b"></div></div>
<div><button onclick="go('same')">1 same</button><button onclick="go('related')">2 related</button><button onclick="go('opposing')">3 opposing</button>
<button onclick="go('unrelated')">4 unrelated</button><button onclick="back()">&larr; back</button><button onclick="dl()">Download CSV</button></div>
<details><summary>Rules (same ones the models got)</summary><pre>__RULES__</pre></details>
<script>const I=__ITEMS__;let L={};try{L=JSON.parse(localStorage.getItem('cp_review')||'{}')}catch(e){}
let i=I.findIndex(x=>!L[x.pid]);if(i<0)i=I.length-1;
function show(){const x=I[i];a.textContent=x.a;b.textContent=x.b;ap.textContent=x.ap;bp.textContent=x.bp;
prog.textContent=Object.keys(L).length+' of '+I.length+' done'+(L[x.pid]?' (this one: '+L[x.pid]+')':'')}
function go(l){L[I[i].pid]=l;try{localStorage.setItem('cp_review',JSON.stringify(L))}catch(e){};if(i<I.length-1)i++;show()}
function back(){if(i>0)i--;show()}
function dl(){const w=who.value||'human';const rows=['pid,label,labeller'].concat(Object.entries(L).map(([p,l])=>p+','+l+','+w));
const u=URL.createObjectURL(new Blob([rows.join('\\n')],{type:'text/csv'}));const e=document.createElement('a');e.href=u;e.download='human_labels.csv';e.click()}
document.onkeydown=e=>{if(e.target.tagName=='INPUT')return;const m={'1':'same','2':'related','3':'opposing','4':'unrelated'};if(m[e.key])go(m[e.key]);if(e.key=='ArrowLeft')back()};show()</script>"""
open(f"{OUT}/review_pairs.html", "w", encoding="utf-8").write(page.replace("__RULES__", rules).replace("__ITEMS__", json.dumps(items, ensure_ascii=False)))
print("review sheet:", f"{OUT}/review_pairs.html", len(items), "pairs |", int(pick.index.isin(dis.index).sum()), "contested")
