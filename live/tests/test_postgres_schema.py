"""The PostgreSQL schema (live/sql/schema_postgres.sql) must have exactly the columns the collector's store writes.
If someone adds a column to Store and forgets the PostgreSQL file, this fails."""
import os
import re
import sys

LIVE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, LIVE)
from collector.core import Store  # noqa: E402

TYPES = {'text', 'integer', 'bigint', 'double', 'boolean', 'timestamptz', 'jsonb'}


def pg_columns():
    sql = open(os.path.join(LIVE, 'sql', 'schema_postgres.sql'), encoding='utf-8').read()
    sql = re.sub(r'--[^\n]*', '', sql)
    out = {}
    for name, body in re.findall(r'CREATE TABLE IF NOT EXISTS live\.(\w+)\s*\((.*?)\);', sql, re.S):
        cols = []
        for part in re.split(r',(?![^()]*\))', body):
            w = part.split()
            if len(w) >= 2 and w[0] != 'PRIMARY' and w[1].lower().rstrip(',') in TYPES:
                cols.append(w[0])
        out[name] = cols
    return out


def test_postgres_schema_matches_store(tmp_path):
    st = Store(str(tmp_path / 's.db'))
    pg = pg_columns()
    for t in ('items', 'item_versions', 'sightings', 'page_snapshots'):
        lite = [r[1] for r in st.db.execute(f'PRAGMA table_info({t})')]
        assert t in pg, f'{t} missing in schema_postgres.sql'
        assert sorted(pg[t]) == sorted(lite), f'{t}: postgres {sorted(set(pg[t]) ^ set(lite))} differ'
