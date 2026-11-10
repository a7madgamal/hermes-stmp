#!/usr/bin/env python3
"""Read STMP's pinned contract out of the app's own test, and write contract.json.

Source of truth is `HelpContractTest.kt`, not `GET /help`:

* CI in the STMP repo already fails when a route is added or removed without a
  `CONTRACT_VERSION` bump, so that file is the hand-checked, test-enforced truth.
* `GET /help` describes one running instance. A plugin's shipped surface must not
  depend on which secrets the author happened to store on their phone.

Usage
    python3 tools/sync_contract.py                 # fetch and rewrite contract.json
    python3 tools/sync_contract.py --check         # fail if the app's contract moved
    python3 tools/sync_contract.py --check-offline # validate committed JSON only
    python3 tools/sync_contract.py --file PATH     # parse a local copy (tests)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from actions import ACTIONS, routes_by_tool, tool_for_path  # noqa: E402

REPO = "a7madgamal/STMP.AI"
KT_PATH = "app/src/test/java/com/mido/phonebridge/HelpContractTest.kt"
DEFAULT_REF = "main"
OUT = Path(__file__).resolve().parent.parent / "contract.json"

VERSION_RE = re.compile(r'const val CONTRACT_VERSION\s*=\s*(\d+)')
ROUTE_RE = re.compile(r'"(GET|POST|PUT|PATCH|DELETE)\s+(/[^"]*)"')
PINNED_START_RE = re.compile(r'val PINNED_ROUTES:\s*Set<String>\s*=\s*setOf\(')
EXEMPT_RE = re.compile(r'setOf\(([^)]*)\)\s*,\s*\n\s*declaredExemptRoutes\(\)', re.S)


class ContractError(Exception):
    """The upstream file does not have the shape this parser relies on."""


def fetch(ref: str) -> tuple[str, str]:
    url = f"https://raw.githubusercontent.com/{REPO}/{ref}/{KT_PATH}"
    request = urllib.request.Request(url, headers={"User-Agent": "hermes-stmp-contract"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        raise ContractError(f"{url} answered HTTP {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise ContractError(f"could not fetch {url}: {exc}") from exc
    digest = hashlib.sha256(raw).hexdigest()
    try:
        return raw.decode("utf-8"), digest
    except UnicodeDecodeError as exc:
        raise ContractError(f"{url} is not UTF-8") from exc


def parse(text: str) -> tuple[int, list[str], list[str]]:
    """(contract_version, pinned_routes, exempt_routes) — all three or a loud error."""
    version_match = VERSION_RE.search(text)
    if not version_match:
        raise ContractError("CONTRACT_VERSION not found — the test file changed shape")

    start = PINNED_START_RE.search(text)
    if not start:
        raise ContractError("PINNED_ROUTES not found — the test file changed shape")
    tail = text[start.end():]
    end = tail.find("\n        )")
    if end == -1:
        raise ContractError("PINNED_ROUTES has no closing paren — cannot bound the set")
    pinned = ROUTE_RE.findall(tail[:end])
    pinned_routes = [f"{method} {path}" for method, path in pinned]
    if not pinned_routes:
        raise ContractError("PINNED_ROUTES parsed to nothing — the scan is broken, not the app")
    if len(set(pinned_routes)) != len(pinned_routes):
        raise ContractError("PINNED_ROUTES contains a duplicate")

    exempt_match = EXEMPT_RE.search(text)
    if not exempt_match:
        raise ContractError(
            "the gate-exemption assertion in HelpContractTest.kt was not found; "
            "exempt routes cannot be derived, so generation refuses to guess"
        )
    exempt_routes = [
        f"{method} {path}" for method, path in ROUTE_RE.findall(exempt_match.group(1))
    ]
    if not exempt_routes:
        raise ContractError("the exemption assertion parsed to nothing")

    return int(version_match.group(1)), sorted(pinned_routes), sorted(exempt_routes)


def build(version: int, pinned: list[str], exempt: list[str], *, ref: str, blob: str) -> dict:
    """Cross-check the authored actions against the parsed route set, then emit."""
    unknown_exempt = sorted(set(exempt) - set(pinned))
    if unknown_exempt:
        raise ContractError(
            f"exempt routes are not pinned routes: {unknown_exempt} — the assertion and the "
            "pinned set disagree upstream"
        )

    claimed = {route for tool in ACTIONS.values() for route in tool.values()}
    missed = sorted(set(pinned) - claimed)
    extra = sorted(claimed - set(pinned))
    if missed:
        raise ContractError(
            "the app pins routes with no action here: "
            + ", ".join(missed)
            + " — add them to tools/actions.py under the tool that matches their plugin class"
        )
    if extra:
        raise ContractError(
            "these actions name routes the app no longer pins: "
            + ", ".join(extra)
            + " — the action list drifted ahead of the app; remove or repoint them"
        )

    for tool, route_map in routes_by_tool().items():
        for route in route_map:
            expected = tool_for_path(route.split(" ", 1)[1])
            if expected != tool:
                raise ContractError(
                    f"{tool} claims {route!r}, but that path belongs to {expected!r}"
                )

    tools: dict[str, dict] = {}
    for tool in sorted(ACTIONS):
        actions = {}
        for action, route in sorted(ACTIONS[tool].items()):
            method, path = route.split(" ", 1)
            actions[action] = {
                "method": method,
                "path": path,
                "exempt": route in exempt,
            }
        tools[tool] = {"actions": actions}

    return {
        "contract_version": version,
        "source": {
            "repo": REPO,
            "path": KT_PATH,
            "ref": ref,
            "blob_sha256": blob,
        },
        "exempt": sorted(exempt),
        "route_count": len(pinned),
        "tools": tools,
    }


def dump(contract: dict) -> str:
    return json.dumps(contract, indent=2, sort_keys=True) + "\n"


def parse_local(path: Path) -> tuple[int, list[str], list[str], str]:
    raw = path.read_bytes()
    return (*parse(raw.decode("utf-8")), hashlib.sha256(raw).hexdigest())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if the contract moved")
    parser.add_argument("--check-offline", action="store_true", help="validate committed JSON only")
    parser.add_argument("--file", type=Path, help="parse a local HelpContractTest.kt")
    parser.add_argument("--ref", default=None, help=f"git ref to read (default {DEFAULT_REF})")
    args = parser.parse_args(argv)

    committed: dict | None = None
    if OUT.exists():
        committed = json.loads(OUT.read_text(encoding="utf-8"))
    ref = args.ref or (committed or {}).get("source", {}).get("ref", DEFAULT_REF)

    if args.check_offline:
        if committed is None:
            print("contract.json is missing", file=sys.stderr)
            return 1
        try:
            expected = build(
                committed["contract_version"],
                sorted(r for t in committed["tools"].values() for a in t["actions"].values()
                       for r in [f"{a['method']} {a['path']}"]),
                committed["exempt"],
                ref=ref,
                blob=committed["source"]["blob_sha256"],
            )
        except ContractError as exc:
            print(f"contract check failed: {exc}", file=sys.stderr)
            return 1
        if dump(expected) != dump(committed):
            print(
                "contract.json disagrees with tools/actions.py; run tools/generate.py "
                "and tools/sync_contract.py",
                file=sys.stderr,
            )
            return 1
        print(f"offline contract check OK: v{committed['contract_version']}, "
              f"{committed['route_count']} routes, {len(committed['exempt'])} exempt")
        return 0

    try:
        if args.file:
            version, pinned, exempt, blob = parse_local(args.file)
        else:
            text, blob = fetch(ref)
            version, pinned, exempt = parse(text)
        contract = build(version, pinned, exempt, ref=ref, blob=blob)
    except ContractError as exc:
        print(f"contract error: {exc}", file=sys.stderr)
        return 1

    if args.check:
        if committed is None:
            print("contract.json is missing; run tools/sync_contract.py", file=sys.stderr)
            return 1
        if dump(contract) == dump(committed):
            print(f"contract check OK: v{version}, {len(pinned)} routes, {len(exempt)} exempt")
            return 0
        # Distinguish a real surface change from a comment/whitespace edit.
        same_surface = (
            committed.get("contract_version") == contract["contract_version"]
            and sorted(
                f"{a['method']} {a['path']}"
                for t in committed["tools"].values()
                for a in t["actions"].values()
            )
            == sorted(pinned)
            and committed.get("exempt") == sorted(exempt)
        )
        if same_surface and committed["source"]["blob_sha256"] != blob:
            print(
                "upstream file changed but the parsed contract did not (comments or formatting). "
                "Run tools/sync_contract.py to refresh blob_sha256.",
                file=sys.stderr,
            )
            return 1
        print(
            "STMP's contract moved: regenerate and review.\n"
            f"  committed v{committed.get('contract_version')} -> upstream v{version}\n"
            "  1. python3 tools/sync_contract.py\n"
            "  2. python3 tools/generate.py\n"
            "  3. review the diff, then bump the plugin version if the surface changed",
            file=sys.stderr,
        )
        return 1

    OUT.write_text(dump(contract), encoding="utf-8")
    print(
        f"wrote {OUT.relative_to(OUT.parent.parent)}: v{contract['contract_version']}, "
        f"{contract['route_count']} routes, {len(contract['exempt'])} exempt, "
        f"blob {blob[:12]}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
