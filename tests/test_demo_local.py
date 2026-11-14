"""Local demo lifecycle, fixture request validation, and wrapper safety."""

import contextlib
import io
import json
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

import demo_local


ROOT = Path(__file__).resolve().parents[1]


class DemoLocalTests(unittest.TestCase):
    def test_fixture_requires_auth_and_version(self):
        server = demo_local.FixtureServer()
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        url = f"http://127.0.0.1:{server.server_port}/a2a/agentCard/v1.0"
        try:
            for headers, status in (
                ({}, 401),
                ({"Authorization": "Bearer " + demo_local.SYNTHETIC_TOKEN}, 400),
            ):
                request = urllib.request.Request(url, headers=headers)
                with self.assertRaises(urllib.error.HTTPError) as error:
                    urllib.request.urlopen(request, timeout=5)
                self.assertEqual(error.exception.code, status)
                error.exception.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def test_fixture_rejects_wrong_rpc_shape(self):
        server = demo_local.FixtureServer()
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        url = f"http://127.0.0.1:{server.server_port}/a2a"
        headers = {
            "Authorization": "Bearer " + demo_local.SYNTHETIC_TOKEN,
            "A2A-Version": "1.0", "Content-Type": "application/json",
        }
        try:
            for body in (b"not-json", b"[]", b"{}", b'{"method":"message/send"}'):
                request = urllib.request.Request(url, data=body, headers=headers)
                with self.assertRaises(urllib.error.HTTPError) as error:
                    urllib.request.urlopen(request, timeout=5)
                self.assertEqual(error.exception.code, 400)
                error.exception.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def test_lifecycle_closes_port_on_probe_failure(self):
        server = demo_local.FixtureServer()
        port = server.server_port
        with patch("demo_local.FixtureServer", return_value=server):
            with patch("demo_local.invoke_probe", side_effect=RuntimeError("synthetic")):
                with self.assertRaises(RuntimeError):
                    demo_local.run_scenario("unused", "success")
        with socket.socket() as connection:
            connection.settimeout(2)
            self.assertNotEqual(connection.connect_ex(("127.0.0.1", port)), 0)

    def test_mismatched_outcome_fails(self):
        with patch("demo_local.invoke_probe", return_value={
            "Success": True, "StatusCode": 200, "Category": None,
        }):
            with self.assertRaises(RuntimeError):
                demo_local.run_scenario("unused", "forbidden")

    def test_main_does_not_write_success_for_failed_demo(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "evidence.json"
            with patch("demo_local.shutil.which", return_value="unused"):
                with patch("demo_local.subprocess.run") as process:
                    process.return_value.stdout = "7.7.0"
                    with patch("demo_local.run_scenario", side_effect=RuntimeError("synthetic")):
                        with contextlib.redirect_stderr(io.StringIO()):
                            self.assertEqual(demo_local.main([
                                "--scenario", "success", "--evidence-file", str(path),
                            ]), 1)
            self.assertFalse(path.exists())

    def test_missing_powershell_is_explicit(self):
        with patch("demo_local.shutil.which", return_value=None):
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(demo_local.main(["--scenario", "success"]), 2)

    def test_demo_cli_success_and_sanitized_evidence(self):
        if not shutil.which("pwsh"):
            self.fail("Install PowerShell 7+ to verify the self-contained demo.")
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "evidence.json"
            process = subprocess.run(
                [sys.executable, str(ROOT / "demo_local.py"),
                 "--scenario", "success", "--evidence-file", str(path)],
                capture_output=True, text=True, timeout=60, check=False,
            )
            self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
            evidence = path.read_text(encoding="utf-8")
            self.assertNotIn(demo_local.SYNTHETIC_TOKEN, evidence)
            self.assertNotIn(demo_local.SENTINEL, evidence)
            self.assertEqual(json.loads(evidence)["scope"], "LOCAL_HTTP_FIXTURE_ONLY_NOT_AZURE")
            self.assertTrue(json.loads(evidence)["cases"][0]["expectation_verified"])

    def test_wrapper_cost_and_cleanup_gates_before_azure(self):
        pwsh = shutil.which("pwsh")
        if not pwsh:
            self.fail("Install PowerShell 7+ to verify wrapper gates.")
        for arguments in (["-Azure"], ["-Cleanup"], ["-Azure", "-AcceptCost"]):
            with self.subTest(arguments=arguments):
                process = subprocess.run(
                    [pwsh, "-NoProfile", "-File", str(ROOT / "demo.ps1")] + arguments,
                    capture_output=True, text=True, timeout=30, check=False,
                )
                self.assertEqual(process.returncode, 2, process.stdout + process.stderr)


if __name__ == "__main__":
    unittest.main()
