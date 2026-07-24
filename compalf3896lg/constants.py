"""
Constants for the Compal F3896LG client.

The F3896LG (a DOCSIS 3.1 gateway that Liberty Global / Ziggo ship in the
Netherlands) exposes a small REST API under ``/rest/v1`` on its HTTPS admin
interface. The certificate is self-signed, so TLS verification is off by
default.
"""

from __future__ import annotations

#: Default admin host on a Ziggo LAN.
DEFAULT_HOST = "192.168.178.1"

#: The admin interface is HTTPS only.
DEFAULT_SCHEME = "https"
DEFAULT_PORT = 443

#: Root of the REST API.
API_PATH = "/rest/v1"

#: Per-request timeout (seconds) for the ordinary, fast endpoints.
DEFAULT_TIMEOUT = 20

#: The ``/network/hosts`` table is assembled on demand and, on a busy LAN with
#: dozens of clients, routinely takes longer than :data:`DEFAULT_TIMEOUT`. It
#: gets its own, more generous timeout so a slow host list does not fail a poll.
HOSTS_TIMEOUT = 60

#: A single browser-style client identifier. The router does not check it, but
#: sending one keeps the request shape close to the real web UI.
USER_AGENT = "compalf3896lg/1.1.0 (+https://github.com/AboveColin/compalf3896lg)"

# -- router error codes (the ``errorCode`` field in error bodies) -------------

#: ``503`` "A user is logged in!" — the box allows only one session at a time.
ERR_SESSION_BUSY = 65545

#: ``401`` "Unauthorized" — the bearer token expired or was invalidated.
ERR_UNAUTHORIZED = 7

#: ``405`` — method not allowed on an existing URI.
ERR_METHOD_NOT_ALLOWED = 10

# -- session behaviour --------------------------------------------------------

#: An idle session is released by the box roughly this many seconds after the
#: last authenticated request. Prefer calling :meth:`CompalClient.logout`
#: (``DELETE /user/<id>/token/<token>``) to free the single slot immediately;
#: this TTL is only the fallback for when a client exits without logging out.
TOKEN_TTL = 900

#: The login endpoint locks out after this many *contiguous* failed password
#: attempts (a ``503`` "session busy" is **not** a failure and does not count).
LOCKOUT_FAILURE_LIMIT = 6

#: Wi-Fi band identifiers used across the API.
BAND_2G = "band2g"
BAND_5G = "band5g"
BANDS = (BAND_2G, BAND_5G)
