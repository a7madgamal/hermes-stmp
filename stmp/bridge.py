"""HTTP transport for the STMP bridge.

One place that knows how to talk to the phone, and nothing else. No retries: a
retry after a decline is a second approval prompt for an action a human already
refused, and a retry after a timeout is a second prompt for something nobody
answered. The failure is the answer.

Standard library only, on purpose: this plugin must not add a dependency to the
agent's environment just to send JSON to one URL.
"""

from __future__ import annotations

import json
import socket
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Mapping

DEFAULT_TIMEOUT = 75.0
#: The phone holds the approval modal for 60 s. A caller that gives up sooner
#: reports "unreachable" while a human is still deciding, which is a lie.
MIN_TIMEOUT = 65.0
MAX_TIMEOUT = 600.0


class BridgeError(Exception):
    """A failed call, carrying the device's own error code."""

    def __init__(self, code: str, detail: str, *, status: int | None = None):
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.status = status

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"{self.code}: {self.detail}"


class ConfigError(Exception):
    """`base_url` or `timeout_seconds` is unusable. Raised before any request."""


@dataclass(frozen=True)
class Config:
    base_url: str
    timeout: float
    #: Where downloads may be written. Empty means the plugin's own data dir.
    download_dir: str = ""
    #: Where uploads may be read from. Empty means "anywhere except the denied
    #: credential stores", which is the default posture and is enforced in paths.py.
    upload_dir: str = ""
    #: Whether a download may replace an existing file.
    allow_overwrite: bool = False

    @classmethod
    def from_settings(
        cls,
        base_url: Any,
        timeout_seconds: Any = None,
        download_dir: Any = None,
        upload_dir: Any = None,
        allow_overwrite: Any = None,
    ) -> "Config":
        """Validate what the user typed, loudly.

        A bridge URL that is wrong must fail here with the value in the message,
        not surface later as a connection error the model has to guess about.
        """
        raw = ("" if base_url is None else str(base_url)).strip()
        if not raw:
            raise ConfigError(
                "no base_url configured. Set plugins.entries.stmp.settings.base_url to the "
                "bridge address shown in the STMP app, for example http://192.168.1.20:8787"
            )
        parsed = urllib.parse.urlsplit(raw)
        if parsed.scheme not in ("http", "https"):
            raise ConfigError(
                f"base_url {raw!r} must start with http:// or https:// — got scheme "
                f"{parsed.scheme or '(none)'!r}"
            )
        if not parsed.hostname:
            raise ConfigError(f"base_url {raw!r} has no host")
        if parsed.query or parsed.fragment or parsed.path not in ("", "/"):
            raise ConfigError(
                f"base_url {raw!r} must be the bare origin (scheme, host, optional port) — "
                "drop the path, query or fragment"
            )

        timeout = DEFAULT_TIMEOUT
        if timeout_seconds not in (None, ""):
            try:
                timeout = float(timeout_seconds)
            except (TypeError, ValueError) as exc:
                raise ConfigError(
                    f"timeout_seconds must be a number, got {timeout_seconds!r}"
                ) from exc
            if timeout < MIN_TIMEOUT:
                raise ConfigError(
                    f"timeout_seconds {timeout:g} is shorter than the phone's 60 s approval "
                    f"window; use at least {MIN_TIMEOUT:g}"
                )
            if timeout > MAX_TIMEOUT:
                raise ConfigError(
                    f"timeout_seconds {timeout:g} is longer than {MAX_TIMEOUT:g}; a stuck call "
                    "should surface, not hold the turn open"
                )

        origin = f"{parsed.scheme}://{parsed.netloc}"
        return cls(
            base_url=origin,
            timeout=timeout,
            download_dir="" if download_dir is None else str(download_dir).strip(),
            upload_dir="" if upload_dir is None else str(upload_dir).strip(),
            allow_overwrite=_as_bool(allow_overwrite),
        )

    @property
    def device(self) -> str:
        """Host:port, for messages the model may show a user."""
        return urllib.parse.urlsplit(self.base_url).netloc


class Bridge:
    """JSON-only client for one STMP instance."""

    def __init__(self, config: Config):
        self.config = config

    # -- public API ---------------------------------------------------------

    def call(
        self,
        method: str,
        path: str,
        *,
        query: Mapping[str, Any] | None = None,
        body: Mapping[str, Any] | None = None,
        raw_body: bytes | None = None,
        content_type: str | None = None,
    ) -> Any:
        """One request. Returns parsed JSON, or raw bytes for a streaming route."""
        status, payload, content_type_in = self._send(
            method, path, query=query, body=body, raw_body=raw_body, content_type=content_type
        )

        if content_type_in.startswith("application/json"):
            try:
                parsed = json.loads(payload.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise BridgeError(
                    "bad_response",
                    f"{method} {path} answered {status} with a body that is not JSON",
                    status=status,
                ) from exc
            if isinstance(parsed, dict) and parsed.get("ok") is False:
                raise BridgeError(
                    str(parsed.get("error") or "error"),
                    str(parsed.get("detail") or "the device refused the call"),
                    status=status,
                )
            if status >= 400:
                # A non-JSON error envelope from something in front of the bridge
                # (a wrong port, a proxy, the app's own default page).
                raise BridgeError(
                    "bad_response",
                    f"{method} {path} answered {status} without the bridge's JSON envelope",
                    status=status,
                )
            return parsed

        if status >= 400:
            snippet = payload[:200].decode("utf-8", "replace")
            raise BridgeError(
                "bad_response",
                f"{method} {path} answered {status}: {snippet}",
                status=status,
            )
        return payload

    def probe(self) -> Any:
        return self.call("GET", "/probe")

    # -- transport ---------------------------------------------------------

    def _send(
        self,
        method: str,
        path: str,
        *,
        query: Mapping[str, Any] | None,
        body: Mapping[str, Any] | None,
        raw_body: bytes | None,
        content_type: str | None,
    ) -> tuple[int, bytes, str]:
        if not path.startswith("/"):
            raise ValueError(f"path must start with '/': {path!r}")

        url = self.config.base_url + path
        pairs = [(k, _stringify(v)) for k, v in (query or {}).items() if v is not None]
        if pairs:
            url = f"{url}?{urllib.parse.urlencode(pairs)}"

        headers = {"Accept": "application/json"}
        data: bytes | None = None
        if raw_body is not None:
            data = raw_body
            headers["Content-Type"] = content_type or "application/octet-stream"
        elif method.upper() in ("POST", "PUT", "PATCH", "DELETE"):
            data = json.dumps(dict(body or {})).encode("utf-8")
            headers["Content-Type"] = "application/json"

        request = urllib.request.Request(url, data=data, headers=headers, method=method.upper())

        try:
            with urllib.request.urlopen(request, timeout=self.config.timeout) as response:
                return (
                    response.status,
                    response.read(),
                    (response.headers.get("Content-Type") or "").split(";")[0].strip().lower(),
                )
        except urllib.error.HTTPError as exc:
            # The bridge answers errors with its own JSON envelope; read it rather
            # than discarding the detail the model needs.
            try:
                return (
                    exc.code,
                    exc.read(),
                    (exc.headers.get("Content-Type") or "").split(";")[0].strip().lower()
                    if exc.headers
                    else "",
                )
            finally:
                exc.close()
        except urllib.error.URLError as exc:
            reason = exc.reason
            if isinstance(reason, (TimeoutError, socket.timeout)):
                raise BridgeError(
                    "timeout",
                    f"{self.config.device} did not answer within {self.config.timeout:g}s",
                ) from exc
            raise BridgeError(
                "unreachable", f"no route to {self.config.device}: {reason}"
            ) from exc
        except (TimeoutError, socket.timeout) as exc:
            raise BridgeError(
                "timeout",
                f"{self.config.device} did not answer within {self.config.timeout:g}s",
            ) from exc
        except OSError as exc:
            raise BridgeError(
                "unreachable", f"connection to {self.config.device} failed: {exc}"
            ) from exc


def _stringify(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


#: What counts as "on" for a boolean setting. Anything else is off, because a
#: setting that cannot be read must not grant the more permissive behaviour.
_TRUTHY = frozenset({"1", "true", "yes", "on", "y", "t"})


def _as_bool(value: Any) -> bool:
    """Read a settings value as a boolean, defaulting to False."""
    if value is None or value == "":
        return False
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in _TRUTHY
