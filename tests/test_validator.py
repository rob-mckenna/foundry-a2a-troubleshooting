"""Offline regression tests; no Azure resources or credentials are used."""

import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from a2a_validator import A2AValidator, EXAMPLE


ROOT = Path(__file__).resolve().parents[1]


class ValidatorTests(unittest.TestCase):
    def validate(self, **changes):
        config = dict(EXAMPLE)
        config.update(changes)
        validator = A2AValidator()
        with contextlib.redirect_stdout(io.StringIO()):
            result = validator.validate_full_configuration(config)
        return result, validator

    def test_automatic_discovery_needs_no_card_path(self):
        self.assertTrue(self.validate()[0])

    def test_direct_v1_card(self):
        self.assertTrue(self.validate(mode="direct_client", card_path="agentCard/v1.0")[0])

    def test_preview_is_explicit_and_warned(self):
        valid, validator = self.validate(
            mode="direct_client", card_path="agentCard/v0.3", protocol_version="0.3"
        )
        self.assertTrue(valid)
        self.assertTrue(any("preview" in warning for warning in validator.warnings))

    def test_suffixes_and_unsafe_urls_fail(self):
        base = str(EXAMPLE["server_url"])
        for url in (
            base + "/unexpected", base + "?a2a-version=1.0", base + "#fragment",
            base + "//", base.replace("https:", "http:"),
            base.replace("https://", "https://user:secret@"),
            base.replace(".com/", ".com:443/"),
            base.replace(".com/", ".com:bad/"),
            base.replace("/agents/", "/agents/../"),
            base.replace("example-agent", "example%2Fagent"),
            base.replace(".azure.com", ".azure.com.attacker.example"),
            base.replace("/api/", "/api /"), base.replace("/api/", "\\api\\"),
        ):
            with self.subTest(url=url):
                self.assertFalse(self.validate(server_url=url, tool_url=url)[0])

    def test_one_trailing_slash_is_not_a_platform_failure(self):
        valid, validator = self.validate(
            server_url=str(EXAMPLE["server_url"]) + "/"
        )
        self.assertTrue(valid)
        self.assertTrue(validator.warnings)

    def test_target_mismatches_fail(self):
        for old, new in (
            ("example.services", "different.services"),
            ("example-project", "different-project"),
            ("example-agent", "different-agent"),
        ):
            with self.subTest(component=old):
                self.assertFalse(self.validate(
                    tool_url=str(EXAMPLE["tool_url"]).replace(old, new)
                )[0])

    def test_card_target_and_path_mismatches_fail(self):
        for card in (
            "https://other.services.ai.azure.com/agentCard/v1.0",
            str(EXAMPLE["server_url"]).replace("example-agent", "other") + "/agentCard/v1.0",
            "/agentCard/v1.0", "../agentCard/v1.0", "card", "agentCard/v2.0",
            "agentCard/v1.0?secret=sentinel", "agentCard/v1.0#fragment",
        ):
            with self.subTest(card=card):
                self.assertFalse(self.validate(mode="direct_client", card_path=card)[0])

    def test_connection_custom_card_is_rejected(self):
        self.assertFalse(self.validate(card_path="agentCard/v1.0")[0])

    def test_missing_and_conflicting_version_fail(self):
        self.assertFalse(self.validate(protocol_version="")[0])
        self.assertFalse(self.validate(
            mode="direct_client", card_path="agentCard/v0.3"
        )[0])

    def test_auth_and_identity_conflicts_fail(self):
        for changes in (
            {"auth_type": "Entra"}, {"auth_type": "invalid"},
            {"auth_type": "ServicePrincipal"},
            {"identity_type": "Project Managed Identity"},
            {"audience": "https://management.azure.com"},
        ):
            with self.subTest(changes=changes):
                self.assertFalse(self.validate(**changes)[0])

    def test_direct_service_principal_and_preview_context(self):
        self.assertTrue(self.validate(
            mode="direct_client", card_path="agentCard/v1.0",
            auth_type="ServicePrincipal", identity_type="Service Principal",
        )[0])
        valid, validator = self.validate(auth_type="AgentOnBehalfOfUser")
        self.assertTrue(valid)
        self.assertTrue(any("AgentBlueprint" in warning for warning in validator.warnings))

    def test_invalid_field_types_and_empty_values_fail(self):
        for changes in (
            {"server_url": None}, {"card_path": []}, {"auth_type": 7},
            {"mode": ""}, {"tool_url": ""},
        ):
            with self.subTest(changes=changes):
                self.assertFalse(self.validate(**changes)[0])

    def test_state_is_reset_between_runs(self):
        validator = A2AValidator()
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertFalse(validator.validate_full_configuration({}))
            self.assertTrue(validator.validate_full_configuration(dict(EXAMPLE)))
        self.assertFalse(validator.errors)

    def test_untrusted_inputs_are_not_echoed(self):
        sentinel = "DO_NOT_PUBLISH_SENTINEL"
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            validator = A2AValidator()
            validator.validate_full_configuration(
                dict(EXAMPLE, server_url="https://user:" + sentinel + "@example.com",
                     card_path=sentinel, auth_type=sentinel)
            )
        self.assertNotIn(sentinel, output.getvalue())

    def test_cli_exit_codes_and_safe_read_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            for content, expected in (
                (json.dumps(EXAMPLE), 0), ("{}", 1), ("[]", 2), ("not-json", 2),
            ):
                path.write_text(content, encoding="utf-8")
                run = subprocess.run(
                    [sys.executable, str(ROOT / "a2a_validator.py"), "--config", str(path)],
                    capture_output=True, text=True, check=False,
                )
                self.assertEqual(run.returncode, expected, run.stdout + run.stderr)

    def test_no_arguments_does_not_validate_an_example(self):
        run = subprocess.run(
            [sys.executable, str(ROOT / "a2a_validator.py")],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(run.returncode, 2)
        self.assertNotIn("STATIC RESULT: PASS", run.stdout)


if __name__ == "__main__":
    unittest.main()
