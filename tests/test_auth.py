"""Tests for login, the single session slot, and lockout.

The router allows exactly one authenticated session and locks the login
endpoint after a run of wrong passwords. Confusing those two with a bad
password is what turns a busy web-UI tab into a user deleting and re-adding
their integration, so each gets its own exception and its own case here.
"""

from __future__ import annotations

import pytest
from aiohttp import web

from liberty_global_gateway import (
    AuthManager,
    GatewayAuthError,
    GatewayLockoutError,
    GatewayNetworkError,
    GatewaySessionBusyError,
    LibertyGatewayClient,
)
from liberty_global_gateway.constants import ERR_SESSION_BUSY

from .conftest import PASSWORD, TOKEN, USER_ID, FakeGateway


def manager(api: FakeGateway, http, password: str = PASSWORD) -> AuthManager:
    """An auth manager pointed at the fake over plain HTTP."""
    return AuthManager(http, f"http://{api.host}:{api.port}", password)


class TestLockoutCheck:
    """The manager reads the lockout status before it tries a password."""

    async def test_a_clean_status_allows_a_login(self, api: FakeGateway, http) -> None:
        api.allow_login()
        assert await manager(api, http).async_login() == TOKEN

    async def test_a_live_lockout_refuses_to_attempt_a_login(
        self, api: FakeGateway, http
    ) -> None:
        # Attempting one while locked out only extends the lockout.
        api.allow_login(lockout=120)
        with pytest.raises(GatewayLockoutError) as caught:
            await manager(api, http).async_login()
        assert caught.value.lockout_time == 120

    async def test_no_login_is_posted_while_locked_out(
        self, api: FakeGateway, http
    ) -> None:
        api.allow_login(lockout=120)
        with pytest.raises(GatewayLockoutError):
            await manager(api, http).async_login()
        assert api.paths("POST") == []

    async def test_the_check_can_be_skipped(self, api: FakeGateway, http) -> None:
        api.allow_login(lockout=120)
        assert await manager(api, http).async_login(check_lockout=False) == TOKEN

    async def test_the_status_reports_failures_and_seconds(
        self, api: FakeGateway, http
    ) -> None:
        api.allow_login(failures=3, lockout=60)
        assert await manager(api, http).async_get_lockout() == (3, 60)

    async def test_a_missing_login_details_block_reads_as_zero(
        self, api: FakeGateway, http
    ) -> None:
        api.json("/user/login", {})
        assert await manager(api, http).async_get_lockout() == (0, 0)

    async def test_non_numeric_counters_read_as_zero(
        self, api: FakeGateway, http
    ) -> None:
        api.json(
            "/user/login",
            {"loginDetails": {"numberOfContiguousFailures": "n/a", "lockoutTime": None}},
        )
        assert await manager(api, http).async_get_lockout() == (0, 0)

    async def test_an_error_status_is_reported(self, api: FakeGateway, http) -> None:
        api.json("/user/login", {"message": "nope"}, status=500)
        with pytest.raises(GatewayAuthError, match="HTTP 500"):
            await manager(api, http).async_get_lockout()


class TestLogin:
    """The login round trip itself."""

    async def test_the_password_is_posted(self, api: FakeGateway, http) -> None:
        api.allow_login()
        await manager(api, http).async_login()
        assert api.bodies[-1] == {"password": PASSWORD}

    async def test_the_token_and_user_id_are_kept(self, api: FakeGateway, http) -> None:
        api.allow_login()
        auth = manager(api, http)
        await auth.async_login()
        assert auth.token == TOKEN
        assert auth.user_id == USER_ID
        assert auth.obtained_at is not None

    async def test_the_auth_header_carries_the_bearer_token(
        self, api: FakeGateway, http
    ) -> None:
        api.allow_login()
        auth = manager(api, http)
        await auth.async_login()
        assert auth.auth_header() == {"Authorization": f"Bearer {TOKEN}"}

    async def test_no_token_means_no_auth_header(self, api: FakeGateway, http) -> None:
        assert manager(api, http).auth_header() == {}

    async def test_a_wrong_password_is_an_auth_error(self, api: FakeGateway, http) -> None:
        api.json("/user/login", {"loginDetails": {"lockoutTime": 0}})
        api.json("/user/login", {"message": "wrong password"}, status=401, method="POST")
        with pytest.raises(GatewayAuthError, match="wrong password"):
            await manager(api, http).async_login()

    async def test_a_200_without_a_token_is_an_auth_error(
        self, api: FakeGateway, http
    ) -> None:
        api.json("/user/login", {"loginDetails": {"lockoutTime": 0}})
        api.json("/user/login", {"created": {}}, method="POST")
        with pytest.raises(GatewayAuthError, match="no token"):
            await manager(api, http).async_login()

    async def test_a_failure_without_a_message_still_names_the_status(
        self, api: FakeGateway, http
    ) -> None:
        api.json("/user/login", {"loginDetails": {"lockoutTime": 0}})
        api.status("/user/login", 500, method="POST")
        with pytest.raises(GatewayAuthError, match="HTTP 500"):
            await manager(api, http).async_login()


class TestSingleSessionSlot:
    """A busy slot is not a bad password, and must not be reported as one."""

    async def test_a_503_is_a_session_busy_error(self, api: FakeGateway, http) -> None:
        api.json("/user/login", {"loginDetails": {"lockoutTime": 0}})
        api.json("/user/login", {"message": "A user is logged in!"}, status=503, method="POST")
        with pytest.raises(GatewaySessionBusyError):
            await manager(api, http).async_login()

    async def test_the_busy_error_code_is_enough_on_its_own(
        self, api: FakeGateway, http
    ) -> None:
        # Some firmware answers 200 with the error code in the body.
        api.json("/user/login", {"loginDetails": {"lockoutTime": 0}})
        api.json("/user/login", {"errorCode": ERR_SESSION_BUSY}, status=403, method="POST")
        with pytest.raises(GatewaySessionBusyError):
            await manager(api, http).async_login()

    async def test_a_busy_slot_is_not_reported_as_a_bad_password(
        self, api: FakeGateway, http
    ) -> None:
        # GatewaySessionBusyError does not inherit from GatewayAuthError, so a
        # caller that prompts for a new password on auth errors leaves the user
        # alone here. Usually the router's own web UI is simply open.
        assert not issubclass(GatewaySessionBusyError, GatewayAuthError)


class TestLogout:
    """Releasing the slot immediately instead of waiting for the idle timeout."""

    async def test_the_token_is_deleted_on_the_router(
        self, api: FakeGateway, http
    ) -> None:
        api.allow_login()
        auth = manager(api, http)
        await auth.async_login()
        assert await auth.async_logout() is True
        assert api.paths("DELETE") == [f"/rest/v1/user/{USER_ID}/token/{TOKEN}"]

    async def test_the_local_token_is_cleared(self, api: FakeGateway, http) -> None:
        api.allow_login()
        auth = manager(api, http)
        await auth.async_login()
        await auth.async_logout()
        assert auth.token is None
        assert auth.user_id is None

    async def test_logging_out_without_a_token_does_nothing(
        self, api: FakeGateway, http
    ) -> None:
        assert await manager(api, http).async_logout() is False
        assert api.requests == []

    async def test_a_failed_logout_still_clears_the_local_token(
        self, api: FakeGateway, http
    ) -> None:
        # The slot idles out on its own, so holding a token we know is gone
        # helps nobody.
        api.allow_login()
        auth = manager(api, http)
        await auth.async_login()
        auth._session = None  # noqa: SLF001  force the request to fail
        try:
            await auth.async_logout()
        except AttributeError:
            pass
        assert auth.token is None

    async def test_clear_does_not_contact_the_router(
        self, api: FakeGateway, http
    ) -> None:
        api.allow_login()
        auth = manager(api, http)
        await auth.async_login()
        before = len(api.requests)
        auth.clear()
        assert auth.token is None
        assert len(api.requests) == before


class TestTransportErrors:
    """Below the API, a dead router is a network error."""

    async def test_an_unreachable_router_is_a_network_error(self, http) -> None:
        auth = AuthManager(http, "http://127.0.0.1:1", PASSWORD)
        with pytest.raises(GatewayNetworkError, match="failed"):
            await auth.async_get_lockout()

    async def test_a_slow_router_is_a_network_error(
        self, api: FakeGateway, http
    ) -> None:
        import asyncio

        async def slow(_request: web.Request) -> web.StreamResponse:
            await asyncio.sleep(5)
            return web.json_response({})

        api.handle("GET", "/user/login", slow)
        auth = AuthManager(http, f"http://{api.host}:{api.port}", PASSWORD, timeout=1)
        with pytest.raises(GatewayNetworkError, match="timed out"):
            await auth.async_get_lockout()

    async def test_a_non_json_body_parses_as_nothing(
        self, api: FakeGateway, http
    ) -> None:
        api.text("/user/login", "<html>login</html>")
        assert await manager(api, http).async_get_lockout() == (0, 0)


class TestClientConstruction:
    """The client refuses to be built without what it needs."""

    def test_a_host_is_required(self) -> None:
        from liberty_global_gateway import GatewayValidationError

        with pytest.raises(GatewayValidationError, match="host is required"):
            LibertyGatewayClient("", PASSWORD)

    def test_a_password_is_required(self) -> None:
        from liberty_global_gateway import GatewayValidationError

        with pytest.raises(GatewayValidationError, match="password is required"):
            LibertyGatewayClient("192.0.2.1", "")

    async def test_the_host_is_exposed(self, api: FakeGateway, http) -> None:
        client = LibertyGatewayClient(api.host, PASSWORD, session=http, port=api.port, scheme="http")
        assert client.host == api.host

    async def test_create_is_the_constructor(self, api: FakeGateway, http) -> None:
        client = LibertyGatewayClient.create(
            api.host, PASSWORD, session=http, port=api.port, scheme="http"
        )
        assert isinstance(client, LibertyGatewayClient)

    async def test_a_borrowed_session_survives_close(
        self, api: FakeGateway, http
    ) -> None:
        api.allow_login()
        client = LibertyGatewayClient(api.host, PASSWORD, session=http, port=api.port, scheme="http")
        await client.close()
        assert http.closed is False

    async def test_an_owned_session_is_closed(self, api: FakeGateway) -> None:
        api.allow_login()
        client = LibertyGatewayClient(api.host, PASSWORD, port=api.port, scheme="http")
        owned = client._session  # noqa: SLF001  ownership is the thing under test
        await client.close()
        assert owned.closed is True

    async def test_the_context_manager_logs_out_and_closes(
        self, api: FakeGateway
    ) -> None:
        api.allow_login()
        api.json("/system/info", {"systemInfo": {"modelName": "F3896LG"}})
        async with LibertyGatewayClient(api.host, PASSWORD, port=api.port, scheme="http") as client:
            await client.login()
            owned = client._session  # noqa: SLF001
        assert owned.closed is True
        assert api.paths("DELETE") == [f"/rest/v1/user/{USER_ID}/token/{TOKEN}"]
