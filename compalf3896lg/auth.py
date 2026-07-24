"""
Login / session management for the Compal F3896LG.

:class:`AuthManager` owns the single bearer token the router hands out. It is
careful about two firmware quirks:

* **Single session.** The box permits exactly one authenticated session and has
  no logout endpoint, so a login attempt while another session is active
  returns ``503`` "A user is logged in!" (``errorCode`` 65545). That is surfaced
  as :class:`~compalf3896lg.exceptions.CompalSessionBusyError` and is *not*
  treated as a bad password.
* **Lockout.** After a handful of *contiguous* wrong-password attempts the login
  endpoint locks out for a while. Before every login the manager reads the
  unauthenticated ``GET /user/login`` status and refuses to attempt a login
  while ``lockoutTime`` is non-zero, so it never digs the hole deeper.
"""

from __future__ import annotations

import asyncio
import time
from typing import Optional

import aiohttp

from .constants import API_PATH, DEFAULT_TIMEOUT, ERR_SESSION_BUSY, USER_AGENT
from .exceptions import (
    CompalAuthError,
    CompalLockoutError,
    CompalNetworkError,
    CompalSessionBusyError,
)


class AuthManager:
    """Obtains and holds the router's single bearer token."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        base_url: str,
        password: str,
        *,
        ssl: Optional[bool] = False,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> None:
        self._session = session
        self._base_url = base_url.rstrip("/")
        self._password = password
        self._ssl = ssl
        self._timeout = timeout
        self._token: Optional[str] = None
        self._user_id: Optional[int] = None
        self._obtained_at: Optional[float] = None
        self._lock = asyncio.Lock()

    @property
    def token(self) -> Optional[str]:
        """The current bearer token, or ``None`` if not logged in."""
        return self._token

    @property
    def user_id(self) -> Optional[int]:
        """The user id returned at login (``3`` / "regular" on stock firmware)."""
        return self._user_id

    @property
    def obtained_at(self) -> Optional[float]:
        """``time.time()`` when the current token was obtained."""
        return self._obtained_at

    def auth_header(self) -> dict[str, str]:
        """Authorization header for the current token (empty if none)."""
        return {"Authorization": f"Bearer {self._token}"} if self._token else {}

    def clear(self) -> None:
        """Forget the current token (does not contact the router)."""
        self._token = None
        self._user_id = None
        self._obtained_at = None

    async def async_logout(self) -> bool:
        """Release the router's single session by deleting the current token.

        The gateway logs a client out with ``DELETE /user/<userId>/token/<token>``
        (returns ``204``). Doing this frees the single login slot **immediately**
        instead of waiting for the idle timeout, so the web UI and other clients
        can log in again right away. Best effort: the local token is always
        cleared, even if the network call fails.

        Returns ``True`` if the logout request reached the router successfully.
        """
        token, user_id = self._token, self._user_id
        if not token or user_id is None:
            self.clear()
            return False
        ok = False
        try:
            status, _ = await self._request(
                "DELETE", f"/user/{user_id}/token/{token}", auth=True
            )
            ok = status in (200, 202, 204)
        except CompalNetworkError:
            # The slot will still idle-expire; nothing else to do.
            ok = False
        finally:
            self.clear()
        return ok

    async def async_get_lockout(self) -> tuple[int, int]:
        """Return ``(contiguous_failures, lockout_seconds)`` from the router.

        Uses the unauthenticated ``GET /user/login`` status endpoint, so it is
        safe to call before logging in.
        """
        status, data = await self._request("GET", "/user/login", auth=False)
        details = (data or {}).get("loginDetails") or {}
        try:
            failures = int(details.get("numberOfContiguousFailures", 0))
        except (TypeError, ValueError):
            failures = 0
        try:
            lockout = int(details.get("lockoutTime", 0))
        except (TypeError, ValueError):
            lockout = 0
        if status >= 400:
            raise CompalAuthError(f"could not read login status (HTTP {status})")
        return failures, lockout

    async def async_login(self, *, check_lockout: bool = True) -> str:
        """Log in and return the bearer token.

        Raises :class:`CompalLockoutError` if the endpoint is currently locked,
        :class:`CompalSessionBusyError` if another session holds the slot, and
        :class:`CompalAuthError` if the password is rejected.
        """
        async with self._lock:
            if check_lockout:
                _failures, lockout = await self.async_get_lockout()
                if lockout > 0:
                    raise CompalLockoutError(
                        f"login is locked out for ~{lockout}s after failed attempts",
                        lockout_time=lockout,
                    )

            status, data = await self._request(
                "POST", "/user/login", auth=False, json={"password": self._password}
            )
            error_code = (data or {}).get("errorCode")

            if status in (200, 201):
                created = (data or {}).get("created") or {}
                token = created.get("token")
                if not token:
                    raise CompalAuthError("login succeeded but no token was returned")
                self._token = token
                self._user_id = created.get("userId")
                self._obtained_at = time.time()
                return token

            if status == 503 or error_code == ERR_SESSION_BUSY:
                raise CompalSessionBusyError(
                    "another session already holds the router's single login slot; "
                    "retry after the previous session's token expires"
                )

            message = (data or {}).get("message") or f"login failed (HTTP {status})"
            raise CompalAuthError(str(message))

    async def _request(self, method: str, path: str, *, auth: bool, json=None):
        """Low-level request returning ``(status, parsed_json_or_None)``."""
        headers = {"User-Agent": USER_AGENT}
        if auth:
            headers.update(self.auth_header())
        try:
            async with self._session.request(
                method,
                f"{self._base_url}{API_PATH}{path}",
                headers=headers,
                json=json,
                ssl=self._ssl,
                timeout=aiohttp.ClientTimeout(total=self._timeout),
            ) as resp:
                try:
                    data = await resp.json(content_type=None)
                except (aiohttp.ContentTypeError, ValueError):
                    data = None
                return resp.status, data
        except asyncio.TimeoutError as err:
            raise CompalNetworkError(f"request to {path} timed out") from err
        except aiohttp.ClientError as err:
            raise CompalNetworkError(f"request to {path} failed: {err}") from err
