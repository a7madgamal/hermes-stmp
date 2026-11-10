"""Host-side implementation of the STMP Hermes plugin.

Modules
    bridge    one JSON client for the phone; no retries, by design
    errors    every failure code translated into its next step
    dispatch  GENERATED from STMP's own contract test
    handlers  the argument allowlist and the call
    schema    what the model is shown, derived from the same allowlist
    snapshot  what the connected instance can do, remembered on change
"""

from __future__ import annotations

__all__ = ["bridge", "dispatch", "errors", "handlers", "schema", "snapshot"]
