# STMP — a phone as the trust boundary

**Hermes gets your Gmail, your vault and your SSH — and never holds a credential.
Every gated action waits for a hand on a phone.**

This plugin turns [STMP](https://github.com/a7madgamal/STMP.AI) into Hermes's hands
and eyes on a real Android phone. The interesting part is not the tool count. It is
where the secrets are: the Google tokens, the API keys and the SSH private keys live
in the phone's Keystore-wrapped vault, and this plugin has no configuration field
that could carry one.

```yaml
requires_env: []     # there is no credential on this machine to declare
```

Every gated route waits for a person: a full-screen modal on the phone, 60 seconds,
naming what is about to happen. An agent that has been prompt-injected, or a host
that has been compromised, can still only ask a human — it cannot approve itself.

## What it is, and what it is not

It **is** a host-side plugin: thirteen tools, one per plugin class the STMP app
exposes, whose routes are generated from the app's own contract test.

It **is not** a fork, a rewrite, or a companion app. Nothing in STMP changes to make
this work, and the same plugin works against any STMP instance.

## Install

1. Install the STMP app on the Android phone.

   Download the APK from the [releases page](https://github.com/a7madgamal/STMP.AI/releases).
   The asset is named `stmp-v<version>.apk` (about 43 MB). Open it on the phone and allow
   your browser or file manager to install unknown apps when Android asks.

   Four things about that download, because each one is a wasted trip otherwise:

   - **Use the releases list, not "latest".** Every release is published as a pre-release,
     so `github.com/a7madgamal/STMP.AI/releases/latest` returns 404. Pick the newest entry
     from the list and download the APK attached to it.
   - **Android 8.0 or newer, real phone only.** The APK is `arm64-v8a` only, so it will not
     install on an x86_64 emulator. Every phone this targets is arm64.
   - **Install over an existing STMP; do not uninstall first.** All releases are signed with
     the same key, so an upgrade installs cleanly and keeps your rules, caller names and
     account. A different signing key is a different app identity, which is why the key is
     pinned in CI.
   - **If you do uninstall, do not tick "keep app data".** Android deletes the app's
     Keystore key on uninstall while that checkbox keeps the rest, which leaves a vault that
     can never be opened; the app will then offer to reset it. Your secrets are gone either
     way — the kept data only buys you a vault you cannot unlock.

   The app updates itself from this page (Preferences → About & updates). Note that a
   pre-release is the app's **beta channel**, so the default **stable** channel sees nothing
   until a release is promoted — check the channel setting before reporting "no update".
2. In the app: start the bridge, sign in to Google if you want the Google routes, and
   note the bridge address it shows — the phone's Tailscale address or its LAN address.
   **Prefer the tailnet address, and prefer https if your copy serves it:** this bridge
   carries mail, Drive files and SSH output, and a plain-`http` LAN address sends all of
   that readable to anything on the same network.
3. Install this plugin from the Hermes catalog and point it at that address:

   ```bash
   hermes plugins search stmp                              # confirm the entry and its pin
   hermes plugins install stmp --enable --yes-deps
   hermes config set plugins.entries.stmp.settings.base_url http://100.x.y.z:8787
   ```

   `stmp` is a curated catalog entry (`plugin-catalog/stmp.yaml` in
   `NousResearch/hermes-agent`), so the name alone resolves and the install checks out
   one exact commit. `owner/repo` still works, but only the catalog form can be moved
   forward by `hermes plugins update`, and only the catalog form was reviewed.
   `--yes-deps` answers the dependency prompt, so the command finishes in one run over
   SSH or in CI.

   Updates arrive when the catalog pin moves — a new PR against `hermes-agent`, after
   which `hermes plugins update stmp` fetches it. Pushing to this repository alone does
   not reach catalog users: the pin, not the branch, is what they install.

4. Call `stmp_help`. The first call from a new machine is refused with
   `caller_unverified`: approve and name that caller on the phone, then retry. This
   is the app's identity gate, not a bug — an unnamed address gets no route at all.

## Tools

One tool per plugin class; `action` selects the route. All thirteen are registered
unconditionally, so what the manifest declares is exactly what runs.

| Tool | Actions |
| --- | --- |
| `stmp_probe` | `reach` |
| `stmp_help` | `contract` |
| `stmp_debug` | `report`, `audit_clear` |
| `stmp_logs` | `read` |
| `stmp_gmail` | `profile`, `list`, `read`, `modify`, `trash`, `send` |
| `stmp_calendar` | `list`, `create`, `update`, `delete`, `move`, `quickadd` |
| `stmp_drive` | `list`, `get`, `download`, `create_folder`, `rename`, `move`, `trash`, `upload` |
| `stmp_contacts` | `search` |
| `stmp_notifications` | `list`, `act`, `dismiss` |
| `stmp_secrets` | `list`, `get`, `call` |
| `stmp_ssh` | `run`, `detach`, `job` |
| `stmp_audio` | `cue` |
| `stmp_tts` | `speak` |

Deliberately excluded: the app's `google` plugin (zero routes) and one tool per
stored secret. A secret's *name* is the user's own data; publishing one tool per
secret would publish the vault into a public manifest. `stmp_secrets` reads the
names at runtime instead.

### `stmp_probe`: is a human actually reachable?

The probe's handler runs **only after** someone approved the request. Before a
multi-step run that will need several approvals, call it: if it fails, nobody is at
the phone, and the run should stop instead of stacking prompts behind a locked
screen.

### The vault never crosses the wire

`stmp_secrets` returns names, documentation links and each secret's allowed hosts.
There is no argument that asks for a value. `call` asks the phone to make an HTTP
request with the secret attached, inside that secret's own host allowlist; the
response comes back, the credential does not.

### Two routes are gate-exempt, and say so

`POST /tts` and `POST /audio/{cue}` run with no modal: one plays one of three fixed
cues, the other speaks the string it was given. That is the app's deliberate design
(a route whose job is to reach someone who is not looking cannot require them to
look), and both tool descriptions state it. Nothing else skips the gate.

`GET /help` is **not** exempt. It is a gated route whose *default rule* downgrades it
to a 5-second NOTIFY card; depending on the user's policy it may resolve without a
tap, and it can still be denied. Treat it as gated.

## Failures carry their next step

Every error result ends with the action that resolves it, because a status code
teaches nobody anything:

| Answer | What the tool tells the model |
| --- | --- |
| `403 caller_unverified` | approve and name this machine on the phone, then retry |
| `403 caller_denied` | blocked on the phone; do not retry |
| `403 denied` | nobody approved it, or the screen was locked; do not retry |
| `408` / timeout | the approval window expired; do not retry |
| `401 auth_expired` | sign in to Google again on the phone |
| `unknown_secret` | call `list` to see the names this instance actually holds |
| connection refused | the phone is unreachable at the configured `base_url` |

No call is ever retried automatically. A retry after a decline is a second prompt
for a decision a human already made.

## Unattended runs fail closed

Cron jobs, single-query sessions and other headless runs hit the phone's gate with
nobody to answer. The plugin's timeout (75 s, longer than the 60 s modal) makes that
a clean failure the agent can report, not a hang. Nothing here switches approvals
off to make a scheduled job pass.

## The surface is generated from the app, not from the wire

`tools/sync_contract.py` parses `HelpContractTest.kt` in the STMP repo — the file
whose CI fails when a route is added or removed without a contract bump. It reads
`CONTRACT_VERSION`, the pinned route set and the two exempt routes, then
cross-checks the authored action list: a route with no action, an action naming a
dropped route, or an action filed under the wrong plugin class all fail loudly.

`contract.json` and `stmp/dispatch.py` are committed, so the shipped surface is
auditable at the pinned commit, and CI regenerates both to prove they are current.

`GET /help` is used at runtime only to say what the *connected* instance supports
(older/newer contract, plugins switched off) — never to decide which tools exist.

## Development

```bash
python3 tools/sync_contract.py          # refresh contract.json from the app
python3 tools/generate.py               # rewrite stmp/dispatch.py
python3 tools/generate.py --check       # CI: the generated file is current
python3 tools/sync_contract.py --check  # CI: the app's contract has not moved
PYTHONPATH=.:tests python3 -m unittest discover -s tests -t tests
hermes plugins doctor . --ci
hermes plugins validate . --install-deps
```

The tests run offline against a stub bridge: no phone, no network, no credentials.

## Disclosure

What a user should know before installing, in full:

- **Network.** The plugin talks to exactly one address: the `base_url` you configure.
  There is no other endpoint, no telemetry, no update check.
- **Reads.** It reads a local file only for `stmp_drive.upload`, and only from
  `upload_dir` when that is set. With no `upload_dir`, credential stores are refused
  (`~/.ssh`, `~/.gnupg`, `~/.aws`, `~/.config`, `~/.kube`, `~/.docker`), along with
  any `.env*` file and Hermes's own home.
- **Writes.** A download writes only inside `download_dir` (default: this plugin's
  data folder), never over an existing file unless `allow_overwrite` is on, and only
  after the phone approved the read. Everything else that changes state is a gated
  route: mail, calendar, Drive, notifications, SSH commands. The phone decides
  whether to ask, and the human decides whether to allow.
- **Credentials.** None. Not a token, not a key, not a cookie. `requires_env` is
  empty and there is no `oauth:` block, because the credentials this plugin uses
  live on the phone and are never readable from here.
- **Data at rest.** The plugin stores one thing: what the connected instance
  reported (contract version, plugin and route counts, SSH connection names) in
  Hermes's own plugin state, rewritten only when that changes. No message content,
  no file content, no secret metadata beyond names and hosts.
- **Exemptions.** Two routes, named above and in their tool descriptions.
- **Limits.** Android device required; the phone must be reachable from the host
  (LAN or tailnet, no cloud relay). The Google routes need a Google account signed
  in on the phone. Contacts need `READ_CONTACTS`; notifications need the listener
  enabled. A user's own gate policy decides how much friction each route carries.

## License

MIT. See [LICENSE](LICENSE).
