# Model card: citypulse-matcher-v2

**What it does:** given two short claims (German or English, as extracted from public posts), it gives the probability that they are the *same argument*, a *related* concern, *opposing*, or *unrelated*. CityPulse uses it to group differently worded claims and to decide whether a new claim has an equivalent in the history.

| | |
|---|---|
| Architecture | mDeBERTa-v3-base cross-encoder, 4-class head, 279 M parameters |
| Base model | [`MoritzLaurer/mDeBERTa-v3-base-mnli-xnli`](https://huggingface.co/MoritzLaurer/mDeBERTa-v3-base-mnli-xnli), MIT licence |
| Labels | 0 same, 1 related, 2 opposing, 3 unrelated (`config.json` `id2label`) |
| Input | `tokenizer(claim_a, claim_b, max_length=96, truncation=True)`; the score is the average over both text orders |
| Training data | 11,245 claim pairs (both orders used) whose query claim was published 2025-01-04..2025-12-31, labelled by Claude Opus with `pipeline/prompts/pair_codebook_v1.md`. Derived from the challenge dataset: **not redistributed** |
| Training | 4 epochs, AdamW lr 2e-5, batch 32, linear warm-up 10%, class weights 1/sqrt(frequency), best epoch on DEV (12% of training queries). Seed 0. RTX 5090, 210 s |
| Stored as | fp16 safetensors (558 MB), **loaded as float32** for inference. Max change in probabilities from the fp16 export: 0.0045 (3,000 pairs) |
| Measured | see `docs/EVALUATION.md`: pair F1 0.65 [0.57–0.71] vs cosine 0.37 on later months; provisional (AI reference labels) |
| Not for | detecting contradictions ("opposing" F1 about 0.13, disabled in the product); polling or measuring public opinion; texts much longer than one claim |

## Files and checksum

The weights are **not in git** (size, and they are derived from the challenge data). Expected folder `models/citypulse-matcher-v2/` (or set `CITYPULSE_MODEL`):

```
config.json  model.safetensors  tokenizer.json  tokenizer_config.json  spm.model  special_tokens_map.json  added_tokens.json  export_check.json
```

sha256 of `model.safetensors` (also in `models/checksums.txt`):

```
2b7c277eb458c4f59d8228fe5a363e29c6aa47e98e9bccc4477d5091f458670d
```

Check: `shasum -a 256 models/citypulse-matcher-v2/model.safetensors`. `python -m citypulse.check` and `/api/meta` show the checksum of the loaded file.

## How to get the weights (no retraining)

The complete folder is shipped as **`citypulse-matcher-v2.zip`** (578 MB) in the team's release folder, next to `SHA256SUMS.txt`. Two copies exist: the team's laptop (release folder) and the team GPU box (`~/future_city_hackathon/citypulse/models/citypulse-matcher-v2/`). Both have the checksum below.

```bash
(cd ~/citypulse_release && shasum -a 256 -c --ignore-missing SHA256SUMS.txt)   # citypulse-matcher-v2.zip: OK
unzip -q ~/citypulse_release/citypulse-matcher-v2.zip -d models/       # run from the repository root
shasum -a 256 models/citypulse-matcher-v2/model.safetensors            # 2b7c277e…670d
.venv/bin/python -m citypulse.check     # "matcher model weights OK", "bundle manifest OK", "live model reproduces cached scores OK"
```

Restart the API afterwards. `/api/health` then shows `matcher.mode: local-model`.

**Redistribution:** do **not** publish these weights (public GitHub, Hugging Face, public release assets). The base model is MIT, which would allow it, but the fine-tuning labels are derived from the challenge dataset, which came with no redistribution licence. Share them only inside the team, through a private channel.

**Or retrain** (needs the lab folder with the challenge data and the labelled pairs, about 4 minutes on a CUDA GPU; on an Apple M-series laptop about 35 minutes, estimated from epoch timings):

```bash
cd "$CITYPULSE_LAB"
python ../citypulse/pipeline/27_finetune_matcher.py --train out/citypulse/v2/train.csv \
  --base MoritzLaurer/mDeBERTa-v3-base-mnli-xnli --tag mdeberta2 --seed 0 \
  --score out/citypulse/v2/eval.csv out/citypulse/v2/index.csv --save models/mdeberta2_s0
python ../citypulse/pipeline/33_export_fp16.py models/mdeberta2_s0 ../citypulse/models/citypulse-matcher-v2 out/citypulse/v2/eval.csv   # needs CUDA for its check
```

A retrained model gives slightly different weights (and a different checksum): GPU kernels are not bit-exact and the three seeds already differ (dev F1 0.66–0.73). After retraining, rerun `make eval` and `make bundle` so the cached scores and thresholds belong to the new weights.

The labelled pairs come from `pipeline/29_pairs_v2.py` (pair table, time split), `pipeline/21_pairs_label.py --model opus` (labels, Claude Code CLI) and `pipeline/31_v2_sets.py` (train / eval / index files).

**Known pitfall (fixed 15 Nov):** the base checkpoint is stored in fp16. `transformers` >= 5 keeps that dtype when loading, and training in fp16 turns the loss into NaN after the first step (the model then predicts "same" for everything). `27_finetune_matcher.py` now loads with `dtype=torch.float32`. The engine refuses weights that produce non-finite outputs.

## Without the weights

The application still runs: replay, emerging concerns and cross-city views use the cached v2 scores in `app_data/pair_scores.parquet` (marked `score_source: cached`). Live matching of searched text and of uploaded batches is off, and the header says so. The app never swaps in a weaker model under this name.
