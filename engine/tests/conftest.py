import os, sys, tempfile
import pytest

# tests read the real data bundle but never the uploads of this machine: an uploaded batch would change the counts
os.environ.setdefault("CITYPULSE_RUNS", tempfile.mkdtemp(prefix="citypulse-test-runs-"))

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


def pytest_configure(config):
    config.addinivalue_line("markers", "live: needs a real LLM / embedder / model (skipped by default; run with -m 'live or not live')")


def pytest_collection_modifyitems(config, items):
    if config.getoption("-m"):
        return
    skip = pytest.mark.skip(reason="live test: run with  -m 'live or not live'")
    for it in items:
        if "live" in it.keywords:
            it.add_marker(skip)
