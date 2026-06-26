"""SQLite data access for Reel Together.

One household, one database. The schema holds:

* ``users``      — one row per Home Assistant user that has opened the app.
* ``titles``     — the shared catalog of movies / shows the household added.
* ``interests``  — each user's status (want / watching / watched / skip) and
                   optional 1–5 rating for a title.
* ``activity``   — a lightweight feed of what happened, for the "together" feel.

Connections are per-thread (waitress serves on a thread pool) and WAL mode is
enabled so reads and writes don't block each other.
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from typing import Optional

from . import config

_LOCAL = threading.local()

VALID_STATUSES = ("want", "watching", "watched", "skip")

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS users (
    id            TEXT PRIMARY KEY,
    username      TEXT,
    display_name  TEXT NOT NULL,
    created_at    REAL NOT NULL,
    last_seen     REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS titles (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    type        TEXT NOT NULL DEFAULT 'unknown',
    title       TEXT NOT NULL,
    year        INTEGER,
    overview    TEXT,
    poster_url  TEXT,
    service     TEXT,
    seasons          INTEGER,
    episodes_total   INTEGER,
    episodes_watched INTEGER NOT NULL DEFAULT 0,
    source      TEXT NOT NULL,
    source_id   TEXT NOT NULL,
    source_url  TEXT,
    extra       TEXT,
    added_by    TEXT,
    added_at    REAL NOT NULL,
    UNIQUE(source, source_id),
    FOREIGN KEY(added_by) REFERENCES users(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS interests (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    TEXT NOT NULL,
    title_id   INTEGER NOT NULL,
    status     TEXT NOT NULL CHECK(status IN ('want','watching','watched','skip')),
    rating     INTEGER CHECK(rating BETWEEN 1 AND 5),
    updated_at REAL NOT NULL,
    UNIQUE(user_id, title_id),
    FOREIGN KEY(user_id)  REFERENCES users(id)  ON DELETE CASCADE,
    FOREIGN KEY(title_id) REFERENCES titles(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS activity (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    TEXT,
    title_id   INTEGER,
    action     TEXT NOT NULL,
    detail     TEXT,
    created_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_interests_title ON interests(title_id);
CREATE INDEX IF NOT EXISTS idx_interests_user  ON interests(user_id);
CREATE INDEX IF NOT EXISTS idx_activity_created ON activity(created_at DESC);
"""


def get_db() -> sqlite3.Connection:
    conn = getattr(_LOCAL, "conn", None)
    if conn is None:
        conn = sqlite3.connect(config.DB_PATH, timeout=30, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=30000;")
        conn.execute("PRAGMA foreign_keys=ON;")
        _LOCAL.conn = conn
    return conn


def init_db() -> None:
    os.makedirs(os.path.dirname(os.path.abspath(config.DB_PATH)), exist_ok=True)
    get_db().executescript(SCHEMA)
    _migrate()


def _migrate() -> None:
    """Add columns introduced after 0.1.0 to an existing titles table."""
    conn = get_db()
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(titles)")}
    additions = {
        "service": "TEXT",
        "seasons": "INTEGER",
        "episodes_total": "INTEGER",
        "episodes_watched": "INTEGER NOT NULL DEFAULT 0",
    }
    for name, decl in additions.items():
        if name not in cols:
            conn.execute(f"ALTER TABLE titles ADD COLUMN {name} {decl}")


def _now() -> float:
    return time.time()


# --- Users -----------------------------------------------------------------
def upsert_user(uid: str, username: Optional[str], display_name: str) -> dict:
    conn = get_db()
    now = _now()
    conn.execute(
        """INSERT INTO users (id, username, display_name, created_at, last_seen)
           VALUES (?,?,?,?,?)
           ON CONFLICT(id) DO UPDATE SET
             username=excluded.username,
             display_name=excluded.display_name,
             last_seen=excluded.last_seen""",
        (uid, username, display_name, now, now),
    )
    return dict(conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone())


def list_users() -> list[dict]:
    rows = get_db().execute("SELECT * FROM users ORDER BY display_name COLLATE NOCASE")
    return [dict(r) for r in rows]


def count_users() -> int:
    return get_db().execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]


# --- Titles ----------------------------------------------------------------
def add_title(data: dict, added_by: str) -> dict:
    """Insert a title into the shared catalog (idempotent on source+source_id)."""
    conn = get_db()
    extra = json.dumps(data.get("extra") or {})
    conn.execute(
        """INSERT INTO titles
             (type,title,year,overview,poster_url,service,seasons,episodes_total,
              source,source_id,source_url,extra,added_by,added_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(source, source_id) DO NOTHING""",
        (
            data.get("type", "unknown"),
            data["title"],
            data.get("year"),
            data.get("overview"),
            data.get("poster_url"),
            data.get("service"),
            data.get("seasons"),
            data.get("episodes_total"),
            data["source"],
            str(data["source_id"]),
            data.get("source_url"),
            extra,
            added_by,
            _now(),
        ),
    )
    row = conn.execute(
        "SELECT * FROM titles WHERE source=? AND source_id=?",
        (data["source"], str(data["source_id"])),
    ).fetchone()
    return dict(row)


def get_title(title_id: int) -> Optional[dict]:
    row = get_db().execute("SELECT * FROM titles WHERE id=?", (title_id,)).fetchone()
    return dict(row) if row else None


def update_title(title_id: int, fields: dict) -> Optional[dict]:
    if not fields:
        return get_title(title_id)
    allowed = {
        "type", "title", "year", "overview", "poster_url", "source_url", "extra",
        "service", "seasons", "episodes_total", "episodes_watched",
    }
    sets, params = [], []
    for key, val in fields.items():
        if key not in allowed:
            continue
        if key == "extra" and not isinstance(val, str):
            val = json.dumps(val or {})
        sets.append(f"{key}=?")
        params.append(val)
    if not sets:
        return get_title(title_id)
    params.append(title_id)
    get_db().execute(f"UPDATE titles SET {', '.join(sets)} WHERE id=?", params)
    return get_title(title_id)


def remove_title(title_id: int) -> None:
    get_db().execute("DELETE FROM titles WHERE id=?", (title_id,))


def _hydrate_interests(conn) -> dict[int, list[dict]]:
    rows = conn.execute(
        """SELECT i.title_id, i.user_id, i.status, i.rating, u.display_name
           FROM interests i JOIN users u ON u.id = i.user_id"""
    ).fetchall()
    by_title: dict[int, list[dict]] = {}
    for r in rows:
        by_title.setdefault(r["title_id"], []).append(dict(r))
    return by_title


def list_titles(
    current_user_id: str,
    status: Optional[str] = None,
    type_: Optional[str] = None,
    q: Optional[str] = None,
) -> list[dict]:
    conn = get_db()
    titles = [dict(r) for r in conn.execute("SELECT * FROM titles ORDER BY added_at DESC")]
    by_title = _hydrate_interests(conn)
    out = []
    for t in titles:
        t["extra"] = json.loads(t["extra"]) if t.get("extra") else {}
        ints = by_title.get(t["id"], [])
        t["interests"] = ints
        t["want_count"] = sum(1 for x in ints if x["status"] == "want")
        t["watched_count"] = sum(1 for x in ints if x["status"] == "watched")
        mine = next((x for x in ints if x["user_id"] == current_user_id), None)
        t["my_status"] = mine["status"] if mine else None
        t["my_rating"] = mine["rating"] if mine else None
        out.append(t)

    if type_:
        out = [t for t in out if t["type"] == type_]
    if status:
        out = [t for t in out if t["my_status"] == status]
    if q:
        ql = q.lower()
        out = [t for t in out if ql in (t["title"] or "").lower()]
    return out


def suggestions(min_want: int = 2) -> list[dict]:
    """Titles the household should watch together.

    A title qualifies when at least ``min_want`` people marked it 'want' and
    nobody marked it 'skip'. Ranked by how many people want it.
    """
    rows = get_db().execute(
        """SELECT t.*,
                  SUM(CASE WHEN i.status='want'    THEN 1 ELSE 0 END) AS want_count,
                  SUM(CASE WHEN i.status='skip'    THEN 1 ELSE 0 END) AS skip_count,
                  SUM(CASE WHEN i.status='watched' THEN 1 ELSE 0 END) AS watched_count
           FROM titles t
           LEFT JOIN interests i ON i.title_id = t.id
           GROUP BY t.id
           HAVING want_count >= ? AND skip_count = 0
           ORDER BY want_count DESC, t.added_at DESC""",
        (min_want,),
    ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["extra"] = json.loads(d["extra"]) if d.get("extra") else {}
        out.append(d)
    return out


def titles_needing_enrichment() -> list[int]:
    """Ids of Wikipedia-sourced titles that haven't been TMDB-enriched yet.

    TVmaze and TMDB titles already carry good data, so only Wikipedia entries
    are candidates for enrichment.
    """
    rows = get_db().execute("SELECT id, extra FROM titles WHERE source = 'wikipedia'").fetchall()
    out = []
    for r in rows:
        extra = json.loads(r["extra"]) if r["extra"] else {}
        if not extra.get("enriched"):
            out.append(r["id"])
    return out


def titles_by_source(source: str) -> list[dict]:
    rows = get_db().execute("SELECT * FROM titles WHERE source = ?", (source,)).fetchall()
    return [dict(r) for r in rows]


# --- Interests -------------------------------------------------------------
def set_interest(
    user_id: str,
    title_id: int,
    status: Optional[str] = None,
    rating: Optional[int] = None,
) -> Optional[dict]:
    """Create or update the current user's interest in a title.

    ``status='clear'`` removes the interest entirely. When only a rating is
    supplied, the existing status is preserved (defaulting to 'watched').
    """
    conn = get_db()
    if status == "clear":
        conn.execute("DELETE FROM interests WHERE user_id=? AND title_id=?", (user_id, title_id))
        return None

    existing = conn.execute(
        "SELECT * FROM interests WHERE user_id=? AND title_id=?", (user_id, title_id)
    ).fetchone()

    if status is None:
        new_status = existing["status"] if existing else ("watched" if rating else "want")
    else:
        new_status = status
    new_rating = rating if rating is not None else (existing["rating"] if existing else None)

    conn.execute(
        """INSERT INTO interests (user_id,title_id,status,rating,updated_at)
           VALUES (?,?,?,?,?)
           ON CONFLICT(user_id,title_id) DO UPDATE SET
             status=excluded.status, rating=excluded.rating, updated_at=excluded.updated_at""",
        (user_id, title_id, new_status, new_rating, _now()),
    )
    row = conn.execute(
        "SELECT * FROM interests WHERE user_id=? AND title_id=?", (user_id, title_id)
    ).fetchone()
    return dict(row)


# --- Activity --------------------------------------------------------------
def add_activity(user_id: Optional[str], title_id: Optional[int], action: str, detail: Optional[str] = None) -> None:
    get_db().execute(
        "INSERT INTO activity (user_id,title_id,action,detail,created_at) VALUES (?,?,?,?,?)",
        (user_id, title_id, action, detail, _now()),
    )


def list_activity(limit: int = 30) -> list[dict]:
    rows = get_db().execute(
        """SELECT a.*, u.display_name, t.title AS title_name, t.poster_url
           FROM activity a
           LEFT JOIN users  u ON u.id = a.user_id
           LEFT JOIN titles t ON t.id = a.title_id
           ORDER BY a.created_at DESC
           LIMIT ?""",
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]
