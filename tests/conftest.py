"""Shared fixtures for the Liberty Global gateway tests.

The client takes its scheme, host and port as arguments, so the tests point it
at a real aiohttp server on a loopback port rather than mocking aiohttp.
Mocking libraries for aiohttp lag its releases and break the suite on an
unrelated bump; a real server does not, and it also exercises the status codes
and connection failures for real.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable

import pytest
import pytest_asyncio
from aiohttp import ClientSession, web

from liberty_global_gateway import LibertyGatewayClient
from liberty_global_gateway.constants import API_PATH

PASSWORD = "admin-password"
TOKEN = "bearer-token-1"
USER_ID = 3


class FakeGateway:
    """A loopback server standing in for the router's /rest/v1 API.

    ``requests`` records every request, and ``bodies`` the decoded JSON of each
    write, so a test can assert on the exact body the client sent.
    """

    def __init__(self) -> None:
        self.app = web.Application()
        self.requests: list[web.Request] = []
        self.bodies: list[object] = []
        self._routes: dict[tuple[str, str], Callable] = {}
        self.app.router.add_route("*", "/{tail:.*}", self._dispatch)
        self.host = "127.0.0.1"
        self.port = 0

    def handle(self, method: str, path: str, handler: Callable) -> None:
        """Answer ``method`` on the API path ``path`` with ``handler``."""
        self._routes[(method, API_PATH + path)] = handler

    def json(self, path: str, payload: object, status: int = 200, method: str = "GET") -> None:
        """Answer ``path`` with a JSON body."""
        self.handle(method, path, lambda _r: web.json_response(payload, status=status))

    def status(self, path: str, code: int, method: str = "GET") -> None:
        """Answer ``path`` with a bare status code."""
        self.handle(method, path, lambda _r: web.Response(status=code))

    def text(self, path: str, body: str, status: int = 200, method: str = "GET") -> None:
        """Answer ``path`` with a body that is not JSON."""
        self.handle(method, path, lambda _r: web.Response(text=body, status=status))

    def sequence(self, path: str, *responses: tuple, method: str = "GET") -> None:
        """Answer ``path`` with each (status, payload) in turn, repeating the last."""
        remaining = list(responses)

        def handler(_request: web.Request) -> web.StreamResponse:
            status, payload = remaining.pop(0) if len(remaining) > 1 else remaining[0]
            return web.json_response(payload, status=status)

        self.handle(method, path, handler)

    def allow_login(self, *, failures: int = 0, lockout: int = 0) -> None:
        """Serve the login status probe and a successful login."""
        self.json(
            "/user/login",
            {"loginDetails": {"numberOfContiguousFailures": failures, "lockoutTime": lockout}},
        )
        self.json(
            "/user/login",
            {"created": {"token": TOKEN, "userId": USER_ID}},
            status=200,
            method="POST",
        )
        self.handle("DELETE", f"/user/{USER_ID}/token/{TOKEN}", lambda _r: web.Response(status=204))

    async def _dispatch(self, request: web.Request) -> web.StreamResponse:
        self.requests.append(request)
        try:
            self.bodies.append(await request.json())
        except Exception:  # noqa: BLE001  a bodyless request is a valid case
            self.bodies.append(None)
        handler = self._routes.get((request.method, request.path))
        if handler is None:
            return web.json_response({"message": "no route"}, status=404)
        result = handler(request)
        return await result if hasattr(result, "__await__") else result

    def paths(self, method: str = "GET") -> list[str]:
        """Every path requested with ``method``, in order."""
        return [r.path for r in self.requests if r.method == method]


@pytest_asyncio.fixture
async def api() -> AsyncIterator[FakeGateway]:
    """A running fake gateway, with its port filled in."""
    fake = FakeGateway()
    runner = web.AppRunner(fake.app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    fake.port = runner.addresses[0][1]
    try:
        yield fake
    finally:
        await runner.cleanup()


@pytest_asyncio.fixture
async def http() -> AsyncIterator[ClientSession]:
    """A session the test owns, so the client must leave it open."""
    async with ClientSession() as open_session:
        yield open_session


@pytest_asyncio.fixture
async def client(
    api: FakeGateway, http: ClientSession
) -> AsyncIterator[LibertyGatewayClient]:
    """A client pointed at the fake over plain HTTP, already able to log in."""
    api.allow_login()
    instance = LibertyGatewayClient(
        api.host, PASSWORD, session=http, port=api.port, scheme="http"
    )
    yield instance
    await instance.close()


@pytest.fixture(autouse=True)
def no_outbound_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail any test that tries to resolve a name outside loopback.

    This is a tripwire, not a limit: every test here talks to a fake on
    127.0.0.1, so correct tests never notice it exists. It is here because a
    test that points a client at a real gateway looks exactly like a test that
    points it at a fake, and this client can reboot the thing it talks to.

    The guard sits on getaddrinfo rather than on connect, because that is where
    every outbound connection starts and it is the last point at which the
    hostname is still readable.
    """
    import socket

    allowed = {"127.0.0.1", "::1", "localhost", ""}
    real_getaddrinfo = socket.getaddrinfo

    def guarded(host, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003, ANN202
        if host is not None and str(host) not in allowed:
            raise AssertionError(
                f"a test tried to reach {host!r}. Tests must only talk to the "
                "local fake: point the client at the api fixture, not a real "
                "host."
            )
        return real_getaddrinfo(host, *args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", guarded)
