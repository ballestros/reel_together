# Changelog

## 0.1.2

- Fix all `hidden` elements (the Add-a-title and Fix-the-match modals, the
  TV season/episode fields, the appearance menu) showing on load. Their
  `display` rules were overriding the `hidden` attribute; `[hidden]` is now
  enforced, so they stay closed until opened.

## 0.1.1

- Fix add-on build failing with `pip: not found`: pin the `python:3.12-slim`
  base image directly in the Dockerfile instead of relying on the `build.yaml`
  override, which Home Assistant could fall back from to its Python-less Alpine
  base image.

## 0.1.0

Initial release.

- Shared household watchlist served as a Home Assistant ingress add-on.
- Three-column board (Want to Watch / Watching Now / Finished) with drag-to-move,
  matching the Reel Together design: warm paper theme, Bricolage Grotesque +
  Schibsted Grotesk type, and switchable Marigold / Teal / Rose / Plum accents.
- Per-person dots keyed to the Home Assistant user (via ingress headers), an
  Everyone / Me toggle, and a ★ Together flag for titles 2+ people want.
- Add-title modal with provider search, type, streaming service, who's
  interested, and starting status.
- TV episode tracking (progress bar, − / + steppers, auto-fill "Mark finished")
  and 1–5 star ratings on finished titles.
- Filters: type (All / Movies / TV), streaming service, and live search.
- SQLite storage under `/data` (users, titles, interests, activity).
- Pluggable metadata: Wikipedia by default; when a TMDB API key is set, titles
  are enriched automatically in the background with posters, type, and
  season/episode counts (no manual action), and the board refreshes to show it.
- Per-card re-match (↻) to correct an occasional wrong auto-match by picking the
  right TMDB entry.
