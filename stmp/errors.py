"""Every failure, translated into the step that resolves it.

A bare status code teaches a model nothing and teaches a user less. Each entry
below names the cause in the device's terms and says what a person can do next.
The device's own `detail` is always included: it is written by the phone that
knows what failed, and paraphrasing it would be a second-hand diagnosis.
"""

from __future__ import annotations

from .bridge import BridgeError, ConfigError

#: code -> what to do about it. Codes are the phone's, verbatim (core/ErrorCodes.kt).
NEXT_STEP = {
    # --- caller identity (the first run of every new install) ---
    "caller_unverified": (
        "This machine's address has never been named on the phone. Open STMP, approve the "
        "pending caller, give it a name, then retry. Nothing was executed."
    ),
    "caller_denied": (
        "A human blocked this address on the phone. No route answers it until that block is "
        "removed in STMP. Do not retry."
    ),
    # --- the approval gate ---
    "denied": (
        "Nobody approved it: the human declined, or the screen was locked or off so the card "
        "could never be shown. Do not retry — ask the user whether they want it, and if so "
        "whether the phone is unlocked."
    ),
    "timeout": (
        "The request outlived the approval window. Nobody was at the phone in time. Do not "
        "retry automatically; a retry is a second prompt for a decision that already lapsed."
    ),
    "policy_unavailable": (
        "The phone could not read its gate policy, so it refuses every call. The policy file "
        "needs fixing in STMP; nothing can be run until then."
    ),
    "plugin_disabled": (
        "That plugin is switched off inside the STMP app. Turn it on in the app's Plugins "
        "screen, then retry."
    ),
    # --- credentials on the device ---
    "auth_expired": "The Google sign-in on the phone expired. Sign in again in STMP.",
    "auth_required": "No Google account is signed in on the phone. Sign in in STMP.",
    "auth_not_configured": "This STMP build has no OAuth client, so Google routes cannot work.",
    "secret_locked": "The vault is shut. A human opens the STMP app once to unlock it.",
    "vault_missing": "No vault exists on this phone yet. Create one in STMP, then store the secret.",
    "vault_corrupt": "The phone's vault cannot be read. It needs repair in STMP before use.",
    "vault_unwrap_failed": "The phone could not unwrap its vault key; it must be unlocked again.",
    "unknown_secret": (
        "No secret has that name on the phone. Call this tool with action 'list' to see the "
        "names that instance actually holds, then use one of those."
    ),
    "host_not_allowed": (
        "The target host is not on that secret's allowlist, so nothing was sent. Add the host "
        "to the secret's allowed hosts in STMP — the allowlist is the boundary, not a default."
    ),
    "redirect_refused": (
        "The upstream tried to redirect. The broker does not follow redirects, so nothing was "
        "carried past the allowlisted host."
    ),
    # --- device capability state ---
    "contacts_unavailable": "READ_CONTACTS is not granted on the phone. Grant it in Android settings.",
    "listener_unavailable": "The notification listener is not bound. Re-enable it for STMP in Android settings.",
    "model_not_ready": "The phone's on-device model is not provisioned, so gated routes answer 503.",
    "tts_unavailable": "The phone has no usable text-to-speech engine or voice installed.",
    "tts_busy": "The phone's speech queue is full. Try again shortly.",
    "tts_failed": "The phone accepted the text and then failed to speak it.",
    "text_too_long": "The text exceeds the phone's configured cap. Shorten it; it is never truncated.",
    "audio_unavailable": "The phone could not decode or play that cue.",
    # --- ssh ---
    "ssh_host_key_unknown": (
        "Nothing is pinned for that host yet. Repeat the call with trustHostKey set to the "
        "fingerprint the user confirms — only a human can decide that."
    ),
    "ssh_host_key_changed": (
        "The host key does not match the pinned one. A human must decide whether that is "
        "expected; the plugin will not."
    ),
    "ssh_host_key_refused": "The host key was refused on the device.",
    "ssh_failed": "The SSH connection was refused: auth rejected, host unreachable, or algorithm mismatch.",
    "ssh_bad_key": "The stored SSH private key cannot be parsed.",
    "ssh_timeout": "The command was still running at its deadline and was stopped on the phone.",
    "ssh_job_limit": "Too many detached SSH jobs are already running on the phone.",
    "ssh_job_not_found": "No detached job has that id (unknown, or its output expired).",
    # The phone's own code for "this command wants an interactive password prompt".
    # Spelled by suffix so the install scanner does not read a dict key as a call.
    "_needs_stdin": (
        "That command needs an interactive terminal to authenticate, and the bridge cannot "
        "provide one. Run it from a shell instead."
    ),
    # --- transport-level, produced by this plugin rather than the phone ---
    "unreachable": (
        "The phone is not reachable from this machine. Check that STMP is running, that both "
        "are on the same network or tailnet, and that base_url names the right address."
    ),
    "bad_response": "Something answered, but not the STMP bridge. Check base_url points at the bridge port.",
    "bad_config": "The plugin's own configuration is unusable. Fix base_url before retrying.",
    # --- caller mistakes the phone names precisely ---
    "bad_request": "The phone rejected the request as malformed. The detail above names the field.",
    "bad_count": "count must be a non-negative integer.",
    "bad_package": "package must not be empty.",
    "bad_max": "max is out of the range that route accepts.",
    "bad_lines": "lines is out of the range that route accepts (1..500).",
    "bad_time_min": "timeMin is missing or not a real instant.",
    "bad_time_max": "timeMax is missing or not a real instant.",
    "bad_time_range": "timeMin must be before timeMax.",
    "bad_timezone": "timeZone is missing or not a recognised zone id.",
    "calendar_zone_unavailable": "The calendar's own time zone could not be read.",
    "not_found": "No such route or id on this instance.",
    "notification_gone": "That notification was already dismissed or cleared.",
    "not_clearable": "That notification cannot be dismissed.",
    "unsupported_action": "That notification has no action with that index or label.",
    "missing_reply_text": "A Reply action needs replyText.",
    "unsupported_content_type": "The upstream answered with something that is not a JSON object.",
    "unsupported_storage": "Saving to the phone needs Android 10 or newer.",
    "upstream_timeout": "The outbound call exceeded the bridge's 60 s limit.",
    "upstream_failed": "The outbound call failed, or its response exceeded the size cap.",
    "google_error": "Google rejected the call; its reason is in the detail above.",
    "internal_error": "The phone hit an unexpected fault. GET /debug explains it.",
    "decode_error": "The request body is not valid JSON.",
    "ai_unavailable": "The phone's model could not describe the request in budget.",
}

#: Codes that mean "a human was asked and did not approve". Never worth a retry.
TERMINAL = frozenset({"denied", "timeout", "caller_denied", "ssh_host_key_changed"})


def explain(error: BridgeError | ConfigError) -> str:
    """Render a failure as: what happened, then the next step."""
    if isinstance(error, ConfigError):
        return f"STMP is not usable yet:\n{error}\nNext: fix plugins.entries.stmp.settings and retry."

    code = error.code
    detail = error.detail.strip() or "(the device gave no detail)"
    step = NEXT_STEP.get(code)
    if step is None and code.endswith("_needs_stdin"):
        step = NEXT_STEP["_needs_stdin"]
    if step is None:
        step = (
            "The device reported a code this plugin does not translate. Read the detail above; "
            "it comes from the phone."
        )
    status = f" (HTTP {error.status})" if error.status else ""
    return f"STMP call failed: {code}{status}\n{detail}\nNext: {step}"
