"""Stage 7: calibration. "When the model says 90 percent, how often is it right?"

Student: temperature scaling fitted on out-of-fold probabilities (data/parquet/student_oof.parquet),
expected calibration error (ECE) before and after. Uses eval/evallib/calibration.py (eval session's code).
LLM labels: no stated confidence is trusted; confidence = share of runs that agree (stage 4).
Its calibration (accuracy per agreement level) needs the human gold set and is computed in stage 8.

Caveat printed into the metric: the out-of-fold labels are AI votes, so this calibrates the student
against the teacher, not against humans. Refit on the gold set when it exists.
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common import DATA, PARQUET, eval_lib, jdump, log  # noqa: E402


def run():
    p = os.path.join(PARQUET, 'student_oof.parquet')
    if not os.path.exists(p):
        log('calibrate', 'no student_oof.parquet (run stage 6 first): skipped')
        return []
    ev = eval_lib()
    from evallib import calibration as cal
    d = pd.read_parquet(p)
    classes = [c for c in d.columns if c not in ('post_id', 'y')]
    P = d[classes].values.clip(1e-6, 1)
    y = d.y.map({c: i for i, c in enumerate(classes)}).values
    logits = np.log(P)
    T = cal.fit_temperature(logits, y)
    P2 = cal.apply_temperature(logits, T)
    conf1, conf2 = P.max(1), P2.max(1)
    correct = (P.argmax(1) == y)
    e1, e2 = cal.ece(conf1, correct), cal.ece(conf2, correct)
    jdump({'temperature': T, 'classes': classes}, os.path.join(DATA, 'student_temperature.json'))
    note = 'student vs AI teacher labels, out-of-fold, pilot 240'
    rows = [{'metric_id': 'calibration.student.ece_before', 'name': 'Student ECE before scaling', 'value': e1, 'n': len(y), 'method': 'ece', 'note': note},
            {'metric_id': 'calibration.student.ece_after', 'name': 'Student ECE after temperature scaling', 'value': e2, 'n': len(y), 'method': 'ece', 'note': note},
            {'metric_id': 'calibration.student.temperature', 'name': 'Temperature', 'value': T, 'n': len(y), 'method': 'temperature', 'note': note}]
    pd.DataFrame(rows).to_parquet(os.path.join(PARQUET, 'metrics_calibration.parquet'), index=False)
    log('calibrate', f'student T={T:.2f}, ECE {e1:.3f} -> {e2:.3f} (n={len(y)}, vs AI labels)')
    return rows


if __name__ == '__main__':
    run()
