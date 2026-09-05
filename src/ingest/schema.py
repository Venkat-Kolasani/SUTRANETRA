"""SQLite schema for SUTRANETRA — idempotent init (SPEC.md §6)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA_SQL = """
-- Corpus (shared; posts carry immutable source lineage)
CREATE TABLE IF NOT EXISTS posts (
  id INTEGER PRIMARY KEY,
  market TEXT NOT NULL,
  msg_id INTEGER NOT NULL,
  alias TEXT NOT NULL,
  user_id INTEGER,
  thread_id INTEGER,
  subject TEXT,
  ts TEXT,
  body TEXT NOT NULL,
  raw_html TEXT NOT NULL,
  membergroup TEXT,
  postcount INTEGER,
  karma_pos INTEGER,
  karma_neg INTEGER,
  onion_host TEXT,
  source_archive TEXT NOT NULL,
  scrape_date TEXT NOT NULL,
  source_member_path TEXT NOT NULL,
  content_sha256 TEXT NOT NULL,
  UNIQUE(market, msg_id)
);
CREATE INDEX IF NOT EXISTS idx_posts_alias ON posts(market, alias);
CREATE INDEX IF NOT EXISTS idx_posts_content_hash ON posts(content_sha256);
CREATE INDEX IF NOT EXISTS idx_posts_source ON posts(source_archive, scrape_date);

CREATE TABLE IF NOT EXISTS aliases (
  id INTEGER PRIMARY KEY,
  market TEXT NOT NULL,
  alias TEXT NOT NULL,
  n_posts INTEGER,
  first_seen TEXT,
  last_seen TEXT,
  is_vendor INTEGER DEFAULT 0,
  UNIQUE(market, alias)
);

CREATE TABLE IF NOT EXISTS evidence (
  id INTEGER PRIMARY KEY,
  alias_id INTEGER REFERENCES aliases(id),
  post_id INTEGER REFERENCES posts(id),
  kind TEXT NOT NULL,
  value TEXT NOT NULL,
  context TEXT
);
CREATE INDEX IF NOT EXISTS idx_evidence_value ON evidence(kind, value);

-- Investigation runs
CREATE TABLE IF NOT EXISTS cases (
  case_id TEXT PRIMARY KEY,
  created_at TEXT NOT NULL,
  corpus_snapshot TEXT NOT NULL,
  config_hash TEXT NOT NULL,
  model_version TEXT NOT NULL,
  threshold REAL NOT NULL,
  status TEXT NOT NULL,
  report_path TEXT,
  error TEXT
);

CREATE TABLE IF NOT EXISTS pair_scores (
  case_id TEXT NOT NULL REFERENCES cases(case_id),
  a_alias_id INTEGER NOT NULL,
  b_alias_id INTEGER NOT NULL,
  s_char REAL,
  s_embed REAL,
  s_hard REAL,
  s_time REAL,
  n_shared_hard INTEGER,
  confidence REAL,
  label INTEGER,
  reason TEXT,
  PRIMARY KEY (case_id, a_alias_id, b_alias_id)
);

CREATE TABLE IF NOT EXISTS clusters (
  case_id TEXT NOT NULL REFERENCES cases(case_id),
  cluster_id INTEGER NOT NULL,
  alias_id INTEGER NOT NULL REFERENCES aliases(id),
  confidence REAL,
  PRIMARY KEY (case_id, cluster_id, alias_id)
);

CREATE TABLE IF NOT EXISTS opsec_findings (
  id INTEGER PRIMARY KEY,
  case_id TEXT NOT NULL REFERENCES cases(case_id),
  target TEXT NOT NULL,
  finding_kind TEXT NOT NULL,
  value TEXT NOT NULL,
  detail TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_opsec_case ON opsec_findings(case_id);
"""

EXPECTED_TABLES = (
    "posts",
    "aliases",
    "evidence",
    "cases",
    "pair_scores",
    "clusters",
    "opsec_findings",
)


def _migrate_pair_scores_reason(conn: sqlite3.Connection) -> None:
    """Existing DBs created before Prompt 12 lack pair_scores.reason."""
    cols = {row[1] for row in conn.execute("PRAGMA table_info(pair_scores)")}
    if cols and "reason" not in cols:
        conn.execute("ALTER TABLE pair_scores ADD COLUMN reason TEXT")


def init_db(db_path: str | Path) -> Path:
    """Create parent dirs and apply schema. Safe to call multiple times."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.executescript(SCHEMA_SQL)
        _migrate_pair_scores_reason(conn)
    return path


def list_schema(db_path: str | Path) -> list[tuple[str, str, str, int, str, int]]:
    """Return sqlite_master rows for tables (for verification)."""
    with sqlite3.connect(db_path) as conn:
        return conn.execute(
            "SELECT * FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()


def list_columns(db_path: str | Path, table: str) -> list[tuple]:
    with sqlite3.connect(db_path) as conn:
        return conn.execute(f"PRAGMA table_info({table})").fetchall()


if __name__ == "__main__":
    import argparse
    import yaml

    parser = argparse.ArgumentParser(description="Initialize SUTRANETRA SQLite schema")
    parser.add_argument(
        "--config",
        default="config.yaml",
        help="Path to config.yaml (default: config.yaml)",
    )
    parser.add_argument(
        "--db",
        default=None,
        help="Override SQLite path (default: paths.sqlite_db from config)",
    )
    args = parser.parse_args()

    with open(args.config, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    db_path = args.db or cfg["paths"]["sqlite_db"]
    init_db(db_path)
    print(f"Schema initialized: {db_path}")
    print("\nTables:")
    for row in list_schema(db_path):
        if row[1] in EXPECTED_TABLES:
            print(f"  {row[1]}")
    print("\nposts columns:")
    for col in list_columns(db_path, "posts"):
        print(f"  {col[1]} ({col[2]})")
    print("\npair_scores columns:")
    for col in list_columns(db_path, "pair_scores"):
        print(f"  {col[1]} ({col[2]})")
