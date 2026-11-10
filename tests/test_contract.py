"""The generated surface is the app's surface: same routes, same exemptions, same count."""

from __future__ import annotations

import json
import sys
import unittest

from support import ROOT

TOOLS_DIR = ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import sync_contract  # noqa: E402
from actions import ACTIONS  # noqa: E402

from stmp.dispatch import CONTRACT_VERSION, DISPATCH, EXEMPT  # noqa: E402

CONTRACT = json.loads((ROOT / "contract.json").read_text(encoding="utf-8"))

SYNTHETIC = '''
class HelpContractTest {
    private companion object {
        const val CONTRACT_VERSION = 9
        val PINNED_ROUTES: Set<String> = setOf(
            "DELETE /audit",
            "GET /debug",
            "GET /probe",
            "POST /tts",
        )
    }

    @Test
    fun `only the two sound routes skip the gate`() {
        assertEquals(
            setOf("POST /tts"),
            declaredExemptRoutes()
        )
    }
}
'''


class GeneratedTests(unittest.TestCase):
    def test_contract_version_matches_the_dispatch_table(self):
        self.assertEqual(CONTRACT["contract_version"], CONTRACT_VERSION)

    def test_route_count_matches_the_dispatch_table(self):
        self.assertEqual(
            CONTRACT["route_count"],
            sum(len(actions) for actions in DISPATCH.values()),
        )

    def test_every_contract_action_is_in_the_dispatch_table(self):
        for tool, payload in CONTRACT["tools"].items():
            for action, entry in payload["actions"].items():
                self.assertEqual(DISPATCH[tool][action], (entry["method"], entry["path"]))

    def test_exemptions_match_between_contract_and_dispatch(self):
        routes = {
            f"{entry['method']} {entry['path']}"
            for payload in CONTRACT["tools"].values()
            for entry in payload["actions"].values()
            if entry["exempt"]
        }
        self.assertEqual(routes, set(EXEMPT))

    def test_actions_are_claimed_by_the_right_tool(self):
        for tool, actions in ACTIONS.items():
            for route in actions.values():
                path = route.split(" ", 1)[1]
                self.assertEqual(sync_contract.tool_for_path(path), tool)


class ParserTests(unittest.TestCase):
    def test_parser_reads_version_routes_and_exemptions(self):
        version, pinned, exempt = sync_contract.parse(SYNTHETIC)
        self.assertEqual(version, 9)
        self.assertEqual(pinned, ["DELETE /audit", "GET /debug", "GET /probe", "POST /tts"])
        self.assertEqual(exempt, ["POST /tts"])

    def test_missing_version_is_a_loud_error(self):
        with self.assertRaises(sync_contract.ContractError):
            sync_contract.parse(SYNTHETIC.replace("CONTRACT_VERSION = 9", "CONTRACT_VERSION = nine"))

    def test_missing_exemption_assertion_is_a_loud_error(self):
        with self.assertRaises(sync_contract.ContractError) as caught:
            sync_contract.parse(SYNTHETIC.replace("declaredExemptRoutes()", "somethingElse()"))
        self.assertIn("exemption", str(caught.exception))

    def test_a_route_with_no_action_is_refused(self):
        pinned = ["GET /probe", "POST /tts", "GET /brand-new"]
        with self.assertRaises(sync_contract.ContractError) as caught:
            sync_contract.build(9, pinned, ["POST /tts"], ref="main", blob="x")
        self.assertIn("GET /brand-new", str(caught.exception))

    def test_an_action_for_a_route_the_app_dropped_is_refused(self):
        pinned = ["GET /probe", "POST /tts"]
        with self.assertRaises(sync_contract.ContractError) as caught:
            sync_contract.build(9, pinned, ["POST /tts"], ref="main", blob="x")
        self.assertIn("no longer pins", str(caught.exception))

    def test_an_exemption_that_is_not_pinned_is_refused(self):
        pinned = ["GET /probe", "POST /tts"]
        with self.assertRaises(sync_contract.ContractError) as caught:
            sync_contract.build(9, pinned, ["POST /tts", "POST /ghost"], ref="main", blob="x")
        self.assertIn("POST /ghost", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
