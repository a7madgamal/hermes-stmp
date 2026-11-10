"""What each action takes, and how it is sent.

Two tables, both complete by construction: `SPECS` names the arguments an action
accepts, and `tools/dispatch.py` names its route. `tests/test_surface.py` fails if
either table misses an action, so "declared = callable" is checked, not hoped for.

Arguments are an allowlist, not a suggestion. An unknown key is refused with the
list of keys that action takes: silently dropping `subjet` would send an email
with no subject and call it success.
"""

from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from . import snapshot
from .bridge import Bridge, BridgeError, Config, ConfigError
from .dispatch import DISPATCH, EXEMPT
from .errors import explain

#: A tool result longer than this is cut with a marker. `/help` and `/debug` are
#: tens of kilobytes; pasting all of it into the turn costs context and adds
#: nothing a model can use.
MAX_RESULT_CHARS = 40_000
MAX_UPLOAD_BYTES = 100 * 1024 * 1024


@dataclass(frozen=True)
class Spec:
    """One action's argument contract."""

    path: tuple[str, ...] = ()
    query: tuple[str, ...] = ()
    body: tuple[str, ...] = ()
    required: tuple[str, ...] = ()
    kinds: Mapping[str, str] = field(default_factory=dict)
    stream: str | None = None  # "out" (bytes to host) or "in" (host file to device)
    allowed: tuple[str, ...] = ()  # closed value set, e.g. audio cues
    #: tool argument -> the name the phone expects. Only where the wire name would
    #: collide with the tool's own selector (notifications: body field `action`).
    wire: Mapping[str, str] = field(default_factory=dict)

    def args(self) -> tuple[str, ...]:
        extra = ("save_to",) if self.stream == "out" else ()
        extra += ("file_path",) if self.stream == "in" else ()
        return tuple(dict.fromkeys(self.path + self.query + self.body + extra))

    def wire_name(self, key: str) -> str:
        return self.wire.get(key, key)


PING, CHIME, ALARM = "ping", "chime", "alarm"

SPECS: dict[tuple[str, str], Spec] = {
    # -- audio / tts (the two gate-exempt routes; disclosed in every description) --
    ("stmp_audio", "cue"): Spec(path=("cue",), required=("cue",), allowed=(PING, CHIME, ALARM)),
    ("stmp_tts", "speak"): Spec(body=("text",), required=("text",)),
    # -- calendar --
    ("stmp_calendar", "list"): Spec(
        query=("timeMin", "timeMax", "timeZone", "max", "singleEvents", "orderBy",
               "pageToken", "q", "calendarId"),
        required=("timeMin", "timeMax", "timeZone"),
        kinds={"max": "int", "singleEvents": "bool"},
    ),
    ("stmp_calendar", "create"): Spec(
        body=("summary", "start", "end", "timeZone", "calendarId", "description",
              "location", "attendees"),
        required=("summary", "start", "end", "timeZone"),
        kinds={"attendees": "list"},
    ),
    ("stmp_calendar", "update"): Spec(
        path=("id",),
        body=("summary", "start", "end", "timeZone", "calendarId", "description", "location"),
        required=("id", "summary", "start", "end", "timeZone"),
    ),
    ("stmp_calendar", "delete"): Spec(
        path=("id",), query=("calendarId",), required=("id",)
    ),
    ("stmp_calendar", "move"): Spec(
        path=("id",), body=("calendarId", "fromCalendarId"), required=("id", "calendarId")
    ),
    ("stmp_calendar", "quickadd"): Spec(
        body=("text", "timeZone", "calendarId"), required=("text", "timeZone")
    ),
    # -- contacts --
    ("stmp_contacts", "search"): Spec(query=("query",), required=("query",)),
    # -- diagnostics --
    ("stmp_debug", "report"): Spec(),
    ("stmp_debug", "audit_clear"): Spec(),
    ("stmp_help", "contract"): Spec(),
    ("stmp_logs", "read"): Spec(query=("lines", "filter"), kinds={"lines": "int"}),
    ("stmp_probe", "reach"): Spec(),
    # -- drive --
    ("stmp_drive", "list"): Spec(
        query=("max", "q", "pageToken"), kinds={"max": "int"}
    ),
    ("stmp_drive", "get"): Spec(path=("id",), required=("id",)),
    ("stmp_drive", "download"): Spec(path=("id",), required=("id", "save_to"), stream="out"),
    ("stmp_drive", "create_folder"): Spec(body=("name", "parentId"), required=("name",)),
    ("stmp_drive", "rename"): Spec(path=("id",), body=("name",), required=("id", "name")),
    ("stmp_drive", "move"): Spec(path=("id",), body=("parentId",), required=("id", "parentId")),
    ("stmp_drive", "trash"): Spec(path=("id",), required=("id",)),
    ("stmp_drive", "upload"): Spec(
        query=("name", "parent", "type"), required=("file_path",), stream="in"
    ),
    # -- gmail --
    ("stmp_gmail", "profile"): Spec(),
    ("stmp_gmail", "list"): Spec(
        query=("max", "q", "pageToken"), kinds={"max": "int"}
    ),
    ("stmp_gmail", "read"): Spec(path=("id",), required=("id",)),
    ("stmp_gmail", "modify"): Spec(
        path=("id",),
        body=("addLabels", "removeLabels"),
        required=("id",),
        kinds={"addLabels": "list", "removeLabels": "list"},
    ),
    ("stmp_gmail", "trash"): Spec(path=("id",), required=("id",)),
    ("stmp_gmail", "send"): Spec(
        body=("to", "cc", "bcc", "subject", "body", "threadId"),
        required=("to", "subject", "body"),
        kinds={"to": "list", "cc": "list", "bcc": "list"},
    ),
    # -- notifications --
    ("stmp_notifications", "list"): Spec(query=("package", "count"), kinds={"count": "int"}),
    ("stmp_notifications", "act"): Spec(
        path=("id",),
        body=("notification_action", "replyText"),
        required=("id", "notification_action"),
        wire={"notification_action": "action"},
    ),
    ("stmp_notifications", "dismiss"): Spec(path=("id",), required=("id",)),
    # -- secrets (metadata and brokered calls; a value is never returned) --
    ("stmp_secrets", "list"): Spec(),
    ("stmp_secrets", "get"): Spec(path=("name",), required=("name",)),
    ("stmp_secrets", "call"): Spec(
        path=("name",),
        body=("url", "method", "headers", "query", "body"),
        required=("name", "url"),
        kinds={"headers": "dict", "query": "dict"},
    ),
    # -- ssh --
    ("stmp_ssh", "run"): Spec(
        path=("name",),
        body=("command", "trustHostKey", "timeoutMs"),
        required=("name", "command"),
        kinds={"timeoutMs": "int"},
    ),
    ("stmp_ssh", "detach"): Spec(
        path=("name",),
        body=("command", "trustHostKey", "timeoutMs"),
        required=("name", "command"),
        kinds={"timeoutMs": "int"},
    ),
    ("stmp_ssh", "job"): Spec(path=("id",), required=("id",)),
}


class UsageError(Exception):
    """The model called the tool with arguments the action does not take."""


def run(ctx: Any, tool: str, args: Mapping[str, Any]) -> str:
    """Execute one tool call. Returns text for the model, never raises for a
    device-side failure."""
    action = args.get("action")
    if not isinstance(action, str) or not action:
        raise UsageError(
            f"{tool} needs an 'action'. One of: {', '.join(sorted(DISPATCH[tool]))}"
        )

    route = DISPATCH[tool].get(action)
    if route is None:
        raise UsageError(
            f"{tool} has no action {action!r}. One of: {', '.join(sorted(DISPATCH[tool]))}"
        )

    spec = SPECS.get((tool, action))
    if spec is None:
        # A route with no argument contract would be called blind. Fail loudly;
        # tests keep this unreachable.
        raise RuntimeError(f"{tool}.{action} has a route but no argument spec")

    cleaned = _validate(tool, action, spec, args)
    method, path = route

    try:
        config = Config.from_settings(
            ctx.get_config("base_url", None), ctx.get_config("timeout_seconds", None)
        )
        bridge = Bridge(config)
        expanded = _expand(path, cleaned)

        if spec.stream == "in":
            return _upload(bridge, method, expanded, spec, cleaned)
        if spec.stream == "out":
            return _download(bridge, method, expanded, cleaned)

        payload = bridge.call(
            method,
            expanded,
            query={spec.wire_name(key): cleaned[key] for key in spec.query if key in cleaned},
            body={spec.wire_name(key): cleaned[key] for key in spec.body if key in cleaned},
        )
        text = _render(payload)
        if (tool, action) == ("stmp_help", "contract") and isinstance(payload, dict):
            note = snapshot.record(ctx, payload)
            if note:
                text = f"{note}\n\n{text}"
        return text
    except (BridgeError, ConfigError) as exc:
        return explain(exc)


# -- validation ------------------------------------------------------------


def _validate(tool: str, action: str, spec: Spec, args: Mapping[str, Any]) -> dict[str, Any]:
    provided = {key: value for key, value in args.items() if key != "action" and value is not None}
    allowed = spec.args()
    unknown = sorted(set(provided) - set(allowed))
    if unknown:
        raise UsageError(
            f"{tool}.{action} does not take {', '.join(repr(k) for k in unknown)}. "
            f"It takes: {', '.join(allowed) if allowed else '(no arguments)'}"
        )

    missing = [key for key in spec.required if key not in provided or provided[key] == ""]
    if missing:
        raise UsageError(
            f"{tool}.{action} requires {', '.join(missing)}. "
            f"Accepts: {', '.join(allowed)}"
        )

    out: dict[str, Any] = {}
    for key, value in provided.items():
        kind = spec.kinds.get(key, "str")
        out[key] = _coerce(tool, action, key, kind, value)

    if spec.allowed:
        for key in spec.path + spec.body + spec.query:
            if key in out and out[key] not in spec.allowed:
                raise UsageError(
                    f"{tool}.{action} accepts {key} in {', '.join(spec.allowed)} — "
                    f"got {out[key]!r}"
                )
    return out


def _coerce(tool: str, action: str, key: str, kind: str, value: Any) -> Any:
    if kind == "int":
        if isinstance(value, bool):
            raise UsageError(f"{tool}.{action}: {key} must be an integer, not a boolean")
        if isinstance(value, int):
            return value
        try:
            return int(str(value).strip())
        except (TypeError, ValueError) as exc:
            raise UsageError(f"{tool}.{action}: {key} must be an integer, got {value!r}") from exc
    if kind == "bool":
        if isinstance(value, bool):
            return value
        text = str(value).strip().lower()
        if text in ("true", "1", "yes"):
            return True
        if text in ("false", "0", "no"):
            return False
        raise UsageError(f"{tool}.{action}: {key} must be true or false, got {value!r}")
    if kind == "list":
        if isinstance(value, str):
            raise UsageError(
                f"{tool}.{action}: {key} must be a JSON array of strings, not a string"
            )
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            raise UsageError(f"{tool}.{action}: {key} must be a JSON array of strings")
        return value
    if kind == "dict":
        if not isinstance(value, dict):
            raise UsageError(f"{tool}.{action}: {key} must be a JSON object")
        return {str(k): str(v) for k, v in value.items()}
    if not isinstance(value, str):
        raise UsageError(f"{tool}.{action}: {key} must be a string, got {type(value).__name__}")
    return value


def _expand(path: str, values: Mapping[str, Any]) -> str:
    """Fill `{id}`-style path segments, quoting every value."""
    out = path
    for key in ("id", "name", "cue"):
        token = "{" + key + "}"
        if token in out:
            if key not in values:
                raise UsageError(f"route {path} needs {key!r}")
            out = out.replace(token, urllib.parse.quote(str(values[key]), safe=""))
    if "{" in out:
        raise RuntimeError(f"unexpanded path template: {out}")
    return out


# -- streaming routes ------------------------------------------------------


def _upload(bridge: Bridge, method: str, path: str, spec: Spec, values: Mapping[str, Any]) -> str:
    source = Path(os.path.expanduser(str(values["file_path"])))
    if not source.is_absolute():
        raise UsageError(f"file_path must be absolute, got {str(source)!r}")
    if not source.is_file():
        raise UsageError(f"file_path is not a readable file: {source}")
    size = source.stat().st_size
    if size > MAX_UPLOAD_BYTES:
        raise UsageError(
            f"file is {size} bytes; this tool uploads at most {MAX_UPLOAD_BYTES} bytes"
        )

    name = values.get("name") or source.name
    content_type = values.get("type") or mimetypes.guess_type(name)[0] or "application/octet-stream"
    query = {"name": name, "type": content_type}
    if values.get("parent"):
        query["parent"] = values["parent"]

    payload = bridge.call(
        method, path, query=query, raw_body=source.read_bytes(), content_type=content_type
    )
    return _render(payload)


def _download(bridge: Bridge, method: str, path: str, values: Mapping[str, Any]) -> str:
    target = Path(os.path.expanduser(str(values["save_to"])))
    if not target.is_absolute():
        raise UsageError(f"save_to must be absolute, got {str(target)!r}")
    if target.is_dir():
        raise UsageError(f"save_to is a directory: {target}")
    if not target.parent.is_dir():
        raise UsageError(f"save_to's parent directory does not exist: {target.parent}")

    payload = bridge.call(method, path, query={})
    if not isinstance(payload, bytes):
        # /drive/files/{id}/content streams bytes; anything else here is a broken
        # expectation, not a file to guess about.
        raise RuntimeError("download route answered with JSON instead of bytes")
    target.write_bytes(payload)
    return json.dumps(
        {
            "ok": True,
            "saved_to": str(target),
            "bytes": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
        },
        indent=2,
    )


# -- rendering -------------------------------------------------------------


def _render(payload: Any) -> str:
    if isinstance(payload, bytes):
        raise RuntimeError("a streaming route returned bytes on a non-streaming action")
    text = json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True)
    if len(text) > MAX_RESULT_CHARS:
        return (
            text[:MAX_RESULT_CHARS]
            + f"\n… truncated: {len(text)} characters in total. "
            "Narrow the call (fewer lines, a filter, a smaller max) to see the rest."
        )
    return text


__all__ = ["SPECS", "run", "UsageError", "EXEMPT"]
