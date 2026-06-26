# Reel Together

A shared household watchlist for Home Assistant. Add movies and shows, mark what
you want to watch together, and let the app surface your next movie night.

- Runs behind Home Assistant ingress — HA handles login and identifies each user.
- Stores everything locally in SQLite (`/data`).
- Adds titles via Wikipedia (no key) or TMDB (optional free API key) for posters
  and richer data.

After starting, open the Web UI or use the **Reel Together** sidebar panel.
See **DOCS** for configuration.
