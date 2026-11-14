"""Real HTTP exchange with a local fixture, not Azure/Entra verification."""

import json
import os
import platform
import shutil
import subprocess
import sys
import threading
import unittest
from datetime import datetime, timezone
from pathlib import Path
from demo_local import FixtureServer, SENTINEL, SYNTHETIC_TOKEN


ROOT = Path(__file__).resolve().parents[1]
class ExchangeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pwsh = shutil.which("pwsh")
        if not cls.pwsh:
            raise unittest.SkipTest("PowerShell 7+ is required for HTTP integration tests.")
        cls.server = FixtureServer()
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.evidence = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "scope": "LOCAL_HTTP_FIXTURE_ONLY_NOT_AZURE",
            "identity_context": "Synthetic bearer value; no Entra token or real principal",
            "azure_verification": "NOT_RUN_NO_TARGET_PROVIDED",
            "versions": {
                "python": platform.python_version(),
                "os": platform.system(),
                "powershell": subprocess.check_output(
                    [cls.pwsh, "-NoProfile", "-Command", "$PSVersionTable.PSVersion.ToString()"],
                    text=True, timeout=30,
                ).strip(),
                "a2a_protocol": "1.0",
                "sdk": "None; standard-library HTTP fixture and PowerShell REST client",
                "agent_deployment": "Synthetic fixture; no Azure agent deployment",
                "azure_cli": "Not used by this local fixture",
            },
            "cases": [],
        }

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)
        evidence_path = os.environ.get("A2A_EVIDENCE_PATH")
        if evidence_path:
            expected_cases = {
                "v1_card_discovery", "v1_message_exchange",
                "jsonrpc_error_at_http_200", "redirect_not_followed",
            }
            expected_cases.update(
                "task_state_" + state for state in (
                    "completed", "failed", "canceled", "rejected",
                    "input_required", "auth_required", "working",
                )
            )
            expected_cases.update(
                prefix + str(status)
                for prefix in ("http_", "card_http_")
                for status in (401, 403, 404, 405, 429, 500)
            )
            recorded_cases = {case["case"] for case in cls.evidence["cases"]}
            if recorded_cases != expected_cases or "exchange" not in cls.evidence:
                print(
                    "ERROR: evidence was not updated; HTTP verification is incomplete.",
                    file=sys.stderr,
                )
                return
            path = Path(evidence_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(cls.evidence, indent=2) + "\n", encoding="utf-8")

    def setUp(self):
        self.server.requests = []
        self.server.failure_status = None
        self.server.rpc_failure = False
        self.server.task_state = None

    def call(self, function):
        script = str(ROOT / "a2a_diagnostic.ps1").replace("'", "''")
        url = f"http://127.0.0.1:{self.server.server_port}/a2a"
        command = (
            f". '{script}'; "
            f"$result = {function} -Url '{url}' -Token '{SYNTHETIC_TOKEN}'; "
            "$result | ConvertTo-Json -Depth 20 -Compress"
        )
        run = subprocess.run(
            [self.pwsh, "-NoProfile", "-Command", command],
            capture_output=True, text=True, check=False, timeout=40,
        )
        self.assertEqual(run.returncode, 0, "Diagnostic function invocation failed")
        self.assertNotIn(SENTINEL, run.stdout + run.stderr)
        self.assertNotIn(SYNTHETIC_TOKEN, run.stdout + run.stderr)
        return json.loads(run.stdout)

    def record(self, case, result):
        self.assertIn("Success", result)
        self.assertIn("StatusCode", result)
        self.assertIn("Category", result)
        self.evidence["cases"].append({
            "case": case,
            "http_status": result.get("StatusCode"),
            "outcome": "PASS" if result["Success"] else "FAIL",
            "assertion_status": "PASS",
            "category": result.get("Category"),
            "authentication": "Synthetic header present; credential value omitted",
            "raw_remote_output": "OMITTED",
        })

    def test_v1_discovery_and_message_over_http(self):
        card = self.call("Test-EndpointAccessibility")
        self.assertTrue(card["Success"], card)
        self.assertEqual(card["StatusCode"], 200)
        reply = self.call("Test-A2AMessageExchange")
        self.assertTrue(reply["Success"], reply)
        self.assertEqual(reply["StatusCode"], 200)
        self.assertEqual(len(self.server.requests), 2)
        get, post = self.server.requests
        self.assertEqual(get["operation"], "GET")
        self.assertEqual(post["operation"], "POST")
        for request in (get, post):
            self.assertEqual(request["version"], "1.0")
            self.assertTrue(request["synthetic_auth_matches"])
        body = post["body"]
        self.assertEqual(body["jsonrpc"], "2.0")
        self.assertEqual(body["method"], "SendMessage")
        self.assertTrue(body["id"])
        self.assertTrue(body["params"]["message"]["messageId"])
        self.assertEqual(body["params"]["message"]["role"], "ROLE_USER")
        self.assertEqual(body["params"]["message"]["parts"], [
            {"text": "Reply with exactly: A2A diagnostic OK"},
        ])
        self.assertFalse(body["params"]["configuration"]["returnImmediately"])
        self.record("v1_card_discovery", card)
        self.record("v1_message_exchange", reply)
        self.evidence["exchange"] = {
            "transport": "JSON-RPC over loopback HTTP",
            "discovery_path": "/a2a/agentCard/v1.0",
            "version_header": "A2A-Version: 1.0",
            "request": {
                "jsonrpc": "2.0", "method": "SendMessage", "id": "[generated]",
                "params": {
                    "message": {
                        "messageId": "[generated]", "role": "ROLE_USER",
                        "parts": [{"text": "Reply with exactly: A2A diagnostic OK"}],
                    },
                    "configuration": body["params"]["configuration"],
                },
            },
            "fixture_response": {
                "jsonrpc": "2.0", "id": "[matched request]",
                "result": {"message": {
                    "messageId": "[synthetic]", "role": "ROLE_AGENT",
                    "parts": [{"text": "A2A diagnostic OK"}],
                }},
            },
            "note": "Reply is fixture-authored public text, not a real agent response.",
        }

    def test_http_failures_never_pass(self):
        for status in (401, 403, 404, 405, 429, 500):
            with self.subTest(status=status):
                self.server.failure_status = status
                card = self.call("Test-EndpointAccessibility")
                self.assertFalse(card["Success"], card)
                self.assertEqual(card["StatusCode"], status)
                self.record("card_http_" + str(status), card)
                result = self.call("Test-A2AMessageExchange")
                self.assertFalse(result["Success"], result)
                self.assertEqual(result["StatusCode"], status)
                self.record("http_" + str(status), result)

    def test_redirect_is_not_followed(self):
        self.server.failure_status = 302
        result = self.call("Test-A2AMessageExchange")
        self.assertFalse(result["Success"], result)
        self.assertEqual(result["StatusCode"], 302)
        self.assertEqual(len(self.server.requests), 1, "Credential-bearing redirect followed")
        self.record("redirect_not_followed", result)

    def test_rpc_error_with_http_200_fails_and_is_sanitized(self):
        self.server.rpc_failure = True
        result = self.call("Test-A2AMessageExchange")
        self.assertFalse(result["Success"], result)
        self.assertEqual(result["StatusCode"], 200)
        self.record("jsonrpc_error_at_http_200", result)

    def test_completed_and_interrupted_task_states(self):
        for state in (
            "TASK_STATE_COMPLETED", "TASK_STATE_FAILED", "TASK_STATE_CANCELED",
            "TASK_STATE_REJECTED", "TASK_STATE_INPUT_REQUIRED", "TASK_STATE_AUTH_REQUIRED",
            "TASK_STATE_WORKING",
        ):
            with self.subTest(state=state):
                self.server.task_state = state
                result = self.call("Test-A2AMessageExchange")
                self.assertEqual(
                    bool(result["Success"]),
                    state == "TASK_STATE_COMPLETED", result,
                )
                self.record(state.lower(), result)


if __name__ == "__main__":
    unittest.main()
