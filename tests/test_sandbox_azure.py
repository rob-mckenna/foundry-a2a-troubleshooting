"""Offline orchestration tests. Azure is mocked; one probe uses real loopback HTTP."""

import argparse
import contextlib
import copy
import io
import json
import tempfile
import threading
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import Mock, patch

import demo_local
import sandbox_azure as sandbox


SUBSCRIPTION = "11111111-2222-4333-8444-555555555555"
PRINCIPAL = "22222222-3333-4444-8555-666666666666"


def state():
    return sandbox.new_state(SUBSCRIPTION, "eastus2", "gpt-4.1-mini",
                             "2025-04-14", "GlobalStandard", 1)


def args():
    return argparse.Namespace(
        accept_cost=True, subscription=SUBSCRIPTION, location="eastus2",
        model="gpt-4.1-mini", model_version="2025-04-14", sku="GlobalStandard", capacity=1,
    )


def catalog():
    return [{"model": {
        "name": "gpt-4.1-mini", "version": "2025-04-14", "format": "OpenAI",
        "capabilities": {"responses": "true", "agentsV2": "true"},
        "lifecycleStatus": "Legacy",
        "skus": [
            {"name": "GlobalStandard", "usageName": "OpenAI.GlobalStandard.gpt4.1-mini-finetune"},
            {"name": "GlobalStandard", "usageName": "OpenAI.GlobalStandard.gpt4.1-mini",
             "capacity": {"minimum": None, "maximum": 1000, "step": None}},
        ],
    }}]


def tool_response():
    return {"status": "completed", "output": [
        {"type": "a2a_preview_call", "status": "completed", "id": "item-1",
         "call_id": "call-1", "name": "diagnostic"},
        {"type": "a2a_preview_call_output", "status": "completed", "id": "item-2",
         "call_id": "call-1", "name": "diagnostic", "output": "A2A diagnostic OK"},
    ]}


def preflight_values(model_catalog=None, quota=10):
    return [
        {"state": "Enabled", "user": {"type": "user"}},
        {"registrationState": "Registered"},
        catalog() if model_catalog is None else model_catalog,
        [{"name": {"value": "OpenAI.GlobalStandard.gpt4.1-mini"},
          "limit": quota, "currentValue": 0}],
    ]


class SandboxTests(unittest.TestCase):
    def test_cost_and_deletion_gates_before_any_azure_call(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(sandbox, "Azure") as azure:
            harness = sandbox.Sandbox(Path(folder) / "state.json", Path(folder) / "evidence.json")
            options = args()
            options.accept_cost = False
            for operation in (lambda: harness.create(options), lambda: harness.probe(False),
                              lambda: harness.cleanup(False)):
                with self.assertRaises(sandbox.SandboxError):
                    operation()
            azure.assert_not_called()
            self.assertFalse(harness.state_path.exists())

    def test_state_paths_must_differ_even_through_symlinks_or_hardlinks(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "state.json"
            with self.assertRaises(sandbox.SandboxError):
                sandbox.distinct_paths(path, path.parent / "." / path.name)

    def test_reject_invalid_deployment_inputs(self):
        for field, value in (("subscription", "not-a-uuid"), ("capacity", 11),
                             ("capacity", True), ("location", "../other"), ("sku", "ProvisionedManaged")):
            options = vars(args())
            options.pop("accept_cost")
            options["version"] = options.pop("model_version")
            options[field] = value
            with self.subTest(field=field), self.assertRaises(sandbox.SandboxError):
                sandbox.new_state(**options)

    def test_cleanup_rejects_edited_target_before_azure(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(sandbox, "Azure") as azure:
            path = Path(folder) / "state.json"
            value = state()
            value["resource_group"] = "important-production-group"
            sandbox.write_json(path, value)
            with self.assertRaises(sandbox.SandboxError):
                sandbox.Sandbox(path).cleanup(True)
            azure.assert_not_called()

    def test_cleanup_rejects_foreign_or_inconsistent_remote_group(self):
        for wrong in ("tags", "id"):
            with tempfile.TemporaryDirectory() as folder, patch.object(sandbox, "Azure") as factory:
                path = Path(folder) / "state.json"
                value = state()
                sandbox.write_json(path, value)
                remote = {"id": sandbox.ids(value)[0], "tags": sandbox.tags(value)}
                remote[wrong] = {} if wrong == "tags" else "/subscriptions/foreign"
                factory.return_value.arm.return_value = remote
                with self.assertRaises(sandbox.SandboxError):
                    sandbox.Sandbox(path).cleanup(True)
                self.assertEqual(factory.return_value.arm.call_count, 1)
                self.assertTrue(path.exists())

    def test_cleanup_keeps_state_until_deletion_is_confirmed(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(sandbox, "Azure") as factory:
            path = Path(folder) / "state.json"
            value = state()
            sandbox.write_json(path, value)
            group = {"id": sandbox.ids(value)[0], "tags": sandbox.tags(value)}
            factory.return_value.arm.side_effect = [group, {}, sandbox.SandboxError("http-non-2xx", 404)]
            sandbox.Sandbox(path).cleanup(True)
            self.assertEqual(sandbox.load_state(path)["phase"], "deleted")
            self.assertEqual(factory.return_value.arm.call_args_list[1].args[0], "DELETE")

    def test_cleanup_preserves_state_after_failed_delete(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(sandbox, "Azure") as factory:
            path = Path(folder) / "state.json"
            value = state()
            sandbox.write_json(path, value)
            group = {"id": sandbox.ids(value)[0], "tags": sandbox.tags(value)}
            factory.return_value.arm.side_effect = [group, sandbox.SandboxError("http-non-2xx", 403)]
            with self.assertRaises(sandbox.SandboxError):
                sandbox.Sandbox(path).cleanup(True)
            self.assertEqual(sandbox.load_state(path)["phase"], "deleting")

    def test_preflight_uses_inference_quota_not_finetune(self):
        with patch.object(sandbox, "cli", side_effect=preflight_values()):
            result = sandbox.model_preflight(Mock(), state())
        self.assertEqual(result["model_lifecycle"], "Legacy")

    def test_preflight_rejects_missing_model_quota_or_capability(self):
        no_responses = catalog()
        no_responses[0]["model"]["capabilities"]["responses"] = False
        no_sku = catalog()
        no_sku[0]["model"]["skus"] = []
        for values in (preflight_values([], 10), preflight_values(no_responses),
                       preflight_values(no_sku), preflight_values(quota=0),
                       [{"state": "Disabled"}],
                       [{"state": "Enabled"}, {"registrationState": "NotRegistered"}]):
            with self.subTest(values=values), patch.object(sandbox, "cli", side_effect=values):
                with self.assertRaises(sandbox.SandboxError):
                    sandbox.model_preflight(Mock(), state())

    def test_readiness_retries_reads_only_and_surfaces_permanent_errors(self):
        read = Mock(side_effect=[sandbox.SandboxError("http-non-2xx", 403), {"ready": True}])
        with patch.object(sandbox.time, "sleep"):
            self.assertTrue(sandbox.wait_read(read, lambda value: value["ready"])["ready"])
        with self.assertRaises(sandbox.SandboxError):
            sandbox.wait_read(Mock(side_effect=sandbox.SandboxError("http-non-2xx", 400)), bool)

    def test_readiness_times_out_without_false_success(self):
        with patch.object(sandbox.time, "sleep"), self.assertRaises(sandbox.SandboxError):
            sandbox.wait_read(lambda: {}, bool, attempts=2)

    def test_agent_to_agent_requires_completed_actual_tool_item(self):
        response = tool_response()
        self.assertTrue(sandbox.tool_summary(response)["success"])
        self.assertNotIn("REMOTE_SECRET", json.dumps(sandbox.tool_summary(response)))
        for change in (
            {"output": [{"type": "message", "content": "looks successful"}]},
            {"status": "incomplete"}, {"error": {"message": "REMOTE_SECRET"}},
            {"output": [{"type": "a2a_call", "status": "failed", "output": "secret"}]},
            {"output": [{"type": "a2a_call", "status": "completed", "output": ""}]},
        ):
            with self.subTest(change=change):
                self.assertFalse(sandbox.tool_summary({**response, **change})["success"])

    def test_tool_pairs_require_matching_ids_names_status_and_remote_reply(self):
        changes = [
            lambda value: value["output"][1].update(call_id="different"),
            lambda value: value["output"][1].update(name="different"),
            lambda value: value["output"][1].update(status="failed"),
            lambda value: value["output"][0].update(status="in_progress"),
            lambda value: value["output"][1].update(output="REMOTE_SECRET"),
            lambda value: value["output"][1].update(output='{"error":{"code":"failed"}}'),
            lambda value: value["output"][1].update(output={"text": "A2A diagnostic OK"}),
            lambda value: value["output"][0].update(call_id=""),
            lambda value: value["output"].append(copy.deepcopy(value["output"][0])),
            lambda value: value["output"].append(copy.deepcopy(value["output"][1])),
            lambda value: value["output"].pop(0),
            lambda value: value["output"].pop(1),
        ]
        for change in changes:
            value = tool_response()
            change(value)
            self.assertFalse(sandbox.tool_summary(value)["success"])
        self.assertTrue(sandbox.tool_summary(tool_response())["remote_diagnostic_reply_verified"])

    def test_cli_errors_do_not_echo_remote_credentials(self):
        with patch.object(sandbox.shutil, "which", return_value="az"), \
             patch.object(sandbox.subprocess, "run", return_value=argparse.Namespace(
                 returncode=1, stdout="PRIVATE_TOKEN", stderr="PRIVATE_ERROR",
             )):
            with self.assertRaises(sandbox.SandboxError) as error:
                sandbox.cli("account", "show")
            self.assertNotIn("PRIVATE", str(error.exception))

    def test_create_rejects_collision_without_adopting_group(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(sandbox, "Azure") as factory, \
             patch.object(sandbox, "model_preflight", return_value={}), \
             patch.object(sandbox, "cli", return_value={"azure-cli": "test"}), \
             patch.object(sandbox, "powershell_version", return_value="7.7.0"):
            harness = sandbox.Sandbox(Path(folder) / "state.json", Path(folder) / "evidence.json")
            factory.return_value.arm.return_value = {"id": "existing"}
            with self.assertRaises(sandbox.SandboxError):
                harness.create(args())
            self.assertFalse(harness.state_path.exists())
            self.assertEqual(factory.return_value.arm.call_count, 1)

    def test_partial_create_preserves_recovery_state(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(sandbox, "Azure") as factory, \
             patch.object(sandbox, "model_preflight", return_value={}), \
             patch.object(sandbox, "cli", return_value={"azure-cli": "test"}), \
             patch.object(sandbox, "bootstrap_identity", return_value=PRINCIPAL), \
             patch.object(sandbox, "powershell_version", return_value="7.7.0"):
            harness = sandbox.Sandbox(Path(folder) / "state.json", Path(folder) / "evidence.json")
            factory.return_value.arm.side_effect = [
                sandbox.SandboxError("http-non-2xx", 404), sandbox.SandboxError("http-non-2xx", 403),
            ]
            with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(sandbox.SandboxError):
                harness.create(args())
            self.assertEqual(sandbox.load_state(harness.state_path)["phase"], "creating-resource-group")

    def test_create_payloads_and_exact_instance_identity(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(sandbox, "Azure") as factory, \
             patch.object(sandbox, "model_preflight", return_value={}), \
             patch.object(sandbox, "cli", return_value={"azure-cli": "test"}), \
             patch.object(sandbox, "bootstrap_identity", return_value=PRINCIPAL), \
             patch.object(sandbox, "assign_role") as role, \
             patch.object(sandbox, "direct_probe", return_value={"Success": True}), \
             patch.object(sandbox, "powershell_version", return_value="7.7.0"), \
             patch.object(sandbox.time, "sleep"), patch.object(sandbox.Sandbox, "probe") as probe:
            harness = sandbox.Sandbox(Path(folder) / "state.json", Path(folder) / "evidence.json")
            azure = factory.return_value

            def arm(method, resource, body=None, api=sandbox.API):
                if method == "GET" and resource.endswith(harness.state["resource_group"]):
                    if not harness.state_path.exists():
                        raise sandbox.SandboxError("http-non-2xx", 404)
                    return {"id": resource, "tags": sandbox.tags(harness.state)}
                return {"properties": {"provisioningState": "Succeeded"},
                        "identity": {"principalId": PRINCIPAL}}

            azure.arm.side_effect = arm
            azure.request.return_value = {"version": "1", "instance_identity": {"principal_id": PRINCIPAL}}
            with contextlib.redirect_stdout(io.StringIO()):
                options = args()
                options.provision_only = True
                harness.create(options)
            probe.assert_not_called()
            self.assertEqual(harness.state["phase"], "ready")
            self.assertTrue(harness.evidence["provisioning_success"])
            self.assertEqual(harness.evidence["verification_status"], "not-run")
            self.assertFalse(harness.evidence["success"])
            puts = [call for call in azure.arm.call_args_list if call.args[0] == "PUT"]
            account = next(call.args[2] for call in puts if call.args[1] == sandbox.ids(harness.state)[1])
            self.assertTrue(account["properties"]["disableLocalAuth"])
            connection = next(call.args[2] for call in puts if "/connections/" in call.args[1])
            self.assertEqual(connection["properties"]["authType"], "AgenticIdentityToken")
            calls = [call for call in azure.request.call_args_list if call.args[0] == "POST"]
            tool = calls[-1].args[2]["definition"]["tools"][0]
            self.assertEqual(tool["type"], "a2a")
            self.assertNotIn("agent_card_path", tool)
            self.assertEqual(role.call_args.args[2], PRINCIPAL)
            self.assertEqual(role.call_args.args[3], sandbox.AGENT_CONSUMER)

    def test_no_project_identity_fallback_for_caller(self):
        read = Mock(return_value={"identity": {"principalId": PRINCIPAL}, "instance_identity": None})
        with patch.object(sandbox.time, "sleep"), self.assertRaises(sandbox.SandboxError):
            sandbox.wait_read(
                read, lambda value: bool(sandbox.object_value(value.get("instance_identity") or {}).get("principal_id")),
                attempts=2,
            )

    def test_direct_probe_uses_production_helpers_with_token_stdin(self):
        server = demo_local.FixtureServer()
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        azure = Mock()
        azure.token.return_value = demo_local.SYNTHETIC_TOKEN
        value = state()
        try:
            with patch.object(sandbox, "target_url", return_value=f"http://127.0.0.1:{server.server_port}/a2a"), \
                 patch.object(sandbox.subprocess, "run", wraps=sandbox.subprocess.run) as run:
                for send in (False, True):
                    result = sandbox.direct_probe(azure, value, send)
                    self.assertTrue(result["Success"])
                self.assertNotIn(demo_local.SYNTHETIC_TOKEN, str(run.call_args.args[0]))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def test_main_safe_error_and_nonzero_exit(self):
        with tempfile.TemporaryDirectory() as folder, contextlib.redirect_stderr(io.StringIO()) as error:
            self.assertEqual(sandbox.main([
                "cleanup", "--state-file", str(Path(folder) / "missing.json"),
            ]), 1)
            self.assertIn("delete-confirmation-required", error.getvalue())

    def test_existing_state_refusal_does_not_overwrite_evidence(self):
        with tempfile.TemporaryDirectory() as folder, contextlib.redirect_stderr(io.StringIO()):
            path = Path(folder) / "state.json"
            evidence = Path(folder) / "evidence.json"
            sandbox.write_json(path, state())
            evidence.write_text("KEEP_EXISTING_EVIDENCE", encoding="utf-8")
            options = args()
            result = sandbox.main([
                "create", "--accept-cost", "--state-file", str(path),
                "--evidence-file", str(evidence), "--subscription", options.subscription,
                "--location", options.location, "--model", options.model,
                "--model-version", options.model_version,
            ])
            self.assertEqual(result, 1)
            self.assertEqual(evidence.read_text(encoding="utf-8"), "KEEP_EXISTING_EVIDENCE")

    def test_agent_version_must_be_observed_not_assumed(self):
        self.assertEqual(sandbox.agent_version({"versions": {"latest": {"version": "2"}}}), "2")
        with self.assertRaises(sandbox.SandboxError):
            sandbox.agent_version({"id": "not-a-version"})

    def test_error_details_report_fixed_markers_never_remote_text(self):
        details = sandbox.safe_error_details(
            b'{"error":{"message":"REMOTE_SECRET token=PRIVATE_TOKEN dependency HTTP 429 quota exceeded"}}'
        )
        self.assertEqual(details["referenced_http_statuses"], [429])
        self.assertTrue(details["message_markers"]["throttling"])
        self.assertNotIn("REMOTE_SECRET", json.dumps(details))
        self.assertNotIn("PRIVATE_TOKEN", json.dumps(details))

    def test_probe_verifies_full_sequence_and_current_identity_type(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(sandbox, "Azure") as factory, \
             patch.object(sandbox, "powershell_version", return_value="7.7.0"), \
             patch.object(sandbox, "cli", side_effect=[
                 {"user": {"type": "servicePrincipal"}}, {"azure-cli": "2.92.0"},
             ]), patch.object(sandbox, "direct_probe", return_value={
                 "Success": True, "StatusCode": 200, "Response": {"Text": "REDACTED"},
             }) as direct:
            path = Path(folder) / "state.json"
            value = state()
            value.update(phase="ready", cli_identity_type="user")
            sandbox.write_json(path, value)
            azure = factory.return_value
            azure.arm.return_value = {"id": sandbox.ids(value)[0], "tags": sandbox.tags(value)}
            azure.request.side_effect = [
                sandbox.SandboxError("http-non-2xx", 401),
                tool_response(),
            ]
            harness = sandbox.Sandbox(path, Path(folder) / "evidence.json")
            with contextlib.redirect_stdout(io.StringIO()):
                result = harness.probe(True)
            self.assertTrue(result["success"])
            self.assertEqual(result["cli_identity_type"], "servicePrincipal")
            self.assertEqual(direct.call_count, 2)
            self.assertEqual(azure.request.call_count, 2)
            self.assertEqual(azure.request.call_args.args[2]["max_tool_calls"], 1)
            self.assertNotIn("REMOTE_SECRET", harness.evidence_path.read_text(encoding="utf-8"))

    def test_private_diagnostics_records_http_errors_without_raw_data(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(sandbox, "ROOT", Path(folder)):
            private = Path(folder) / "private-evidence"
            journal = sandbox.PrivateDiagnostics(private / "diagnostics.jsonl",
                                                  private / "state.json", private / "evidence.json")
            azure = sandbox.Azure(SUBSCRIPTION, journal)
            azure.token = Mock(return_value="TOKEN_SECRET")
            headers = {"x-ms-request-id": PRINCIPAL, "Set-Cookie": "COOKIE_SECRET",
                       "retry-after": "60", "x-ratelimit-reset-tokens": "SECRET"}
            raw = b'{"error":{"code":"tool_invocation_error","message":"BODY_SECRET","innererror":{"code":"DependencyFailure"}}}'
            azure.opener.open = Mock(side_effect=urllib.error.HTTPError(
                "https://example.test/PRIVATE_PATH", 424, "REASON_SECRET", headers, io.BytesIO(raw),
            ))
            with self.assertRaises(sandbox.SandboxError) as error:
                azure.request("POST", "https://example.test/PRIVATE_PATH", {"input": "PROMPT_SECRET"})
            self.assertEqual(error.exception.status, 424)
            event = json.loads(journal.path.read_text(encoding="utf-8"))
            self.assertEqual(event["body_metadata"]["error_codes"], ["DependencyFailure", "tool_invocation_error"])
            self.assertEqual(event["correlation_ids"]["x-ms-request-id"], PRINCIPAL)
            self.assertEqual(event["http_status"], 424)
            self.assertEqual(event["rate_limit_headers"], {"retry-after": "60"})
            text = journal.path.read_text(encoding="utf-8")
            for secret in ("TOKEN_SECRET", "COOKIE_SECRET", "BODY_SECRET", "PRIVATE_PATH", "PROMPT_SECRET"):
                self.assertNotIn(secret, text)
                self.assertNotIn(secret, str(error.exception))

    def test_private_diagnostics_success_invalid_json_and_transport(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(sandbox, "ROOT", Path(folder)):
            private = Path(folder) / "private-evidence"
            journal = sandbox.PrivateDiagnostics(private / "diagnostics.jsonl",
                                                  private / "state.json", private / "evidence.json")
            azure = sandbox.Azure(SUBSCRIPTION, journal)
            azure.token = Mock(return_value="TOKEN_SECRET")
            response = Mock(status=200, headers={"x-request-id": PRINCIPAL})
            response.read.return_value = b'{"output":[{"type":"message","status":"completed","content":"SECRET"}]}'
            manager = Mock()
            manager.__enter__ = Mock(return_value=response)
            manager.__exit__ = Mock(return_value=False)
            azure.opener.open = Mock(return_value=manager)
            self.assertIn("output", azure.request("POST", "https://example.test"))
            response.read.return_value = b"INVALID_SECRET"
            with self.assertRaises(sandbox.SandboxError):
                azure.request("GET", "https://example.test")
            azure.opener.open.side_effect = urllib.error.URLError("TRANSPORT_SECRET")
            with self.assertRaises(sandbox.SandboxError):
                azure.request("GET", "https://example.test")
            events = [json.loads(line) for line in journal.path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(events), 3)
            self.assertFalse(events[1]["body_metadata"]["json_valid"])
            self.assertTrue(events[2]["transport_failed"])
            self.assertNotIn("SECRET", journal.path.read_text(encoding="utf-8"))

    def test_private_diagnostics_rejects_public_and_colliding_paths(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(sandbox, "ROOT", Path(folder)):
            root = Path(folder)
            state_path = root / "private-evidence" / "state.json"
            evidence = root / "private-evidence" / "evidence.json"
            for path in (root / "evidence" / "public.jsonl", state_path, evidence):
                with self.assertRaises(sandbox.SandboxError):
                    sandbox.PrivateDiagnostics(path, state_path, evidence)

    def test_diagnostic_body_does_not_parse_arbitrary_payload_fields(self):
        raw = b'{"message":"SECRET","input":{"code":"SECRET"},"error":{"code":"Bearer SECRET"},"output":[{"type":"a2a_call","status":"failed","error":{"code":"a2a_failed"}}]}'
        result = sandbox.diagnostic_body(raw)
        self.assertEqual(result["error_codes"], ["a2a_failed"])
        self.assertNotIn("SECRET", json.dumps(result))

    def test_isolation_controls_are_independent_and_never_retried(self):
        text_response = {"status": "completed", "output": [
            {"type": "message", "role": "assistant",
             "content": [{"type": "output_text", "text": "PRIVATE_REPLY"}]},
        ]}
        with tempfile.TemporaryDirectory() as folder, patch.object(sandbox, "Azure") as factory, \
             patch.object(sandbox, "powershell_version", return_value="7.7.0"), \
             patch.object(sandbox, "cli", side_effect=[
                 {"azure-cli": "2.92.0"}, {"user": {"type": "user"}},
             ]), patch.object(sandbox, "direct_probe", return_value={"Success": True, "StatusCode": 200}) as direct:
            path = Path(folder) / "state.json"
            value = state()
            value["phase"] = "ready"
            sandbox.write_json(path, value)
            azure = factory.return_value
            azure.arm.return_value = {"id": sandbox.ids(value)[0], "tags": sandbox.tags(value)}
            azure.request.side_effect = [
                text_response, sandbox.SandboxError("http-non-2xx", 424),
                text_response, sandbox.SandboxError("http-non-2xx", 424),
            ]
            harness = sandbox.Sandbox(path, Path(folder) / "evidence.json")
            with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(sandbox.SandboxError):
                harness.diagnose(True, "all")
            self.assertEqual(azure.request.call_count, 4)
            self.assertEqual(direct.call_count, 1)
            self.assertEqual(len(harness.evidence["checks"]), 5)
            self.assertEqual([case["success"] for case in harness.evidence["checks"]],
                             [True, False, True, True, False])
            bodies = [call.args[2] for call in azure.request.call_args_list]
            self.assertIn("model", bodies[0])
            self.assertEqual(bodies[2]["tool_choice"], "none")
            self.assertEqual(bodies[2]["tools"], [])
            self.assertEqual(bodies[3]["tool_choice"], "required")
            self.assertNotIn("PRIVATE_REPLY", harness.evidence_path.read_text(encoding="utf-8"))

    def test_plain_responses_control_requires_text_and_rejects_tool_output(self):
        response = {"status": "completed", "output": [
            {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "ok"}]},
        ]}
        self.assertTrue(sandbox.responses_text_summary(response)["success"])
        for output in ([], [{"type": "a2a_call", "status": "completed"}],
                       [{"type": "message", "role": "user", "content": [{"type": "output_text", "text": "ok"}]}]):
            self.assertFalse(sandbox.responses_text_summary({**response, "output": output})["success"])


if __name__ == "__main__":
    unittest.main()
