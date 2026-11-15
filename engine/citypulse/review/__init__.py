"""Human verification for CityPulse: review queues, append-only annotations, evaluation against human labels.

    from citypulse.review import router      # FastAPI router, prefix /api/review
    python -m citypulse.review.evaluate      # metrics against the human labels -> review/results/latest.json
    python -m citypulse.review.export_training   # human-corrected pair labels for a later retraining run
"""
from .api import router

__all__ = ["router"]
