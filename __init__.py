"""STMP: a phone as the trust boundary between the agent and its credentials.

Thirteen tools, one per plugin class the STMP app exposes, and one rule the host
side never breaks: no credential is stored here. The vault, the Google tokens and
the SSH keys live on the phone, and every gated call waits for a human to approve
it on that device.

Everything below registers unconditionally. Declared capabilities must match what
`register()` registers, so there is no `check_fn` hiding a tool from validation —
a tool that cannot work explains itself when called.
"""

from __future__ import annotations

from pathlib import Path

from .stmp.handlers import UsageError, run
from .stmp.schema import TOOL_SCHEMAS

TOOLSET = "stmp"
EMOJI = "\U0001f4f1"  # mobile phone


def register(ctx) -> None:
    for name, schema in TOOL_SCHEMAS.items():
        ctx.register_tool(
            name=name,
            toolset=TOOLSET,
            schema=schema,
            handler=_bind(ctx, name),
            description=schema["description"],
            emoji=EMOJI,
        )

    ctx.register_skill(
        name="stmp",
        path=Path(__file__).resolve().parent / "skills" / "stmp" / "SKILL.md",
        description=(
            "How to work with an STMP phone: approve-gated routes, the credential vault, and "
            "what to do when the phone refuses."
        ),
    )


def _bind(ctx, tool: str):
    """One handler per tool, closed over the plugin context."""

    def handler(args, **_kwargs):
        try:
            return run(ctx, tool, args or {})
        except UsageError as exc:
            # A wrong call is not a crash: say what the action takes and stop.
            return f"Tool call rejected: {exc}"

    return handler
