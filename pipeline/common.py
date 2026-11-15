"""Shared helpers: config, paths, codebook values, DuckDB and parquet storage."""
import hashlib
import json
import os
import sys
import time
import tomllib

HERE = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(HERE, 'config.toml'), 'rb') as f:
    CFG = tomllib.load(f)


def path(key):
    return os.path.normpath(os.path.join(HERE, CFG['paths'][key]))


DATA = path('data_dir')
PARQUET = os.path.join(DATA, 'parquet')
EXPORT = os.path.join(DATA, 'export')
RUNS = os.path.join(DATA, 'label_runs')
DB = os.path.join(DATA, 'stadt.duckdb')
for d in (DATA, PARQUET, EXPORT, RUNS):
    os.makedirs(d, exist_ok=True)

# Codebook v1 values (scripts/pilot/codebook.md). Same names as eval/evallib/io.py.
PROJECTS = ['heilbronn_cablecar', 'bonn_cablecar', 'paris_c1', 'ipai', 'other_cablecar', 'irrelevant']
RELEVANT = ['heilbronn_cablecar', 'bonn_cablecar', 'paris_c1', 'ipai']
PROJECT_NAMES = {'heilbronn_cablecar': 'Heilbronn cable car', 'bonn_cablecar': 'Bonn cable car',
                 'paris_c1': 'Paris Câble C1', 'ipai': 'IPAI Heilbronn', 'other_cablecar': 'Other urban cable cars'}
STANCES = ['support', 'oppose', 'neutral_informative', 'mixed', 'unclear']
VOICES = ['news_institutional', 'politician_official', 'citizen', 'company_vendor', 'unclear']
ARGS = ['cost', 'climate_environment', 'traffic_mobility', 'noise_privacy_overflight', 'cityscape_design',
        'safety_technology', 'ipai_who_benefits', 'process_participation', 'tourism_image', 'other']

DATASET_END = CFG['dataset']['end_utc']


def codebook_sha():
    with open(path('codebook'), 'rb') as f:
        return hashlib.sha256(f.read()).hexdigest()[:12]


def log(stage, msg):
    print(f"[{time.strftime('%H:%M:%S')}] {stage}: {msg}", flush=True)


# ---------- storage: parquet files are the truth, DuckDB is a view over them ----------

def write_table(name, df):
    """Write a pandas DataFrame as parquet and (re)load it into DuckDB."""
    p = os.path.join(PARQUET, f'{name}.parquet')
    df.to_parquet(p, index=False)
    try:
        import duckdb
        con = duckdb.connect(DB)
        con.execute(f'CREATE OR REPLACE TABLE {name} AS SELECT * FROM read_parquet(?)', [p])
        con.close()
    except ImportError:
        pass  # parquet alone is enough; DuckDB is a convenience
    return p


def read_table(name, columns=None):
    import pandas as pd
    p = os.path.join(PARQUET, f'{name}.parquet')
    if not os.path.exists(p):
        return None
    return pd.read_parquet(p, columns=columns)


def sql(query, params=None):
    """Run a query on the DuckDB file and return a DataFrame (for checks and notebooks)."""
    import duckdb
    con = duckdb.connect(DB, read_only=True)
    try:
        return con.execute(query, params or []).df()
    finally:
        con.close()


def eval_lib():
    """Import eval/evallib (owned by the eval session) without copying it."""
    p = path('eval_lib')
    if os.path.isdir(os.path.join(p, 'evallib')):
        if p not in sys.path:
            sys.path.insert(0, p)
        import evallib  # noqa: F401
        return evallib
    return None


def jdump(obj, p):
    with open(p, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, indent=1, default=str)
