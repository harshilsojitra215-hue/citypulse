"""Turn the engine's full labelling (engine/app_data/posts.parquet) into a pipeline label run.

    engine\\.venv\\Scripts\\python -I -X utf8 live/engine_bridge/labels_to_pipeline.py

Why: the website's History tab reads pipeline/data/export/data.json. Until now it only had the 14 Nov pilot (240 posts,
3 AI runs). The engine labelled every relevant post of the city export with the same codebook v1 (Claude Haiku; a
reference sample of 534 posts by Claude Opus). Writing those labels as a label run (pipeline/CONTRACT.md section 2)
lets the pipeline's own vote and export build the final History.

Mapping (one row per post, nothing invented):
- post_id  = doc_id (same shape as the export's mention_id, e.g. "19567151,2182")
- project  = project, with other_urban_cablecar -> other_cablecar (codebook name in the pipeline)
- stance   = support / oppose / mixed / unclear unchanged; neutral -> neutral_informative; na -> null (no stance asked)
- voice    = null: the engine stores a hashed author id, not a voice type. History shows voice as "unclear".
- arguments = []: the engine's arguments are free-text claim families, not codebook codes. They are shown in the
  website's Arguments tab instead.
"""
import datetime as dt
import hashlib
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "engine" / "app_data" / "posts.parquet"
RUN_ID = "2026-11-15_engine_haiku_cb1"
OUT = ROOT / "pipeline" / "data" / "label_runs" / f"{RUN_ID}.jsonl"
PROJ = {"other_urban_cablecar": "other_cablecar"}
STANCE = {"neutral": "neutral_informative", "na": None}


def main():
    p = pd.read_parquet(SRC)
    # the engine used its own codebook (engine/pipeline/prompts/codebook_v1.md), not scripts/pilot/codebook.md:
    # same stance definitions (stance is not tone, news that quotes critics is neutral), different file. The pipeline
    # logs that the sha differs; that warning is true and expected.
    sha = hashlib.sha256((ROOT / "engine" / "pipeline" / "prompts" / "codebook_v1.md").read_bytes()).hexdigest()[:12]
    header = {"_run": {"run_id": RUN_ID, "created_at": "2026-11-14T23:01:00Z", "labeller": "claude-haiku (engine full run; Opus reference sample)",
                       "kind": "llm_cloud", "runs_where": "cloud_us", "task": "project_stance", "prompt_version": "engine_codebook_v1",
                       "codebook_version": "v1", "codebook_sha": sha,
                       "params": {"source": "engine/app_data/posts.parquet", "label_source_counts": p.label_source.value_counts().to_dict(),
                                  "converted_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}}}
    n = 0
    with OUT.open("w", encoding="utf-8") as f:
        f.write(json.dumps(header, ensure_ascii=False) + "\n")
        for r in p.itertuples():
            f.write(json.dumps({"post_id": str(r.doc_id), "project": PROJ.get(r.project, r.project),
                                "stance": STANCE.get(r.stance, r.stance), "voice": None, "arguments": [],
                                "evidence": None, "project_prob": None, "stance_probs": None, "abstain": False}, ensure_ascii=False) + "\n")
            n += 1
    print(f"wrote {OUT.relative_to(ROOT)}: {n} posts; projects {p.project.map(lambda x: PROJ.get(x, x)).value_counts().to_dict()}")


if __name__ == "__main__":
    main()
