"""User identity from Home Assistant ingress.

When the app runs behind HA ingress, Home Assistant has already authenticated
the user and forwards three headers:

* ``X-Remote-User-Id``           — stable per-user id (always present)
* ``X-Remote-User-Name``         — username (NOT guaranteed; only the
                                   homeassistant auth provider sets it)
* ``X-Remote-User-Display-Name`` — friendly name

We key everything on the id and fall back gracefully. When the headers are
absent (running the container directly during development) we synthesise a
single local user so the app still works.
"""
from __future__ import annotations

from . import db

HDR_ID = "X-Remote-User-Id"
HDR_NAME = "X-Remote-User-Name"
HDR_DISPLAY = "X-Remote-User-Display-Name"
HDR_INGRESS_PATH = "X-Ingress-Path"

_LOCAL_DEV_ID = "local-dev"


def ingress_base(request) -> str:
    """Base path HA serves us under, e.g. ``/api/hassio_ingress/<token>``.

    Empty string when not behind ingress. Front-end URLs are built against it.
    """
    return request.headers.get(HDR_INGRESS_PATH, "") or ""


def current_user(request) -> dict:
    """Resolve (and persist) the user making this request."""
    uid = request.headers.get(HDR_ID)
    username = request.headers.get(HDR_NAME)
    display = request.headers.get(HDR_DISPLAY)

    if not uid:
        # Not behind ingress — single local identity for dev / direct access.
        uid = _LOCAL_DEV_ID
        display = display or username or "You"

    display = display or username or "Guest"
    return db.upsert_user(uid, username, display)
