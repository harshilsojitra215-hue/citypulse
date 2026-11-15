-- Production path for the city: PostgreSQL 16 + pgvector. Same tables and columns as CONTRACT.md.
-- Tonight we use DuckDB (one file, no server, zero setup risk on stage). This file is the in-house version.
-- Load from the parquet files with any loader (e.g. duckdb's postgres extension or pandas.to_sql).

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE posts (
  post_id text PRIMARY KEY, published_at timestamptz NOT NULL, day date, week date,
  media_type text, platform text, source text, url text, language text, country_code text,
  title text, text text, text_len int, is_paywall_stub boolean, is_truncated boolean,
  vendor_sentiment smallint, engagements bigint, reach double precision, has_author boolean,
  origin text CHECK (origin IN ('dataset','live')), new_since_dataset boolean, ingested_at timestamptz
);
CREATE INDEX ON posts (week);

CREATE TABLE clusters (post_id text PRIMARY KEY REFERENCES posts, cluster_id text, cluster_size int, n_outlets int, is_representative boolean);

CREATE TABLE candidates (post_id text PRIMARY KEY REFERENCES posts, project_hint text, rule_hits text, by_rule boolean,
  by_embedding boolean, emb_score double precision, snippet text, n_mentions int);

CREATE TABLE label_runs (run_id text PRIMARY KEY, created_at timestamptz, labeller text, kind text, runs_where text, task text,
  prompt_version text, codebook_version text, codebook_sha text, params jsonb, n_items int);

-- labels are append-only: a new run gets a new run_id, nothing is overwritten
CREATE TABLE labels (run_id text REFERENCES label_runs, post_id text, project text, project_prob double precision,
  stance text, stance_probs jsonb, voice text, arguments jsonb, evidence text, abstain boolean, PRIMARY KEY (run_id, post_id));

CREATE TABLE human_labels (post_id text, annotator text, project text, stance text, voice text, arguments jsonb, saved_at text);

CREATE TABLE labels_final (post_id text PRIMARY KEY, project text, stance text, voice text, arguments jsonb, n_runs int,
  agreement_project double precision, agreement_stance double precision, confidence text, abstain boolean,
  label_source text, student_project text, student_prob double precision);

CREATE TABLE faq (faq_id text PRIMARY KEY, project text, question text, question_en text, answer_summary text, topic text,
  argument_code text, source_url text, date_seen text, official_figures jsonb);
CREATE TABLE faq_matches (post_id text, faq_id text, match_type text, score double precision, post_value text,
  official_value text, matched_text text, method text, checked boolean, figure_id text);

CREATE TABLE events (event_id text PRIMARY KEY, date date, project text, type text, title text, source_url text,
  evidence_post_id text, after_dataset boolean);
CREATE TABLE peaks (project text, week date, stories int, baseline double precision, p_value double precision,
  q_value double precision, is_peak boolean, weak boolean, linked_event_id text, PRIMARY KEY (project, week));

CREATE TABLE metrics (metric_id text, project text, voice text, name text, value double precision, ci_low double precision,
  ci_high double precision, n int, method text, source_run_ids text, computed_at timestamptz);

-- for "ask the debate" retrieval later: one embedding per snippet (BGE-M3 dense = 1024 dims)
CREATE TABLE embeddings (post_id text PRIMARY KEY REFERENCES posts, model text, embedding vector(1024));
CREATE INDEX ON embeddings USING hnsw (embedding vector_cosine_ops);
