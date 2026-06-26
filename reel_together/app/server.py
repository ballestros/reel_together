"""Flask application for Reel Together.

A small JSON API plus the single-page front-end. Runs behind Home Assistant
ingress on port 8099, served by waitress in production. Authentication is
handled by Home Assistant; we read the forwarded user identity in ``auth``.
"""
from __future__ import annotations

import logging

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
        source = body.get("source")
        source_id = body.get("source_id")
        if not source or source_id is None:
            return jsonify(error="source and source_id are required"), 400

        # Fetch fuller details where possible; fall back to the posted fields.
        details = provider_for_source(source).details(
            str(source_id), body.get("type", "unknown")
        )
        det = details.to_dict() if details else {}

        def pick(key):
            val = det.get(key)
            return val if val not in (None, "") else body.get(key)

        title = pick("title")
        if not title:
            return jsonify(error="could not resolve a title"), 422

        data = {
            "source": source,
            "source_id": str(source_id),
            "type": pick("type") or "unknown",
            "title": title,
            "year": pick("year"),
            "overview": pick("overview"),
            "poster_url": pick("poster_url"),
            "source_url": pick("source_url"),
            "service": body.get("service"),
            "seasons": body.get("seasons") or (det.get("extra") or {}).get("seasons"),
            "episodes_total": body.get("episodes_total") or (det.get("extra") or {}).get("episodes"),
            "extra": det.get("extra") or {},
        }
        row = db.add_title(data, added_by=g.user["id"])
        db.add_activity(g.user["id"], row["id"], "added", title)

        # Whose list(s) it lands on. Defaults to the person adding it.
        status = _norm_status(body.get("status")) or "want"
        if status not in db.VALID_STATUSES:
            status = "want"
        valid_users = {u["id"] for u in db.list_users()}
        who = [uid for uid in (body.get("who") or [g.user["id"]]) if uid in valid_users]
        for uid in who or [g.user["id"]]:
            db.set_interest(uid, row["id"], status=status)
        db.add_activity(g.user["id"], row["id"], status, title)
        enrich.enqueue(row["id"])  # silently upgrade to TMDB data when a key is set

        return jsonify(_hydrated(row["id"])), 201

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
