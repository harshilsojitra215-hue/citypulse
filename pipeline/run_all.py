"""Run the whole pipeline in order, like `make all`.

    python -X utf8 run_all.py                 # dataset only, no network, no paid calls (about 5 minutes on a laptop)
    python -X utf8 run_all.py --from labels   # start at a later stage (earlier tables must exist)
    python -X utf8 run_all.py --live          # also fetch new public news items after 27 Oct 2026
    python -X utf8 run_all.py --embed         # also run the embedding net in candidate retrieval (slow on CPU)

Stage 5 (LLM labelling) is never run here: it costs money or needs a GPU. Run it on purpose
(stages/s05_llm_label.py), then re-run from `labels`.
"""
import argparse
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from stages import (s01_ingest, s02_candidates, s03_dedup, s04_labels, s06_student, s07_calibrate,  # noqa: E402
                    s08_measure, s09_faq_match, s10_events, s11_export, s12_live)

ORDER = ['ingest', 'live', 'candidates', 'dedup', 'labels', 'student', 'labels2', 'calibrate', 'measure', 'faq', 'events', 'export']


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--from', dest='start', default='ingest', choices=ORDER)
    ap.add_argument('--live', action='store_true')
    ap.add_argument('--embed', action='store_true')
    ap.add_argument('--limit', type=int, default=None, help='ingest only the first N records (smoke test)')
    a = ap.parse_args()
    steps = {
        'ingest': lambda: s01_ingest.run(a.limit),
        'live': lambda: s12_live.run() if a.live else None,
        'candidates': lambda: s02_candidates.run(embed=True if a.embed else None),
        'dedup': s03_dedup.run,
        'labels': s04_labels.run,          # first pass: the student trains on these votes
        'student': s06_student.run,
        'labels2': s04_labels.run,         # second pass: adds the student's second opinion
        'calibrate': s07_calibrate.run,
        'measure': s08_measure.run,
        'faq': s09_faq_match.run,
        'events': s10_events.run,
        'export': s11_export.run,
    }
    t = time.time()
    for name in ORDER[ORDER.index(a.start):]:
        steps[name]()
    print(f'done in {time.time() - t:.0f}s -> data/export/data.json')


if __name__ == '__main__':
    main()
