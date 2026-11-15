"""Stage 6: the small local "student" model for relevance and project.

Two modes:
1. Fine-tuned model from Hamburg (the real student): put a Hugging Face folder in
   pipeline/models/student/ (config.json, model weights, tokenizer, labels.json). This stage then
   predicts `project` with a probability for every candidate. CPU is enough for inference.
2. Laptop baseline (runs tonight, no GPU): TF-IDF word and character n-grams + logistic regression,
   trained on the pilot vote (240 posts, 3 AI runs). It is the fallback for the live "update" button
   and the line to beat for the Hamburg model. 5-fold cross-validated accuracy is printed and saved.

Output: a label run file data/label_runs/student_<name>.jsonl (kind=student, project + project_prob,
no stance). Stage 4 uses student labels only for posts that no LLM or human labelled.
"""
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common import DATA, HERE, RUNS, codebook_sha, jdump, log, read_table  # noqa: E402

MODEL_DIR = os.path.join(HERE, 'models', 'student')


def training_data():
    f = read_table('labels_final')
    c = read_table('candidates')[['post_id', 'snippet']]
    p = read_table('posts', columns=['post_id', 'title', 'text'])
    tr = f[f.label_source.isin(['vote', 'human']) & f.project.notna()].merge(p, on='post_id', how='left')
    tr = tr.merge(c, on='post_id', how='left')
    tr['x'] = tr.snippet.fillna(tr.title.fillna('') + ' | ' + tr.text.fillna('').str[:600])
    return tr


def baseline():
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import StratifiedKFold, cross_val_predict
    from sklearn.pipeline import make_pipeline, make_union
    tr = training_data()
    y = tr.project.values
    model = make_pipeline(
        make_union(TfidfVectorizer(ngram_range=(1, 2), min_df=1, sublinear_tf=True),
                   TfidfVectorizer(analyzer='char_wb', ngram_range=(3, 5), min_df=2, sublinear_tf=True)),
        LogisticRegression(max_iter=2000, C=4.0, class_weight='balanced'))
    k = min(5, pd.Series(y).value_counts().min())
    oof = cross_val_predict(model, tr.x, y, cv=StratifiedKFold(k, shuffle=True, random_state=0), method='predict_proba')
    classes = np.unique(y)
    pred = classes[oof.argmax(1)]
    rel = lambda v: np.isin(v, ['heilbronn_cablecar', 'bonn_cablecar', 'paris_c1', 'ipai'])
    m = {'n_train': int(len(y)), 'cv_folds': int(k), 'project_accuracy': float((pred == y).mean()),
         'relevance_accuracy': float((rel(pred) == rel(y)).mean()),
         'note': 'Cross-validated on the pilot vote (AI labels), not on human gold. Agreement with the teacher, not accuracy.'}
    # save out-of-fold probabilities for calibration (stage 7)
    oof_df = pd.DataFrame(oof, columns=classes)
    oof_df.insert(0, 'post_id', tr.post_id.values)
    oof_df.insert(1, 'y', y)
    oof_df.to_parquet(os.path.join(DATA, 'parquet', 'student_oof.parquet'), index=False)
    model.fit(tr.x, y)
    return model, classes, m


def predict_hf(texts):
    from transformers import AutoModelForSequenceClassification, AutoTokenizer
    import torch
    tok = AutoTokenizer.from_pretrained(MODEL_DIR)
    mdl = AutoModelForSequenceClassification.from_pretrained(MODEL_DIR).eval()
    classes = json.load(open(os.path.join(MODEL_DIR, 'labels.json')))
    probs = []
    with torch.no_grad():
        for i in range(0, len(texts), 32):
            enc = tok(texts[i:i + 32], truncation=True, max_length=256, padding=True, return_tensors='pt')
            probs.append(torch.softmax(mdl(**enc).logits, -1).numpy())
    return np.vstack(probs), np.array(classes)


def run():
    c = read_table('candidates')
    if os.path.exists(os.path.join(MODEL_DIR, 'config.json')):
        name = 'student_hf'
        P, classes = predict_hf(c.snippet.tolist())
        metrics = json.load(open(os.path.join(MODEL_DIR, 'metrics.json'))) if os.path.exists(os.path.join(MODEL_DIR, 'metrics.json')) else {}
        labeller, where = os.path.basename(json.load(open(os.path.join(MODEL_DIR, 'config.json'))).get('_name_or_path', 'fine-tuned')), 'local_laptop'
    else:
        name = 'student_tfidf_baseline'
        model, classes, metrics = baseline()
        P = model.predict_proba(c.snippet)
        classes = model.classes_
        labeller, where = 'tfidf+logreg (pilot vote, 240 posts)', 'local_laptop'
    top = P.argmax(1)
    header = {'_run': {'run_id': name, 'labeller': labeller, 'kind': 'student', 'runs_where': where, 'task': 'project',
                       'prompt_version': None, 'codebook_version': 'v1', 'codebook_sha': codebook_sha(), 'params': metrics}}
    with open(os.path.join(RUNS, f'{name}.jsonl'), 'w', encoding='utf-8') as f:
        f.write(json.dumps(header, ensure_ascii=False) + '\n')
        for pid, k, row in zip(c.post_id, top, P):
            f.write(json.dumps({'post_id': pid, 'project': str(classes[k]), 'project_prob': round(float(row[k]), 4),
                                'stance': None, 'voice': None, 'arguments': [], 'abstain': False}) + '\n')
    jdump(metrics, os.path.join(DATA, f'{name}_metrics.json'))
    log('student', f"{name}: {metrics} ; predicted {len(c):,} candidates: {pd.Series(classes[top]).value_counts().to_dict()}")


if __name__ == '__main__':
    run()
