# Trust model

What this plugin can do to you, what it cannot, and where the line is enforced.

## The boundary

```
   ┌─────────────────────────── host ───────────────────────────┐
   │  Hermes agent ──► this plugin ──► HTTP/JSON ──►            │
   │  (no token, no key, no cookie, no vault)                   │
   └────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
   ┌──────────────────────────── phone ─────────────────────────┐
   │  identity gate (named callers only)                        │
   │  approval gate (a human, 60 s, full-screen, per route)     │
   │  vault (Keystore-wrapped; values never returned)           │
   │  Google OAuth tokens · API keys · SSH private keys         │
   └────────────────────────────────────────────────────────────┘
```

Three different things are private here, and each is enforced on the phone, not
here:

1. **Credentials.** The host never receives one. There is no route that returns a
   secret value, and this plugin declares no environment variables or OAuth clients
   to hold one.
2. **The decision.** Any gated call needs a human on the device. A compromised host,
   a prompt-injected model, or a runaway cron job can produce a request; it cannot
   produce an approval.
3. **The record.** The phone keeps the audit log of what was asked and what was
   decided (`GET /debug`, `DELETE /audit`).

## What a compromised host can still do

Honesty matters more than a clean diagram. If this machine is fully compromised:

- It can read every value this plugin has: `base_url`, and the recorded capability
  snapshot. That is all it has.
- It can call every route, including gated ones. Each gated call becomes a prompt a
  human sees and can refuse. It cannot make that prompt go away, answer it, or
  replay an old approval.
- It can use a stored secret *through the phone's broker*, but only against hosts on
  that secret's allowlist. It cannot read the secret to use it anywhere else.
- It can issue SSH commands through a key stored on the phone; each command is a
  card showing the command, and the key is not exportable.

## What the phone's policy decides (not this plugin)

The STMP app lets the owner classify each `plugin × verb` pair as `SECURE`
(full-screen modal), `NOTIFY` (a small card where silence approves) or
`DONT_DISTURB`. That choice belongs to the person holding the phone, and this plugin
neither reads nor changes it. Two consequences:

- A route that this README calls "gated" may be configured by its owner to resolve
  without a tap. The plugin still sends it through the gate; the device decides what
  the gate looks like.
- The only routes that are exempt *by design*, for everyone, are `POST /tts` and
  `POST /audio/{cue}`. Both are named in their tool descriptions.

## Failure is a result, not a retry

The plugin sends one request and reports what came back. It does not retry:

- a decline is a decision, and re-asking is harassment;
- a timeout means nobody was there, and re-asking asks the same absent person;
- a network error may be a phone that is off, which retrying cannot fix.

The timeout (75 s by default) is deliberately longer than the 60 s approval window:
a call that waits for a human must fail as "they did not answer", not as
"unreachable".

## No ambient authority

- No `check_fn` hides a tool: all thirteen are registered and declared.
- No core rebinds: the plugin only calls `ctx.register_tool` and `ctx.register_skill`.
- No subprocess, no `eval`, no shell. HTTP and JSON from the Python standard library.
- No self-update: the version installed is the commit pinned in the catalog.
- No writes outside the paths a user names in a call, and no reads except a file the
  user names for upload.

## Judging this model yourself

The claims above are testable without a phone:

```bash
python3 tools/sync_contract.py --check-offline   # surface matches contract.json
python3 tools/generate.py --check                # generated table is current
PYTHONPATH=.:tests python3 -m unittest discover -s tests -t tests
```

The tests drive the real handlers against a stub bridge, so the error translations,
argument refusals and streaming behaviour are proven offline.
