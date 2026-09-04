"""Posting-time channel (SPEC.md §9).

S_time = 1 − Jensen-Shannon(hour-of-day histograms). Aliases with fewer than
20 timestamped posts get S_time = NULL — not 0, which would mean 'maximally
different schedules'. Fusion (Prompt 07) must impute and set time_missing.

Timezone estimate is a weak indicator from the circular mean of posting
hours (evening-peak UTC-offset hypothesis). It is never a location claim.
"""

from __future__ import annotations

import json
import math
import sqlite3
from datetime import datetime
from pathlib import Path

import numpy as np
from scipy.spatial.distance import jensenshannon

MIN_TS = 20
# Evening-peak hypothesis: forum use concentrates near 20:00 local.
LOCAL_PEAK_HOUR = 20.0

ALIAS_ACTIVITY_SCHEMA = """
CREATE TABLE IF NOT EXISTS alias_activity (
  alias_id INTEGER PRIMARY KEY,
  n_ts INTEGER NOT NULL,
  hour_hist TEXT NOT NULL,
  dow_hist TEXT NOT NULL,
  mean_hour_utc REAL,
  tz_offset_hours REAL,
  tz_regions TEXT,
  tz_confidence REAL
);
"""

# Closed-open UTC offset bands → coarse region labels (hypothesis only).
_REGIONS = (
    (-12.0, -6.5, "Americas (Pacific / Alaska band)"),
    (-6.5, -3.0, "Americas (Central / Eastern band)"),
    (-3.0, 1.5, "Europe / Africa (near UTC)"),
    (1.5, 6.5, "Middle East / South Asia band"),
    (6.5, 12.5, "East Asia / Australia band"),
)


def parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def hour_histogram(hours: list[int]) -> np.ndarray:
    hist = np.zeros(24, dtype=np.float64)
    for h in hours:
        hist[int(h) % 24] += 1
    total = hist.sum()
    if total <= 0:
        return hist
    return hist / total


def dow_histogram(dows: list[int]) -> np.ndarray:
    hist = np.zeros(7, dtype=np.float64)
    for d in dows:
        hist[int(d) % 7] += 1
    total = hist.sum()
    if total <= 0:
        return hist
    return hist / total


def s_time(hist_a: np.ndarray | None, hist_b: np.ndarray | None) -> float | None:
    """1 − JS(hour hists). None if either alias is below the timestamp floor."""
    if hist_a is None or hist_b is None:
        return None
    if hist_a.sum() <= 0 or hist_b.sum() <= 0:
        return None
    js = float(jensenshannon(hist_a, hist_b, base=2.0))
    if math.isnan(js):
        return None
    return 1.0 - js


def circular_mean_hour(hours: list[int]) -> tuple[float, float]:
    """Mean hour on a 24h circle and resultant length R in [0, 1] (confidence)."""
    ang = np.asarray(hours, dtype=np.float64) * (2.0 * math.pi / 24.0)
    c, s = float(np.mean(np.cos(ang))), float(np.mean(np.sin(ang)))
    r = math.hypot(c, s)
    mean = (math.atan2(s, c) % (2.0 * math.pi)) * 24.0 / (2.0 * math.pi)
    return mean, r


def tz_offset_from_mean_hour(mean_hour_utc: float) -> float:
    """UTC offset that would place the circular mean at LOCAL_PEAK_HOUR local."""
    return (LOCAL_PEAK_HOUR - mean_hour_utc + 12.0) % 24.0 - 12.0


def regions_for_offset(offset: float) -> str:
    for lo, hi, label in _REGIONS:
        if lo <= offset < hi:
            return label
    return "unspecified band"


def timezone_estimate(hours: list[int]) -> dict | None:
    if len(hours) < MIN_TS:
        return None
    mean_hour, conf = circular_mean_hour(hours)
    offset = tz_offset_from_mean_hour(mean_hour)
    return {
        "mean_hour_utc": mean_hour,
        "tz_offset_hours": offset,
        "tz_regions": regions_for_offset(offset),
        "tz_confidence": conf,
        "n_ts": len(hours),
        "wording": (
            f"Weak indicator (concentration R={conf:.2f} on {len(hours)} timestamps): "
            f"UTC posting mass centres near {mean_hour:.1f}h. Under an evening-peak "
            f"(~{LOCAL_PEAK_HOUR:.0f}:00 local) hypothesis that implies UTC{offset:+.0f} "
            f"— candidate region: {regions_for_offset(offset)}. Not a location claim."
        ),
    }


def build_alias_activity(conn: sqlite3.Connection) -> dict[int, dict]:
    hours: dict[int, list[int]] = {}
    dows: dict[int, list[int]] = {}
    cur = conn.execute(
        """
        SELECT a.id AS alias_id, p.ts
        FROM posts p
        JOIN aliases a ON a.market = p.market AND a.alias = p.alias
        WHERE p.ts IS NOT NULL AND p.ts != ''
        """
    )
    for row in cur:
        dt = parse_ts(row["ts"])
        if dt is None:
            continue
        hours.setdefault(row["alias_id"], []).append(dt.hour)
        dows.setdefault(row["alias_id"], []).append(dt.weekday())
    out: dict[int, dict] = {}
    for aid, hs in hours.items():
        n = len(hs)
        hh = hour_histogram(hs)
        dh = dow_histogram(dows.get(aid, []))
        rec = {
            "n_ts": n,
            "hour_hist": hh if n >= MIN_TS else None,
            "dow_hist": dh if n >= MIN_TS else None,
            "hours": hs,
        }
        rec["tz"] = timezone_estimate(hs)
        out[aid] = rec
    return out


def persist_activity(db_path: str | Path, activity: dict[int, dict]) -> None:
    rows = []
    for aid, rec in activity.items():
        tz = rec.get("tz") or {}
        hh = rec["hour_hist"] if rec["hour_hist"] is not None else hour_histogram(rec["hours"])
        dh = rec["dow_hist"] if rec["dow_hist"] is not None else np.zeros(7)
        rows.append(
            (
                aid,
                rec["n_ts"],
                json.dumps(hh.tolist()),
                json.dumps(dh.tolist()),
                tz.get("mean_hour_utc"),
                tz.get("tz_offset_hours"),
                tz.get("tz_regions"),
                tz.get("tz_confidence"),
            )
        )
    with sqlite3.connect(db_path) as conn:
        conn.executescript(ALIAS_ACTIVITY_SCHEMA)
        conn.execute("DELETE FROM alias_activity")
        conn.executemany(
            """
            INSERT INTO alias_activity (
              alias_id, n_ts, hour_hist, dow_hist,
              mean_hour_utc, tz_offset_hours, tz_regions, tz_confidence
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        conn.commit()


def persist_s_time(
    db_path: str | Path,
    pairs: list[tuple[int, int]],
    activity: dict[int, dict],
) -> dict:
    scores: list[tuple[int, int, float | None]] = []
    n_null = 0
    n_val = 0
    for a, b in pairs:
        ha = (activity.get(a) or {}).get("hour_hist")
        hb = (activity.get(b) or {}).get("hour_hist")
        val = s_time(ha, hb)
        if val is None:
            n_null += 1
        else:
            n_val += 1
        scores.append((a, b, val))
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS pair_channel_scores (
              a_alias_id INTEGER NOT NULL,
              b_alias_id INTEGER NOT NULL,
              s_embed REAL,
              s_time REAL,
              PRIMARY KEY (a_alias_id, b_alias_id)
            );
            """
        )
        sql = """
            INSERT INTO pair_channel_scores (a_alias_id, b_alias_id, s_embed, s_time)
            VALUES (?, ?, NULL, ?)
            ON CONFLICT (a_alias_id, b_alias_id) DO UPDATE SET s_time = excluded.s_time
            """
        for start in range(0, len(scores), 50_000):
            conn.executemany(sql, scores[start : start + 50_000])
            conn.commit()
    return {"n_s_time": n_val, "n_s_time_null": n_null}


def run(db_path: str | Path) -> dict:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        activity = build_alias_activity(conn)
        pairs = [
            (r["a_alias_id"], r["b_alias_id"])
            for r in conn.execute("SELECT a_alias_id, b_alias_id FROM char_candidates")
        ]
        n_ge20 = sum(1 for r in activity.values() if r["n_ts"] >= MIN_TS)
        n_lt20 = sum(1 for r in activity.values() if r["n_ts"] < MIN_TS)
    persist_activity(db_path, activity)
    time_stats = persist_s_time(db_path, pairs, activity)
    return {
        "n_aliases_with_ts": len(activity),
        "n_aliases_s_time_eligible": n_ge20,
        "n_aliases_s_time_null": n_lt20,
        "activity": activity,
        **time_stats,
    }


def main(argv: list[str] | None = None) -> int:
    import argparse

    import yaml

    parser = argparse.ArgumentParser(description="Temporal S_time + weak TZ indicator")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--db", default=None)
    args = parser.parse_args(argv)
    with open(args.config, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    db_path = args.db or cfg["paths"]["sqlite_db"]
    summary = run(db_path)
    print("temporal activity")
    for k in (
        "n_aliases_with_ts",
        "n_aliases_s_time_eligible",
        "n_aliases_s_time_null",
        "n_s_time",
        "n_s_time_null",
    ):
        print(f"  {k}: {summary[k]}")
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        samples = conn.execute(
            """
            SELECT a.alias AS a, b.alias AS b, p.s_time, xa.n_ts AS n_a, xb.n_ts AS n_b
            FROM pair_channel_scores p
            JOIN aliases a ON a.id = p.a_alias_id
            JOIN aliases b ON b.id = p.b_alias_id
            JOIN alias_activity xa ON xa.alias_id = p.a_alias_id
            JOIN alias_activity xb ON xb.alias_id = p.b_alias_id
            WHERE p.s_time IS NOT NULL
            ORDER BY p.s_time DESC
            LIMIT 3
            """
        ).fetchall()
        print("  S_time samples (eligible pairs):")
        for r in samples:
            print(
                f"    {r['a']!r}/{r['b']!r}: {r['s_time']:.4f} "
                f"(n_ts {r['n_a']}, {r['n_b']})"
            )
        missing = conn.execute(
            """
            SELECT al.alias, al.market, x.n_ts
            FROM alias_activity x
            JOIN aliases al ON al.id = x.alias_id
            WHERE x.n_ts < ?
            ORDER BY x.n_ts
            LIMIT 1
            """,
            (MIN_TS,),
        ).fetchone()
        if missing:
            print(
                f"  S_time NULL path: {missing['alias']!r}@{missing['market']} "
                f"n_ts={missing['n_ts']} (<{MIN_TS})"
            )
        tz_rows = conn.execute(
            """
            SELECT al.alias, al.market, x.n_ts, x.mean_hour_utc,
                   x.tz_offset_hours, x.tz_regions, x.tz_confidence
            FROM alias_activity x
            JOIN aliases al ON al.id = x.alias_id
            WHERE x.n_ts >= ? AND x.tz_confidence IS NOT NULL
            ORDER BY x.tz_confidence DESC
            LIMIT 2
            """,
            (MIN_TS,),
        ).fetchall()
        print("  timezone estimates (weak indicators):")
        for r in tz_rows:
            print(
                f"    {r['alias']!r}@{r['market']}: "
                f"Weak indicator (concentration R={r['tz_confidence']:.2f} "
                f"on {r['n_ts']} timestamps): UTC posting mass centres near "
                f"{r['mean_hour_utc']:.1f}h. Evening-peak hypothesis implies "
                f"UTC{r['tz_offset_hours']:+.0f} — candidate region: "
                f"{r['tz_regions']}. Not a location claim."
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
