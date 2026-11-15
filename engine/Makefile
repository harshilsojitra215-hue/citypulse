PY ?= .venv/bin/python
.PHONY: api web dev test test-live bundle eval review-eval check release-check

api:            ## backend on http://127.0.0.1:8000
	$(PY) -m uvicorn citypulse.api.main:app --host 127.0.0.1 --port 8000

web:            ## frontend on http://127.0.0.1:3000
	cd web && npm install && npm run dev

test:           ## automated tests (no network, no GPU needed)
	$(PY) -m pytest tests -q

test-live:      ## also the tests that call the real LLM and embedder
	$(PY) -m pytest tests -q -m "live or not live"

bundle:         ## rebuild app_data/ from the research lab (needs CITYPULSE_LAB)
	cd "$(CITYPULSE_LAB)" && "$(abspath $(PY))" -I "$(abspath pipeline/30_build_app_data.py)" "$(abspath app_data)"

eval:           ## rerun the benchmark and the leakage audit (needs CITYPULSE_LAB and the GPU score files)
	cd "$(CITYPULSE_LAB)" && "$(abspath $(PY))" -I "$(abspath pipeline/32_eval_v2.py)"

review-eval:    ## recompute metrics against human labels
	$(PY) -m citypulse.review.evaluate

check:          ## is everything needed for the demo in place?
	$(PY) -m citypulse.check

release-check:  ## before every commit/push: secrets, personal data, data files, sizes, tests
	PY=$(PY) bash scripts/release_check.sh
