"""Paths used by the review tools. All of them can be overridden with environment variables (read at call time,
so tests can point them at temporary folders)."""
import os
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DEFAULT_LAB = REPO.parent / "6 Cable car lab"   # the hackathon layout: lab folder next to the repo (set CITYPULSE_LAB otherwise)


def queue_dir() -> Path:
    """Folder with the prepared review queues (*.parquet). Not in git. Default: <data bundle>/review."""
    if os.environ.get("CITYPULSE_REVIEW_QUEUES"):
        return Path(os.environ["CITYPULSE_REVIEW_QUEUES"])
    return Path(os.environ.get("CITYPULSE_DATA") or REPO / "app_data") / "review"


def review_dir() -> Path:
    """Folder that holds annotations/ and results/."""
    return Path(os.environ.get("CITYPULSE_REVIEW_DIR") or REPO / "review")


def annotations_dir() -> Path:
    return review_dir() / "annotations"


def results_dir() -> Path:
    return review_dir() / "results"


def lab_dir() -> Path:
    """Working directory for the pair benchmark: must contain out/citypulse/."""
    env = os.environ.get("CITYPULSE_LAB")
    if env:
        return Path(env)
    if (REPO / "lab").exists():
        return REPO / "lab"
    return DEFAULT_LAB


def lab_out() -> Path:
    return lab_dir() / "out" / "citypulse"
