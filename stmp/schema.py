"""Tool schemas: what the model reads before it decides to call.

Every property here comes from the same `SPECS` table the dispatcher validates
against, so a schema cannot promise an argument the call would refuse. The words
are the only thing authored twice — once as documentation, once as validation —
and a test asserts the two name lists match.
"""

from __future__ import annotations

from typing import Any

from .handlers import SPECS

APPROVAL = (
    "Gated by the phone: unless stated otherwise, the call waits for a human to approve it on "
    "the device (60 s). An unapproved call returns why, and is never retried."
)

TOOL_DOCS: dict[str, str] = {
    "stmp_audio": (
        "Play one of three fixed attention cues on the phone. GATE-EXEMPT: this route runs with "
        "no approval modal, and can only ever play 'ping', 'chime' or 'alarm'. Use it to ask a "
        "human to look at the device; it cannot carry audio, a file or a URL."
    ),
    "stmp_calendar": (
        "Read and change the calendar on the phone's signed-in Google account. "
        + APPROVAL
        + " The calendar's Google token never reaches this machine."
    ),
    "stmp_contacts": (
        "Search the phone's contacts. Returns names with their numbers and addresses, capped at "
        "25 people; the query must be 2-64 characters. "
        + APPROVAL
    ),
    "stmp_debug": (
        "Read the phone's diagnostic report, or delete its request log. The report explains a "
        "broken bridge, so it is served even when the phone's model is not ready. "
        + APPROVAL
    ),
    "stmp_drive": (
        "List, read, download, upload, rename, move and trash files in the phone's Google Drive. "
        "`download` streams bytes to a path on this machine; `upload` sends a local file. "
        + APPROVAL
    ),
    "stmp_gmail": (
        "Read and send mail from the phone's signed-in Gmail account. "
        + APPROVAL
        + " Sending is described on the phone by recipient, subject and body before anyone approves."
    ),
    "stmp_help": (
        "Describe the connected STMP instance: app version, contract version, every plugin it "
        "serves and every route, with which routes are gated. Call this first on an unfamiliar "
        "install, and after the phone updates. "
        + APPROVAL
    ),
    "stmp_logs": (
        "Read the STMP app's own logcat, optionally filtered. Use it when the bridge misbehaves. "
        + APPROVAL
    ),
    "stmp_notifications": (
        "List the phone's notifications, fire one of their actions, or dismiss one. "
        + APPROVAL
    ),
    "stmp_probe": (
        "Check that a human is actually reachable through the approval gate: the request only "
        "reaches the handler after someone approved it. Call it before starting a multi-step run "
        "that will need several approvals — if it fails, a person is not at the phone and the run "
        "should stop instead of stacking up prompts. "
        + APPROVAL
    ),
    "stmp_secrets": (
        "Use the phone's credential vault without ever seeing a value. `list` and `get` return "
        "names, docs links and allowed hosts only; `call` asks the phone to make an HTTP request "
        "with a stored secret attached, inside that secret's own host allowlist. No secret value "
        "crosses to this machine, and there is no argument that could ask for one. "
        + APPROVAL
    ),
    "stmp_ssh": (
        "Run a command over SSH through a key stored on the phone. The private key never leaves "
        "the device, and the approval prompt shows the command. `run` waits for the result; "
        "`detach` starts it and returns a job id; `job` reads a detached job's output. "
        + APPROVAL
    ),
    "stmp_tts": (
        "Speak text aloud through the phone's text-to-speech. GATE-EXEMPT: this route runs with no "
        "approval modal. It speaks the string it is given and nothing else."
    ),
}

ACTION_DOCS: dict[tuple[str, str], str] = {
    ("stmp_audio", "cue"): "Play 'ping', 'chime' or 'alarm'.",
    ("stmp_calendar", "list"): "List events in a window. timeMin/timeMax/timeZone are required.",
    ("stmp_calendar", "create"): "Create an event. summary/start/end/timeZone are required.",
    ("stmp_calendar", "update"): "Replace an event's fields (PATCH semantics, full fields required).",
    ("stmp_calendar", "delete"): "Delete an event, returning it read back.",
    ("stmp_calendar", "move"): "Move an event to another calendar (calendarId is the destination).",
    ("stmp_calendar", "quickadd"): "Let Google parse natural language; the zone must match the calendar's.",
    ("stmp_contacts", "search"): "Find people by name or number.",
    ("stmp_debug", "report"): "Read the diagnostic report.",
    ("stmp_debug", "audit_clear"): "Delete the request log on the phone.",
    ("stmp_drive", "list"): "List or search files.",
    ("stmp_drive", "get"): "Show one file's metadata.",
    ("stmp_drive", "download"): "Download a file into download_dir (save_to relative to it).",
    ("stmp_drive", "create_folder"): "Create a folder.",
    ("stmp_drive", "rename"): "Rename a file or folder.",
    ("stmp_drive", "move"): "Move a file into another folder.",
    ("stmp_drive", "trash"): "Move a file to the trash.",
    ("stmp_drive", "upload"): "Upload a local file (file_path; name/parent/type optional).",
    ("stmp_gmail", "profile"): "Show the signed-in address and totals.",
    ("stmp_gmail", "list"): "List messages (default q 'in:inbox', max 20 of 1..100).",
    ("stmp_gmail", "read"): "Read one message including its plain-text body.",
    ("stmp_gmail", "modify"): "Add or remove labels on a message.",
    ("stmp_gmail", "trash"): "Move a message to the trash.",
    ("stmp_gmail", "send"): "Send a message. to[]/subject/body are required.",
    ("stmp_help", "contract"): "The instance's full capability contract.",
    ("stmp_logs", "read"): "Read recent logcat lines, optionally filtered.",
    ("stmp_notifications", "list"): "List notifications, optionally by package and most-recent count.",
    ("stmp_notifications", "act"): "Fire one of a notification's actions (index or label).",
    ("stmp_notifications", "dismiss"): "Dismiss a notification.",
    ("stmp_probe", "reach"): "Prove the approval gate can reach a human right now.",
    ("stmp_secrets", "list"): "List stored secret names with metadata (never values).",
    ("stmp_secrets", "get"): "One secret's metadata (never the value).",
    ("stmp_secrets", "call"): "Make an HTTP request with a stored secret attached.",
    ("stmp_ssh", "run"): "Run a command and wait for its output.",
    ("stmp_ssh", "detach"): "Start a long command in the background; returns a job id.",
    ("stmp_ssh", "job"): "Read a detached job's output.",
    ("stmp_tts", "speak"): "Speak text aloud.",
}

PARAM_DOCS: dict[str, str] = {
    "action": "Which operation to run. See the action list in this description.",
    "id": "Target id on the phone (message, event, file, notification, SSH job).",
    "name": "Target name: a stored secret, an SSH connection, or the file being created.",
    "cue": "One of 'ping', 'chime', 'alarm'.",
    "text": "Text to speak.",
    "query": "Search text (contacts: 2-64 characters; secrets.call: query parameters object).",
    "max": "Maximum results to return.",
    "q": "Gmail search query, or a Drive search expression.",
    "pageToken": "Pagination token from a previous page.",
    "timeMin": "Window start, RFC 3339 instant.",
    "timeMax": "Window end, RFC 3339 instant, after timeMin.",
    "timeZone": "IANA zone id, e.g. Europe/Berlin.",
    "singleEvents": "Expand recurring events into instances (default true).",
    "orderBy": "Ordering, e.g. startTime.",
    "calendarId": "Calendar id; 'primary' if omitted.",
    "fromCalendarId": "Source calendar when moving; 'primary' if omitted.",
    "summary": "Event title.",
    "start": "Event start, RFC 3339 instant.",
    "end": "Event end, RFC 3339 instant.",
    "description": "Event description.",
    "location": "Event location.",
    "attendees": "Array of attendee email addresses.",
    "to": "Array of recipient email addresses.",
    "cc": "Array of cc addresses.",
    "bcc": "Array of bcc addresses.",
    "subject": "Message subject.",
    "body": "Message body text (secrets.call: request body string).",
    "threadId": "Gmail thread to reply into.",
    "addLabels": "Array of label ids to add.",
    "removeLabels": "Array of label ids to remove.",
    "package": "Android package name to filter notifications by.",
    "count": "How many of the most recent notifications to return.",
    "replyText": "Text for a Reply action; required by the phone for that action.",
    "notification_action": (
        "Which action to fire on the notification: its index, or its label. The phone names "
        "the available actions per notification."
    ),
    "lines": "How many logcat lines (1..500).",
    "filter": "Only keep lines containing this substring.",
    "url": "Absolute URL the phone should call with the secret attached.",
    "method": "HTTP method for secrets.call (GET, POST, PUT, PATCH, DELETE, HEAD).",
    "headers": "Object of header name to value; the secret is substituted by the phone.",
    "command": "Shell command to run on the SSH host.",
    "trustHostKey": "Fingerprint to pin for an unknown host; only a human can confirm it.",
    "timeoutMs": "Deadline in milliseconds.",
    "file_path": "Absolute path on this machine to upload; must be inside upload_dir when set.",
    "save_to": "Path to write the download to, relative to download_dir (or absolute inside it).",
    "parent": "Destination folder id for an upload.",
    "parentId": "Destination folder id.",
    "type": "MIME type; guessed from the file name when omitted.",
}


def schema_for(tool: str) -> dict[str, Any]:
    specs = {action: spec for (owner, action), spec in SPECS.items() if owner == tool}
    if not specs:
        raise ValueError(f"{tool} has no actions")

    actions = sorted(specs)
    properties: dict[str, Any] = {
        "action": {
            "type": "string",
            "enum": actions,
            "description": "\n".join(f"- {a}: {ACTION_DOCS[(tool, a)]}" for a in actions),
        }
    }
    for arg in sorted({arg for spec in specs.values() for arg in spec.args()}):
        properties[arg] = {
            "type": "string",
            "description": PARAM_DOCS[arg],
        }

    # Every route on the phone is JSON, and the only non-strings are the ones the
    # dispatch table marks: typed here so the model sends an array, not "[a, b]".
    for spec in specs.values():
        for arg, kind in spec.kinds.items():
            if kind == "int":
                properties[arg]["type"] = "integer"
            elif kind == "bool":
                properties[arg]["type"] = "boolean"
            elif kind == "list":
                properties[arg] = {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": PARAM_DOCS[arg],
                }
            elif kind == "dict":
                properties[arg] = {
                    "type": "object",
                    "description": PARAM_DOCS[arg],
                    "additionalProperties": {"type": "string"},
                }

    return {
        "name": tool,
        "description": TOOL_DOCS[tool],
        "parameters": {
            "type": "object",
            "properties": properties,
            "required": ["action"],
            "additionalProperties": False,
        },
    }


TOOL_SCHEMAS: dict[str, dict[str, Any]] = {
    tool: schema_for(tool) for tool in TOOL_DOCS
}
