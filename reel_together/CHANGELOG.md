# Changelog

## 0.1.9

- Batch add: paste a list of titles (one per line, optionally `Title (Year)` to
  disambiguate), pick a shared status and who, and Reel Together matches each to
  its best movie/show. You review the matches with posters, untick any wrong
  ones, and add them all at once — reached via "Paste a whole list instead" in
  the Add dialog. Good for seeding a watchlist from an existing list.

## 0.1.8

- Edit a title's details: each card now has a ✎ action that opens a small editor
  to fix its type, streaming service, and season/episode counts — handy when you
  forgot to set where something's streaming. The card's edit / re-match / remove
  controls are now grouped in one tidy corner row.

## 0.1.7

- Fix the periodic flicker: the board now re-renders only when the data has
  actually changed, instead of rebuilding every card (and reloading posters) on
  each background refresh.
- The background refresh reads the local database, not the metadata APIs, so it
  costs nothing external. The TVmaze "airing" sweep now skips shows whose next
  episode is already known and re-checks the rest at most once a day, keeping
  outside calls to a minimum.

## 0.1.6

- TV shows now come from **TVmaze** (free, no API key): search, posters,
  overview, and accurate season/episode counts. Movies still come from Wikipedia
  (or TMDB if a key is set), and search merges both. TMDB background enrichment
  now targets only Wikipedia-added titles.
- **Airing soon**: a TV show with an upcoming episode shows a ▶ badge with the
  next air date on its card, refreshed in the background every few hours.

## 0.1.5

- Mobile-friendly layout. The header now stacks cleanly on phones (brand +
  actions, then full-width search, then filters) instead of wrapping awkwardly,
  and collapses to a single row only on wide screens.
- Touch support: because drag-and-drop is mouse-only, each card gets a status
  dropdown on touch devices to move it between Want / Watching / Finished; the
  remove (×) and re-match (↻) controls, previously hover-only, stay visible on
  touch. Drag-and-drop is unchanged on desktop.

## 0.1.4

- Pull TV season and episode counts from Wikidata (the article's linked item,
  properties P2437 / P1113) when adding a show from Wikipedia — so no-key
  installs get episode tracking too. The Add-a-title modal now pre-fills the
  season/episode fields from the provider (Wikidata or TMDB) so you can confirm
  or tweak them before saving.

## 0.1.3

- Show the sidebar panel to all Home Assistant users, not just admins
  (`panel_admin: false`), so the whole household can open Reel Together.
- Keep the household member list live: the board now refreshes who's joined
  without a page reload, and per-person dot colours stay stable as people join.

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
