---
name: stmp
description: How to work with an STMP phone — an approval gate and a credential vault the agent cannot bypass. Use when a tool name starts with stmp_, when a call comes back "denied" or "caller_unverified", or before starting a run that will need several human approvals.
---

# Working with an STMP phone

The phone is the trust boundary. It holds the credentials (Google tokens, API keys,
SSH private keys) and it holds the human. This machine holds neither: there is no
token to find, and nothing here can approve its own action.

## Read the device before you plan

`stmp_help` costs one call and answers what this instance can actually do: app
version, contract version, every plugin and route, which routes are gated. The
plugin's own surface is fixed when it is generated; the phone in front of you may
be older or newer. When the answer names a contract version different from the
plugin's, say so instead of guessing what exists.

## Prove a human is there before a long run

`stmp_probe` only reaches the device's handler *after* somebody approved it. If it
fails, no person is at the phone: stop, and tell the user. Stacking up prompts
behind a locked phone produces a wall of denials, not progress.

## Every gated call waits for a person

A gated call holds an approval modal for 60 seconds. Two outcomes are normal, and
neither is a bug:

- `denied` — a human declined, or the screen was off or locked. Do not retry. Ask
  whether they want it, and whether the phone is unlocked.
- timeout — nobody answered in time. Do not retry either; a retry is a second
  prompt for a decision that already lapsed.

Two routes are exempt and run without a modal: `stmp_tts` and `stmp_audio`. Their
descriptions say so. Never present an exempt call as evidence that a human approved
anything.

## The vault, specifically

`stmp_secrets` never returns a value and has no argument that could ask for one.
`list` and `get` give names, docs links and the hosts each secret may reach;
`call` asks the phone to make an HTTP request with the secret attached, inside that
secret's own host allowlist.

- Never look for credentials on this machine. There are none, and searching is the
  wrong move.
- A secret name the instance does not hold comes back as `unknown_secret`: call
  `list`, then use a name that exists — or tell the user to store it on the phone.
- `host_not_allowed` means the URL's host is outside the secret's allowlist. The
  fix is on the phone; do not try to route around it.

## Failures are already translated

Every error result ends with a `Next:` line naming the resolving step. Follow it
rather than retrying the same call. The ones that need a person:

- `caller_unverified` — this machine's address has never been named on the phone.
  The first install hits this before anything works. Approve and name the caller
  in STMP.
- `caller_denied` — blocked on purpose. Stop.
- `secret_locked` / `vault_missing` — the human has to open STMP; you cannot.
- `ssh_host_key_unknown` — repeat the call with `trustHostKey` set to a fingerprint
  the *user* confirms. Never invent one.

## Unattended runs

Cron jobs, single-query sessions and other headless runs fail closed: the phone
will not approve on its own, and this plugin does not try to. If a scheduled task
needs a gated route, its failure is the correct result — report it and let a human
decide. Do not switch off approvals to make a job pass.

## Choosing a tool

One tool per plugin class; `action` picks the route. Short map:

| Need | Tool |
| --- | --- |
| Is anyone at the phone? | `stmp_probe` |
| What can this instance do? | `stmp_help` |
| Mail | `stmp_gmail` |
| Calendar | `stmp_calendar` |
| Files | `stmp_drive` |
| People | `stmp_contacts` |
| Notifications | `stmp_notifications` |
| Stored credentials | `stmp_secrets` |
| Commands on a server | `stmp_ssh` |
| Diagnose the bridge | `stmp_debug`, `stmp_logs` |
| Make a sound | `stmp_audio`, `stmp_tts` |

The tool result already includes what the phone answered; pass the facts on rather
than paraphrasing them into something the device did not say.
