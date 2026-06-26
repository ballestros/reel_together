# Reel Together

A shared household watchlist that runs as a **Home Assistant add-on**. Everyone
in your home sees the same list of movies and shows, marks what they *want to
watch*, what they're *watching*, and what they've *watched* — and the app
surfaces the titles you all want to watch next for movie night.

* **Logged-in by default** — runs behind Home Assistant ingress, so HA handles
  authentication and tells the app who each person is. No separate password.
* **Self-contained data** — everything is stored in a local SQLite database
  under the add-on's `/data` directory. Nothing leaves your home except the
  metadata lookups you trigger.
* **Pluggable metadata** — adds titles using **Wikipedia** out of the box (no
  API key). Drop in a free **TMDB** API key to get proper poster art, reliable
  movie/TV typing, genres and runtimes — and to enrich titles you already added.

## Repository layout

```
.
├── repository.yaml          # marks this folder as an HA add-on repository
└── reel_together/           # the add-on
    ├── config.yaml          # add-on manifest (ingress, options, schema)
    ├── build.yaml           # base image per architecture
    ├── Dockerfile
    ├── requirements.txt
    ├── DOCS.md              # configuration & usage
    ├── CHANGELOG.md
    └── app/                 # the Flask application
        ├── server.py        # routes + ingress handling
        ├── db.py            # SQLite schema & data access
        ├── auth.py          # user identity from HA ingress headers
        ├── config.py        # reads /data/options.json
        └── providers/       # wikipedia (default) + tmdb (optional)
```

## Install it in Home Assistant

1. Push this folder to a Git repository (or copy `reel_together/` into your Home
   Assistant `/addons` folder for a purely local install).
2. In Home Assistant: **Settings → Add-ons → Add-on Store → ⋮ → Repositories**,
   and add your repository URL. (Skip this step for a local `/addons` install.)
3. Install **Reel Together**, then **Start** it.
4. Click **Open Web UI** — or use the **Reel Together** item in the sidebar.

See [`reel_together/DOCS.md`](reel_together/DOCS.md) for configuration, including
how to enable TMDB.

## Develop / run it directly

You can run the app as a plain container or process while iterating:

```bash
cd reel_together
pip install -r requirements.txt
REEL_TOGETHER_DB=./dev.db REEL_ALLOW_DIRECT=true python -m app.server
# open http://localhost:8099
```

Outside of ingress there are no HA user headers, so the app signs you in as a
single local "You" user. Set `REEL_ALLOW_DIRECT=true` so the app accepts direct
(non-ingress) connections during development.
