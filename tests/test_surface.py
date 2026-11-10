"""Declared = registered, and the schema cannot promise what the call refuses."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from support import ROOT

from stmp.dispatch import DISPATCH, EXEMPT
from stmp.handlers import SPECS
from stmp.schema import TOOL_DOCS, TOOL_SCHEMAS


def declared_tools() -> list[str]:
    """plugin.yaml's provides_tools, without pulling a YAML dependency into tests."""
    text = (ROOT / "plugin.yaml").read_text(encoding="utf-8")
    match = re.search(r"^provides_tools:\n((?:\s+-\s+\S+\n)+)", text, re.M)
    if not match:
        raise AssertionError("plugin.yaml has no provides_tools list")
    return re.findall(r"-\s+(\S+)", match.group(1))


class SurfaceTests(unittest.TestCase):
    def test_declared_tools_match_the_schemas(self):
        self.assertEqual(sorted(declared_tools()), sorted(TOOL_SCHEMAS))

    def test_declared_tools_match_the_dispatch_table(self):
        self.assertEqual(sorted(DISPATCH), sorted(TOOL_SCHEMAS))

    def test_every_action_has_a_route_and_a_spec(self):
        for tool, actions in DISPATCH.items():
            for action in actions:
                self.assertIn(
                    (tool, action), SPECS,
                    f"{tool}.{action} has a route but no argument spec",
                )

    def test_no_spec_without_a_route(self):
        for tool, action in SPECS:
            self.assertIn(action, DISPATCH.get(tool, {}),
                          f"{tool}.{action} has a spec but no route")

    def test_schema_properties_are_exactly_what_the_action_accepts(self):
        for tool, schema in TOOL_SCHEMAS.items():
            offered = set(schema["parameters"]["properties"])
            accepted = {"action"} | {
                arg for (owner, _), spec in SPECS.items() if owner == tool
                for arg in spec.args()
            }
            self.assertEqual(offered, accepted, f"{tool} shows a different argument set")

    def test_required_arguments_exist_as_properties(self):
        for (tool, action), spec in SPECS.items():
            props = TOOL_SCHEMAS[tool]["parameters"]["properties"]
            for required in spec.required:
                self.assertIn(required, props, f"{tool}.{action} requires {required} but hides it")

    def test_every_action_appears_in_its_tool_description(self):
        for tool, actions in DISPATCH.items():
            described = TOOL_SCHEMAS[tool]["parameters"]["properties"]["action"]["description"]
            for action in actions:
                self.assertIn(action, described.casefold(), f"{tool} never mentions {action}")


class DisclosureTests(unittest.TestCase):
    def test_the_two_exempt_routes_are_disclosed(self):
        exempt_tools = {
            tool for tool, actions in DISPATCH.items()
            if any(f"{method} {path}" in EXEMPT for method, path in actions.values())
        }
        self.assertEqual(exempt_tools, {"stmp_audio", "stmp_tts"})
        for tool in exempt_tools:
            self.assertIn("GATE-EXEMPT", TOOL_DOCS[tool])
        others = set(TOOL_DOCS) - exempt_tools
        for tool in others:
            self.assertNotIn("GATE-EXEMPT", TOOL_DOCS[tool],
                             f"{tool} claims an exemption it does not have")

    def test_no_tool_documentation_names_the_authors_instance(self):
        private_net = re.compile(
            r"\b(?:10\.\d{1,3}\.\d{1,3}\.\d{1,3}"
            r"|192\.168\.\d{1,3}\.\d{1,3}"
            r"|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}"
            r"|100\.(?:6[4-9]|[7-9]\d|1[01]\d|12[0-7])\.\d{1,3}\.\d{1,3})\b"
        )
        for text in list(TOOL_DOCS.values()) + [s["description"] for s in TOOL_SCHEMAS.values()]:
            self.assertIsNone(private_net.search(text), "a private address leaked into a description")
            self.assertNotIn("tailscale", text.lower())

    def test_no_setting_the_phone_cannot_honour(self):
        text = (ROOT / "plugin.yaml").read_text(encoding="utf-8")
        # Caller identity is a device-side decision keyed by address; a "caller_name"
        # setting would be a promise the bridge never reads.
        self.assertNotIn("caller_name", text)


class DefaultsTests(unittest.TestCase):
    def test_the_timeout_setting_exceeds_the_approval_window(self):
        text = (ROOT / "plugin.yaml").read_text(encoding="utf-8")
        match = re.search(r"timeout_seconds:\s*\n\s+type:\s*int\s*\n\s+default:\s*(\d+)", text)
        self.assertIsNotNone(match, "plugin.yaml lost its timeout default")
        self.assertGreater(int(match.group(1)), 60)


if __name__ == "__main__":
    unittest.main()
