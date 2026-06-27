"""Flask application for Reel Together.

A small JSON API plus the single-page front-end. Runs behind Home Assistant
ingress on port 8099, served by waitress in production. Authentication is
handled by Home Assistant; we read the forwarded user identity in ``auth``.
"""
from __future__ import annotations

import logging
import re

from flask import Flask, abort, g, jsonify, render_template, request

from . import __version__ as VERSION
from . import airing, auth, config, db, enrich
from .providers import combined_search, provider_for_source

log = logging.getLogger("reel_together")

# The design's "Finished" column maps to the 'watched' status.
STATUS_ALIASES = {"finished": "watched"}


def _norm_status(status):
    if status is None:
        return None
    return STATUS_ALIASES.get(status, status)


_QUERY_YEAR = re.compile(r"\s*\((\d{4})\)\s*$")


def _parse_query(q: str):
    """Split 'Title (Year)' into (title, year); year is optional."""
    m = _QUERY_YEAR.search(q)
    if m:
        return q[: m.start()].strip(), int(m.group(1))
    return q, None


def _best_match(results, year):
    """Top search result, preferring one whose year matches when given."""
    if not results:
        return None
    if year:
        for r in results:
            if r.year == year:
                return r
    return results[0]


def create_app() -> Flask:
    app = Flask(__name__)
    db.init_db()
    enrich.start()  # background TMDB enrichment (no-op without a key)
    airing.start()  # keep TVmaze 'next episode' dates fresh

    # ----------------------------------------------------------------- guard
    @app.before_request
    def _guard_and_identify():
        remote = request.remote_addr or ""
        allowed = (
            remote == config.INGRESS_IP
            or remote.startswith("127.")
            or remote in ("::1", "localhost")
            or config.ALLOW_DIRECT_ACCESS
        )
        if not allowed:
            abort(403)
        g.base_path = auth.ingress_base(request)
        if request.endpoint != "static":
            g.user = auth.current_user(request)

    # ------------------------------------------------------------- helpers
    def _hydrated(title_id: int):
        for t in db.list_titles(g.user["id"]):
            if t["id"] == title_id:
                return t
        return db.get_title(title_id)

    def _status_and_who(body: dict):
        status = _norm_status(body.get("status")) or "want"
        if status not in db.VALID_STATUSES:
            status = "want"
        valid_users = {u["id"] for u in db.list_users()}
        who = [uid for uid in (body.get("who") or [g.user["id"]]) if uid in valid_users]
        return status, who

    def _add_resolved(item: dict, status: str, who: list) -> dict:
        """Resolve provider details for one item, add it, and set interests.

        Shared by single add and bulk add. Raises ValueError if the item can't
        be resolved.
        """
        source = item.get("source")
        source_id = item.get("source_id")
        if not source or source_id is None:
            raise ValueError("source and source_id are required")
        details = provider_for_source(source).details(str(source_id), item.get("type", "unknown"))
        det = details.to_dict() if details else {}

        def pick(key):
            val = det.get(key)
            return val if val not in (None, "") else item.get(key)

        title = pick("title")
        if not title:
            raise ValueError("could not resolve a title")
        extra = det.get("extra") or {}
        data = {
            "source": source,
            "source_id": str(source_id),
            "type": pick("type") or "unknown",
            "title": title,
            "year": pick("year"),
            "overview": pick("overview"),
            "poster_url": pick("poster_url"),
            "source_url": pick("source_url"),
            "service": item.get("service"),
            "seasons": item.get("seasons") or extra.get("seasons"),
            "episodes_total": item.get("episodes_total") or extra.get("episodes"),
            "extra": extra,
        }
        row = db.add_title(data, added_by=g.user["id"])
        db.add_activity(g.user["id"], row["id"], "added", title)
        enrich.enqueue(row["id"])
        valid_users = {u["id"] for u in db.list_users()}
        for uid in (who or [g.user["id"]]):
            if uid in valid_users:
                db.set_interest(uid, row["id"], status=status)
        return row

    # --------------------------------------------------------------- pages
    @app.get("/")
    def index():
        return render_template("index.html", base_path=g.base_path, version=VERSION)

    @app.get("/health")
    def health():
        return jsonify(status="ok", version=VERSION)

    # ----------------------------------------------------------------- API
    @app.get("/api/me")
    def api_me():
        return jsonify(
            user=g.user,
            users=db.list_users(),
            config=config.public_config(),
        )

    @app.get("/api/search")
    def api_search():
        query = (request.args.get("q") or "").strip()
        if not query:
            return jsonify(results=[])
        limit = min(int(request.args.get("limit", 10) or 10), 20)
        results = [r.to_dict() for r in combined_search(query, limit=limit)]
        # Flag titles already in the household catalog.
        existing = {
            (t["source"], t["source_id"]): t["id"]
            for t in db.list_titles(g.user["id"])
        }
        for r in results:
            r["in_catalog"] = existing.get((r["source"], r["source_id"]))
        return jsonify(results=results, provider=config.active_provider_name())

    @app.get("/api/details")
    def api_details():
        source = request.args.get("source")
        source_id = request.args.get("source_id")
        if not source or not source_id:
            return jsonify(error="source and source_id are required"), 400
        det = provider_for_source(source).details(str(source_id), request.args.get("type", "unknown"))
        return jsonify(det.to_dict() if det else {})

    @app.get("/api/titles")
    def api_titles():
        return jsonify(
            titles=db.list_titles(
                g.user["id"],
                status=request.args.get("status") or None,
                type_=request.args.get("type") or None,
                q=request.args.get("q") or None,
            )
        )

    @app.post("/api/titles")
    def api_add_title():
        body = request.get_json(silent=True) or {}
        status, who = _status_and_who(body)
        try:
            row = _add_resolved(body, status, who)
        except ValueError as exc:
            return jsonify(error=str(exc)), (422 if "title" in str(exc) else 400)
        return jsonify(_hydrated(row["id"])), 201

    @app.post("/api/resolve")
    def api_resolve():
        """Match a list of free-text titles to their best provider result."""
        body = request.get_json(silent=True) or {}
        queries = body.get("queries") or []
        existing = {
            (t["source"], t["source_id"]): t["id"]
            for t in db.list_titles(g.user["id"])
        }
        out = []
        for raw in queries[:80]:
            q = (raw or "").strip()
            if not q:
                continue
            title_q, year_q = _parse_query(q)
            match = _best_match(combined_search(title_q, limit=6), year_q)
            m = match.to_dict() if match else None
            if m:
                m["in_catalog"] = existing.get((m["source"], m["source_id"]))
            out.append({"query": q, "match": m})
        return jsonify(results=out)

    @app.post("/api/titles/bulk")
    def api_bulk():
        """Add a batch of already-resolved items, sharing one status/who."""
        body = request.get_json(silent=True) or {}
        items = body.get("items") or []
        status, who = _status_and_who(body)
        existing = {(t["source"], t["source_id"]) for t in db.list_titles(g.user["id"])}
        added, skipped, failed = [], [], []
        for item in items[:100]:
            key = (item.get("source"), str(item.get("source_id")))
            try:
                row = _add_resolved(item, status, who)
            except ValueError:
                failed.append(item.get("title") or item.get("query") or "?")
                continue
            (skipped if key in existing else added).append(row["title"])
        return jsonify(added=added, skipped=skipped, failed=failed)

    @app.delete("/api/titles/<int:title_id>")
    def api_delete_title(title_id: int):
        title = db.get_title(title_id)
        if not title:
            abort(404)
        db.remove_title(title_id)
        db.add_activity(g.user["id"], None, "removed", title["title"])
        return jsonify(ok=True)

    @app.put("/api/titles/<int:title_id>/interest")
    def api_set_interest(title_id: int):
        title = db.get_title(title_id)
        if not title:
            abort(404)
        body = request.get_json(silent=True) or {}
        status = _norm_status(body.get("status"))
        rating = body.get("rating")

        if status is not None and status not in (*db.VALID_STATUSES, "clear"):
            return jsonify(error=f"invalid status: {status}"), 400
        if rating is not None:
            try:
                rating = int(rating)
            except (TypeError, ValueError):
                return jsonify(error="rating must be an integer 1-5"), 400
            if not 1 <= rating <= 5:
                return jsonify(error="rating must be 1-5"), 400

        db.set_interest(g.user["id"], title_id, status=status, rating=rating)
        # Marking a show finished auto-fills its episode progress.
        if status == "watched" and title.get("episodes_total"):
            db.update_title(title_id, {"episodes_watched": title["episodes_total"]})
        if status and status != "clear":
            db.add_activity(g.user["id"], title_id, status, title["title"])
        elif rating:
            db.add_activity(g.user["id"], title_id, "rated", f"{title['title']} ({rating}★)")
        return jsonify(_hydrated(title_id))

    @app.put("/api/titles/<int:title_id>")
    def api_update_title(title_id: int):
        title = db.get_title(title_id)
        if not title:
            abort(404)
        body = request.get_json(silent=True) or {}
        fields = {k: body[k] for k in ("service", "seasons", "episodes_total", "type", "year")
                  if k in body}
        if "episodes_watched" in body and body["episodes_watched"] is not None:
            ew = max(0, int(body["episodes_watched"]))
            total = body.get("episodes_total", title.get("episodes_total"))
            if total:
                ew = min(ew, int(total))
            fields["episodes_watched"] = ew
        db.update_title(title_id, fields)
        return jsonify(_hydrated(title_id))

    @app.post("/api/titles/<int:title_id>/enrich")
    def api_enrich(title_id: int):
        # Enrichment is automatic in the background; this endpoint forces it
        # for one title (e.g. a manual retry) and is not surfaced in the UI.
        if not db.get_title(title_id):
            abort(404)
        if not config.TMDB_API_KEY:
            return jsonify(error="TMDB key not configured"), 400
        enrich.enrich_title(title_id)
        return jsonify(_hydrated(title_id))

    @app.get("/api/titles/<int:title_id>/matches")
    def api_matches(title_id: int):
        title = db.get_title(title_id)
        if not title:
            abort(404)
        if not config.TMDB_API_KEY:
            return jsonify(error="TMDB key not configured"), 400
        query = (request.args.get("q") or title["title"]).strip()
        return jsonify(results=enrich.tmdb_candidates(query))

    @app.post("/api/titles/<int:title_id>/rematch")
    def api_rematch(title_id: int):
        title = db.get_title(title_id)
        if not title:
            abort(404)
        if not config.TMDB_API_KEY:
            return jsonify(error="TMDB key not configured"), 400
        body = request.get_json(silent=True) or {}
        tmdb_id = body.get("tmdb_id")
        type_ = body.get("type", "movie")
        if not tmdb_id:
            return jsonify(error="tmdb_id is required"), 400
        if not enrich.apply_match(title_id, tmdb_id, type_):
            return jsonify(error="could not apply that match"), 404
        db.add_activity(g.user["id"], title_id, "rematched", title["title"])
        return jsonify(_hydrated(title_id))

    @app.get("/api/suggestions")
    def api_suggestions():
        min_want = 2 if db.count_users() >= 2 else 1
        return jsonify(suggestions=db.suggestions(min_want=min_want), min_want=min_want)

    @app.get("/api/activity")
    def api_activity():
        limit = min(int(request.args.get("limit", 30) or 30), 100)
        return jsonify(activity=db.list_activity(limit=limit))

    @app.errorhandler(403)
    def _forbidden(_e):
        return jsonify(error="forbidden"), 403

    @app.errorhandler(404)
    def _not_found(_e):
        return jsonify(error="not found"), 404

    return app


def main():
    logging.basicConfig(
        level=getattr(logging, config.LOG_LEVEL.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    app = create_app()
    log.info(
        "Reel Together v%s on :%s (provider=%s, tmdb=%s)",
        VERSION, config.PORT, config.active_provider_name(), bool(config.TMDB_API_KEY),
    )
    from waitress import serve

    serve(app, host="0.0.0.0", port=config.PORT, threads=8, ident="ReelTogether")


if __name__ == "__main__":
    main()
