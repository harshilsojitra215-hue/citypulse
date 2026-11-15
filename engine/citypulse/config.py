"""All paths and switches in one place. Everything can be overridden by environment variables (see .env.example)."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = Path(os.environ.get("CITYPULSE_DATA", ROOT / "app_data"))          # the data bundle (never in git)
RUNS = Path(os.environ.get("CITYPULSE_RUNS", ROOT / "runs"))              # one folder per uploaded batch
MODEL_DIR = Path(os.environ.get("CITYPULSE_MODEL", ROOT / "models" / "citypulse-matcher-v2"))
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")       # embeddings (bge-m3) and optional local LLM
EMBED_MODEL = os.environ.get("CITYPULSE_EMBED_MODEL", "bge-m3")
LLM_BACKEND = os.environ.get("CITYPULSE_LLM_BACKEND", "claude")           # claude (Claude Code CLI) | openrouter | ollama
LLM_MODEL = os.environ.get("CITYPULSE_LLM_MODEL", "haiku")                # e.g. haiku | qwen3.8:27b-q4_K_M
AUTHOR_SALT = os.environ.get("CITYPULSE_AUTHOR_SALT", "fch2026-cablecar") # authors are only ever stored as a salted hash
PROJECT_NAMES = {"heilbronn_cablecar": "Heilbronn", "bonn_cablecar": "Bonn", "paris_c1": "Paris Câble C1",
                 "other_urban_cablecar": "Other cities", "ipai": "IPAI campus"}
EARLIEST_REPLAY_CUTOFF = "2026-07-01"   # the matcher saw nothing published from this date on (training and calibration end 2026-06-30)
