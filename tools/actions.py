"""The authored half of the contract: one action name per pinned route.

`sync_contract.py` reads the route set out of STMP's own `HelpContractTest.kt`.
This module supplies the only thing that file cannot: what a caller *calls* each
route. Every route must appear exactly once, under the tool that matches its
plugin class, or generation fails. That is deliberate — a new route in the app
must not silently become an unreachable capability here.
"""

#: tool -> {action: "METHOD /path"}
ACTIONS: dict[str, dict[str, str]] = {
    "stmp_audio": {
        "cue": "POST /audio/{cue}",
    },
    "stmp_calendar": {
        "list": "GET /calendar/events",
        "create": "POST /calendar/events",
        "update": "POST /calendar/events/{id}",
        "delete": "DELETE /calendar/events/{id}",
        "move": "POST /calendar/events/{id}/move",
        "quickadd": "POST /calendar/quickadd",
    },
    "stmp_contacts": {
        "search": "GET /contacts",
    },
    "stmp_debug": {
        "report": "GET /debug",
        "audit_clear": "DELETE /audit",
    },
    "stmp_drive": {
        "list": "GET /drive/files",
        "get": "GET /drive/files/{id}",
        "download": "GET /drive/files/{id}/content",
        "create_folder": "POST /drive/files",
        "rename": "POST /drive/files/{id}/rename",
        "move": "POST /drive/files/{id}/move",
        "trash": "POST /drive/files/{id}/trash",
        "upload": "POST /drive/files/upload",
    },
    "stmp_gmail": {
        "profile": "GET /gmail/profile",
        "list": "GET /gmail/messages",
        "read": "GET /gmail/messages/{id}",
        "modify": "POST /gmail/messages/{id}/modify",
        "trash": "POST /gmail/messages/{id}/trash",
        "send": "POST /gmail/messages/send",
    },
    "stmp_help": {
        "contract": "GET /help",
    },
    "stmp_logs": {
        "read": "GET /logs",
    },
    "stmp_notifications": {
        "list": "GET /notifications",
        "act": "POST /notifications/{id}/action",
        "dismiss": "POST /notifications/{id}/dismiss",
    },
    "stmp_probe": {
        "reach": "GET /probe",
    },
    "stmp_secrets": {
        "list": "GET /secrets",
        "get": "GET /secrets/{name}",
        "call": "POST /secrets/{name}/call",
    },
    "stmp_ssh": {
        "run": "POST /ssh/{name}",
        "detach": "POST /ssh/{name}/detach",
        "job": "GET /ssh/job/{id}",
    },
    "stmp_tts": {
        "speak": "POST /tts",
    },
}

#: Which plugin class owns a path prefix. Used to prove each action sits under the
#: tool that matches the app's own taxonomy. Order matters: first match wins.
PREFIX_TO_TOOL: list[tuple[str, str]] = [
    ("/audio/", "stmp_audio"),
    ("/tts", "stmp_tts"),
    ("/calendar/", "stmp_calendar"),
    ("/contacts", "stmp_contacts"),
    ("/audit", "stmp_debug"),
    ("/debug", "stmp_debug"),
    ("/drive/", "stmp_drive"),
    ("/gmail/", "stmp_gmail"),
    ("/help", "stmp_help"),
    ("/logs", "stmp_logs"),
    ("/notifications", "stmp_notifications"),
    ("/probe", "stmp_probe"),
    ("/secrets", "stmp_secrets"),
    ("/ssh/", "stmp_ssh"),
]


def tool_for_path(path: str) -> str | None:
    for prefix, tool in PREFIX_TO_TOOL:
        if path.startswith(prefix):
            return tool
    return None


def routes_by_tool() -> dict[str, dict[str, str]]:
    """tool -> {route: action}, for the cross-check in generate.py."""
    out: dict[str, dict[str, str]] = {}
    for tool, actions in ACTIONS.items():
        for action, route in actions.items():
            bucket = out.setdefault(tool, {})
            if route in bucket:
                raise ValueError(
                    f"{tool} claims {route!r} twice ({bucket[route]!r} and {action!r})"
                )
            bucket[route] = action
    return out
