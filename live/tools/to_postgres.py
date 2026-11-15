"""Copy a collector SQLite store into PostgreSQL (schema live.*, see live/sql/schema_postgres.sql).

  pip install "psycopg[binary]"
  python -I -X utf8 live/tools/to_postgres.py --db live/data/live_radar_v2.db --dsn postgresql://user@localhost:5432/citypulse

Idempotent: rows are upserted on their keys, so running it twice gives the same tables. At the end it compares row
counts per table and exits 1 if any differ. The DSN is read from --dsn or the env var CITYPULSE_PG_DSN; it is never printed.
"""
import argparse
import os
import sqlite3
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCHEMA = os.path.join(os.path.dirname(HERE), 'sql', 'schema_postgres.sql')
TABLES = {'items': ['key'], 'item_versions': ['key', 'version_no'], 'sightings': ['key', 'source', 'project', 'run_id'],
          'page_snapshots': None}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--db', required=True)
    ap.add_argument('--dsn', default=os.environ.get('CITYPULSE_PG_DSN'))
    a = ap.parse_args(argv)
    if not a.dsn:
        sys.exit('no --dsn and no CITYPULSE_PG_DSN')
    import psycopg
    src = sqlite3.connect(a.db)
    with psycopg.connect(a.dsn) as pg:
        pg.execute(open(SCHEMA, encoding='utf-8').read())
        bad = 0
        for t, pk in TABLES.items():
            cols = [r[1] for r in src.execute(f'PRAGMA table_info({t})')]
            rows = src.execute(f'SELECT {", ".join(cols)} FROM {t}').fetchall()
            ph = ', '.join(['%s'] * len(cols))
            if pk:
                upd = ', '.join(f'{c} = EXCLUDED.{c}' for c in cols if c not in pk)
                sql = f'INSERT INTO live.{t} ({", ".join(cols)}) VALUES ({ph}) ON CONFLICT ({", ".join(pk)}) DO UPDATE SET {upd}'
            else:   # page snapshots have no key: replace the table
                pg.execute(f'DELETE FROM live.{t}')
                sql = f'INSERT INTO live.{t} ({", ".join(cols)}) VALUES ({ph})'
            with pg.cursor() as cur:
                cur.executemany(sql, rows)
            n_pg = pg.execute(f'SELECT count(*) FROM live.{t}').fetchone()[0]
            ok = n_pg == len(rows)
            bad += not ok
            print(f'{t:15} sqlite={len(rows):6} postgres={n_pg:6} {"OK" if ok else "DIFFERENT"}')
        pg.commit()
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
