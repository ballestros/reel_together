"""Reel Together — a shared household watchlist for Home Assistant.

A small Flask application packaged as a Home Assistant add-on. It runs behind
HA ingress (so Home Assistant handles authentication and identifies each user),
stores everything in a local SQLite database under ``/data``, and pulls movie /
TV metadata from a pluggable provider (Wikipedia by default, TMDB when an API
key is configured).
"""

__version__ = "0.1.8"
