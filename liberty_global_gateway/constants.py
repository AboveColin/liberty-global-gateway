"""
Constants for the Liberty Global gateway client.

Liberty Global (and its sister operators) ship a family of DOCSIS cable
gateways that all run the same LG-RDK firmware and expose the same small REST
API under ``/rest/v1`` on their HTTPS admin interface. The certificate is
self-signed, so TLS verification is off by default.
"""

from __future__ import annotations

#: Default admin host. Ziggo hands out ``192.168.178.1``; UPC/Virgin Media
#: builds typically use ``192.168.0.1``. Callers that can determine the real
#: default gateway of the network should prefer that over this fallback.
DEFAULT_HOST = "192.168.178.1"

#: Gateway models known to run this firmware, mapped to the hardware
#: generation the web UI itself buckets them into (the SPA switches on
#: ``localization.modelName`` to pick a ``mv1``/``mv2+``/``mv3`` feature set).
#:
#: Only the F3896LG has been verified against real hardware; the rest are
#: listed because the shipped firmware bundle explicitly handles them.
KNOWN_MODELS = {
    "CH7465LG": "mv1",
    "F3896LG": "mv2+",
    "F3897LG": "mv2+",
    "F5685LGB": "mv3",
    "F5685LGE": "mv3",
}

#: Operator "skins" the firmware recognises, mapped to a human-readable brand.
#: The active one is reported as ``localization.skin``.
KNOWN_SKINS = {
    "ziggo": "Ziggo",
    "upc": "UPC",
    "virgin_media": "Virgin Media",
    "unitymedia": "Unitymedia",
    "sunrise": "Sunrise",
    "yallo": "Yallo",
    "munro": "Munro",
    "lumina": "Lumina",
    "grandslam": "Grand Slam",
}

#: Manufacturers seen in the gateways' UPnP device descriptions. Compal built
#: the earlier CH7465LG; Sagemcom builds the F-series.
KNOWN_MANUFACTURERS = ("Sagemcom", "Compal")

#: The admin interface is HTTPS only.
DEFAULT_SCHEME = "https"
DEFAULT_PORT = 443

#: Root of the REST API.
API_PATH = "/rest/v1"

#: The one endpoint that needs no authentication. It returns the operator
#: skin, the marketing product name and the model number, which is enough to
#: positively identify a gateway before asking the user for a password.
LOCALIZATION_PATH = "/system/localization"

#: Per-request timeout (seconds) for an unauthenticated :func:`probe`. Kept
#: short: it runs against hosts that may not be a gateway at all.
PROBE_TIMEOUT = 5

#: Per-request timeout (seconds) for the ordinary, fast endpoints.
DEFAULT_TIMEOUT = 20

#: The ``/network/hosts`` table is assembled on demand and, on a busy LAN with
#: dozens of clients, routinely takes longer than :data:`DEFAULT_TIMEOUT`. It
#: gets its own, more generous timeout so a slow host list does not fail a poll.
HOSTS_TIMEOUT = 60

#: A single browser-style client identifier. The router does not check it, but
#: sending one keeps the request shape close to the real web UI.
USER_AGENT = "liberty_global_gateway/1.3.0 (+https://github.com/AboveColin/liberty_global_gateway)"

# -- router error codes (the ``errorCode`` field in error bodies) -------------

#: ``503`` "A user is logged in!" — the box allows only one session at a time.
ERR_SESSION_BUSY = 65545

#: ``401`` "Unauthorized" — the bearer token expired or was invalidated.
ERR_UNAUTHORIZED = 7

#: ``405`` — method not allowed on an existing URI.
ERR_METHOD_NOT_ALLOWED = 10

# -- session behaviour --------------------------------------------------------

#: An idle session is released by the box roughly this many seconds after the
#: last authenticated request. Prefer calling :meth:`LibertyGatewayClient.logout`
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
