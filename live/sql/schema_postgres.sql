-- Collector store, production path for the city: PostgreSQL 16 (same server as the team's pipeline/sql/schema_postgres.sql).
-- Today the collector writes one SQLite file (live/data/*.db): no server, no setup risk on stage. Same tables and columns
-- as live/collector/core.py Store; live/tests/test_postgres_schema.py fails if the two drift apart.
-- Copy an existing SQLite store into PostgreSQL: python -I -X utf8 live/tools/to_postgres.py --db live/data/live_radar_v2.db --dsn postgresql://...
-- Times stay ISO 8601 text, exactly as the collector writes them (UTC); cast with ::timestamptz in queries.

CREATE SCHEMA IF NOT EXISTS live;

-- one row per item (key = sha1 of the canonical URL); the newest version of its text
CREATE TABLE IF NOT EXISTS live.items (
  key text PRIMARY KEY, mention_id text, url text, canonical_url text, content_hash text, title_key text,
  dup_of text, source text, projects text, title text, text text, published_at text, source_name text,
  language text, country text, media_type text, author_hash text, engagements integer,
  source_terms text, retrieved_at text, first_seen text, query text,
  title_hit integer DEFAULT 1, kind text, modified_at text, version_no integer DEFAULT 1,
  first_run_id text, last_changed_at text, last_changed_run_id text,
  text_scope text, date_known integer DEFAULT 1, radar_match text,
  date_source text  -- where a recovered date came from (collector/dates.py); NULL = the source gave it
);
CREATE INDEX IF NOT EXISTS ix_items_title_key ON live.items (title_key);
CREATE INDEX IF NOT EXISTS ix_items_first_seen ON live.items (first_seen);

-- append only: every text an item ever had
CREATE TABLE IF NOT EXISTS live.item_versions (
  key text, version_no integer, content_hash text, title text, text text, seen_at text, run_id text,
  PRIMARY KEY (key, version_no)
);

-- every time a source returned an item (which source, project, query, run)
CREATE TABLE IF NOT EXISTS live.sightings (
  key text, source text, project text, query text, seen_at text, run_id text
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_sight ON live.sightings (key, source, project, run_id);

-- official page monitor
CREATE TABLE IF NOT EXISTS live.page_snapshots (
  page_id text, fetched_at text, url text, content_hash text, text text
);
