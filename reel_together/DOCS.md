# Reel Together — Documentation

## What it does

Reel Together is a shared watchlist for your whole household. It runs as a Home
Assistant add-on behind ingress, so anyone who can log in to Home Assistant can
open it — and the app knows who they are without a separate account.

The app is a three-column board — **Want to Watch**, **Watching Now**, and
**Finished**. The list is shared: everyone sees the same catalog, and the small
coloured dots on each card show where each person stands. Cards in *Want to
Watch* that two or more people want are flagged **★ Together** — your built-in
movie-night shortlist.

## Configuration

Set these under the add-on's **Configuration** tab.

| Option | Default | Description |
| --- | --- | --- |
| `metadata_provider` | `auto` | Which source to search. `auto` uses TMDB when a key is set, otherwise Wikipedia. Force one with `wikipedia` or `tmdb`. |
| `tmdb_api_key` | _(empty)_ | A free TMDB API key. When set, search returns proper poster art and reliable movie/TV data, and titles you added from Wikipedia are **automatically enriched** in the background with TMDB posters, type, and season/episode counts (existing titles are swept on the next restart). |
| `allow_direct_access` | `false` | Leave `false` for normal ingress use. Set `true` only if you intend to reach the add-on directly (bypassing ingress); this relaxes the IP allow-list. |
| `log_level` | `info` | `debug`, `info`, `warning`, or `error`. |

### Getting a TMDB API key (optional)

1. Create a free account at <https://www.themoviedb.org/>.
2. Go to **Settings → API** and request an API key (the "Developer" option).
3. Copy the **API Key (v3 auth)** value into `tmdb_api_key` and restart the add-on.

Wikipedia is used with no key at all — TMDB only upgrades the experience.

## Using it

- **Add a title** — click **+ Add title**, search for the movie or show, then
  pick its type, streaming service, who's interested, and a starting column.
  Search results come from your active provider (Wikipedia or TMDB).
- **Move things along** — drag a card between the three columns to change its
  status. (On the *Watching Now* column, TV cards show an episode progress bar
  with − / + steppers and a **Mark finished** button that auto-fills at the
  finale.)
- **Rate it** — click the stars on a *Finished* card.
- **Wrong match?** — with a TMDB key set, hover a card and click **↻** to search
  TMDB and pick the correct entry. Useful on the rare occasion background
  enrichment matched an ambiguously-named title to the wrong poster.
- **Who's who** — each person who's added a title shows as a coloured dot. Use
  the **Everyone / Me** toggle to switch between the whole household's board and
  just yours; filter by **type** (All / Movies / TV), **service**, or live
  **search**.
- **Appearance** — the ◐ button switches the accent colour (Marigold, Teal,
  Rose, Plum) and toggles compact cards; your choice is remembered per browser.

> People appear as "who" options once they've opened the app at least once
> (that's when Home Assistant first tells the add-on who they are).

## Data & privacy

- All of your watchlist data stays in `reel_together.db` under the add-on's
  `/data` directory, which Home Assistant persists across restarts and includes
  in add-on backups/snapshots.
- The only outbound requests are metadata lookups to Wikipedia and (if
  configured) TMDB — made when you search, and automatically in the background
  to enrich newly added titles when a TMDB key is set.

## Architecture notes

- Identity comes from the ingress headers HA forwards: `X-Remote-User-Id`
  (stable key), `X-Remote-User-Name`, and `X-Remote-User-Display-Name`. The
  username is not guaranteed, so the app keys on the id and falls back to the
  display name.
- The server listens on `0.0.0.0:8099` and only accepts connections from the
  ingress proxy (`172.30.32.2`) plus loopback, unless `allow_direct_access` is
  enabled.
- Front-end requests are built against the `X-Ingress-Path` base so the app
  works correctly under the dynamic ingress URL.
