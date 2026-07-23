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

#: Per-request timeout (seconds). The connected-hosts endpoint in particular
#: can be slow to assemble, so this is generous.
DEFAULT_TIMEOUT = 20

#: A single browser-style client identifier. The router does not check it, but
#: sending one keeps the request shape close to the real web UI.
USER_AGENT = "compalf3896lg/1.0.0 (+https://github.com/AboveColin/compalf3896lg)"

# -- router error codes (the ``errorCode`` field in error bodies) -------------

#: ``503`` "A user is logged in!" — the box allows only one session at a time.
ERR_SESSION_BUSY = 65545

#: ``401`` "Unauthorized" — the bearer token expired or was invalidated.
ERR_UNAUTHORIZED = 7

#: ``405`` — method not allowed on an existing URI.
ERR_METHOD_NOT_ALLOWED = 10

# -- session behaviour --------------------------------------------------------

#: The router has **no logout endpoint**. An idle session is released by the
#: box roughly this many seconds after the last authenticated request. Callers
#: that poll should either poll no more often than this or expect a
#: :class:`~compalf3896lg.exceptions.CompalSessionBusyError` while a previous
#: session is still held.
TOKEN_TTL = 900

#: The login endpoint locks out after this many *contiguous* failed password
#: attempts (a ``503`` "session busy" is **not** a failure and does not count).
LOCKOUT_FAILURE_LIMIT = 6

#: Wi-Fi band identifiers used across the API.
BAND_2G = "band2g"
BAND_5G = "band5g"
BANDS = (BAND_2G, BAND_5G)
