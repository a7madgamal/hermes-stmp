"""What the *connected* instance can do, as opposed to what the plugin ships.

The plugin's surface is fixed at generation time (37 pinned routes on contract
version 4). The phone in front of it may be older, newer, or have plugins
switched off. `stmp_help` answers that; this module remembers the last answer so a
drift is visible instead of silent.

Writes only when the device's capabilities change, through Hermes's own
`ctx.state` store — never into the installed plugin tree, which would be
self-modifying code the catalog declines.
"""

from __future__ import annotations

import time
from typing import Any

from .dispatch import CONTRACT_VERSION

STATE_KEY = "device"


def _fingerprint(contract_version: int | None, plugins: list[dict[str, Any]]) -> str:
    parts = [f"v{contract_version}"]
    for plugin in plugins:
        parts.append(f"{plugin.get('id')}:{len(plugin.get('routes') or [])}")
    return "|".join(parts)


def record(ctx: Any, help_payload: dict[str, Any]) -> str | None:
    """Store the device snapshot; return a note when it differs from what we ship."""
    stmp = help_payload.get("stmp") or {}
    plugins = [
        {"id": p.get("id"), "routes": p.get("routes") or []}
        for p in (help_payload.get("plugins") or [])
        if isinstance(p, dict)
    ]
    device_version = stmp.get("contractVersion")
    if not isinstance(device_version, int):
        return None

    fingerprint = _fingerprint(device_version, plugins)
    state = ctx.state
    previous = state.get(STATE_KEY) or {}
    if previous.get("fingerprint") != fingerprint:
        state.set(
            STATE_KEY,
            {
                "fingerprint": fingerprint,
                "contract_version": device_version,
                "app_version": stmp.get("appVersion"),
                "app_build": stmp.get("appBuild"),
                "plugins": [{"id": p["id"], "routes": len(p["routes"])} for p in plugins],
                "ssh_connections": help_payload.get("sshConnections") or [],
                "seen_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            },
        )

    if device_version < CONTRACT_VERSION:
        return (
            f"This phone reports contract version {device_version}, older than the "
            f"{CONTRACT_VERSION} this plugin was generated from. Some routes may answer "
            "'not_found'. Update the STMP app on the phone."
        )
    if device_version > CONTRACT_VERSION:
        return (
            f"This phone reports contract version {device_version}, newer than the "
            f"{CONTRACT_VERSION} this plugin was generated from. Everything here still works; "
            "newer routes are not exposed until the plugin is regenerated."
        )
    return None
