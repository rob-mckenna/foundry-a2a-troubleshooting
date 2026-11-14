"""Run a bounded local A2A demonstration without Azure resources or credentials."""

import argparse
import json
import platform
import shutil
import subprocess
import sys
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Dict, List, Optional


ROOT = Path(__file__).resolve().parent
SYNTHETIC_TOKEN = "SYNTHETIC_TOKEN_NOT_AN_ENTRA_CREDENTIAL"
SENTINEL = "DO_NOT_PUBLISH_REMOTE_SECRET"
SCENARIOS = (
    "success", "unauthorized", "forbidden", "not-found", "wrong-method",
    "throttled", "server-error", "redirect", "malformed-json", "rpc-error",
    "failed-task",
)
HTTP_SCENARIOS = {
    "unauthorized": 401, "forbidden": 403, "not-found": 404,
    "wrong-method": 405, "throttled": 429, "server-error": 500, "redirect": 302,
}


class FixtureHandler(BaseHTTPRequestHandler):
    """Synthetic loopback fixture; never a substitute for Entra/Foundry validation."""

    protocol_version = "HTTP/1.1"
    server: "FixtureServer"

    def log_message(self, format: str, *args: object) -> None:
        # Request logs are intentionally disabled; headers and paths may be sensitive.
        pass

    def send_json(self, status: int, value: object) -> None:
        content = json.dumps(value).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(content)))
        if 300 <= status < 400:
            self.send_header("Location", "/must-not-follow")
        self.end_headers()
        self.wfile.write(content)

    def capture(self, body: Optional[Dict[str, object]] = None) -> None:
        self.server.requests.append({
            "operation": self.command,
            "path": self.path,
            "version": self.headers.get("A2A-Version"),
            "synthetic_auth_matches": (
                self.headers.get("Authorization") == "Bearer " + SYNTHETIC_TOKEN
            ),
            "body": body,
        })

    def authorize(self) -> bool:
        if self.headers.get("Authorization") != "Bearer " + SYNTHETIC_TOKEN:
            self.send_json(401, {"error": "Synthetic authorization failed"})
            return False
        if self.headers.get("A2A-Version") != "1.0":
            self.send_json(400, {"error": "Explicit v1.0 selection required"})
            return False
        return True

    def do_GET(self) -> None:
        self.capture()
        if not self.authorize():
            return
        if self.server.failure_status is not None:
            self.send_json(self.server.failure_status, {"error": SENTINEL})
            return
        if self.path != "/a2a/agentCard/v1.0":
            self.send_json(404, {"error": "Unknown synthetic route"})
            return
        if self.server.malformed_json:
            content = b"not-json"
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
            return
        url = f"http://127.0.0.1:{self.server.server_port}/a2a"
        self.send_json(200, {
            "name": "Synthetic local agent",
            "description": "Offline HTTP demo; not Foundry.",
            "version": "1.0.0",
            "protocolVersion": "1.0",
            "supportedInterfaces": [{
                "url": url, "protocolBinding": "JSONRPC", "protocolVersion": "1.0",
            }],
            "capabilities": {"streaming": False},
            "defaultInputModes": ["text/plain"],
            "defaultOutputModes": ["text/plain"],
            "skills": [{
                "id": "diagnostic", "name": "diagnostic", "tags": ["demo"],
                "description": "Returns a synthetic diagnostic message",
            }],
            "securitySchemes": {"bearer": {"type": "http", "scheme": "bearer"}},
            "security": [{"bearer": []}],
        })

    def do_POST(self) -> None:
        if self.path != "/a2a":
            self.send_json(404, {"error": "Unknown synthetic route"})
            return
        if not self.authorize():
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 1 or length > 1024 * 1024:
                self.send_json(400, {"error": "Invalid request size"})
                return
            body = json.loads(self.rfile.read(length))
        except (ValueError, UnicodeError):
            self.send_json(400, {"error": "Invalid JSON request"})
            return
        if not isinstance(body, dict):
            self.send_json(400, {"error": "Request must be an object"})
            return
        self.capture(body)
        if self.server.failure_status is not None:
            self.send_json(self.server.failure_status, {"error": SENTINEL})
            return
        params = body.get("params")
        message = params.get("message") if isinstance(params, dict) else None
        if (
            body.get("jsonrpc") != "2.0" or body.get("method") != "SendMessage"
            or not isinstance(body.get("id"), str)
            or not isinstance(message, dict)
            or message.get("role") != "ROLE_USER"
            or not isinstance(message.get("messageId"), str)
            or message.get("parts") != [{"text": "Reply with exactly: A2A diagnostic OK"}]
        ):
            self.send_json(400, {"error": "Invalid synthetic v1.0 SendMessage request"})
            return
        result: Dict[str, object] = {"jsonrpc": "2.0", "id": body["id"]}
        if self.server.rpc_failure:
            result["error"] = {"code": -32602, "message": SENTINEL}
        elif self.server.task_state:
            result["result"] = {"task": {
                "id": "synthetic-task", "contextId": "synthetic-context",
                "status": {"state": self.server.task_state},
                "artifacts": [{
                    "artifactId": "synthetic-artifact",
                    "parts": [{"text": "A2A diagnostic OK"}],
                }],
            }}
        else:
            result["result"] = {"message": {
                "messageId": "synthetic-reply", "role": "ROLE_AGENT",
                "parts": [{"text": "A2A diagnostic OK"}],
            }}
        self.send_json(200, result)


class FixtureServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self) -> None:
        super().__init__(("127.0.0.1", 0), FixtureHandler)
        self.requests: List[Dict[str, object]] = []
        self.failure_status: Optional[int] = None
        self.rpc_failure = False
        self.task_state: Optional[str] = None
        self.malformed_json = False


def invoke_probe(pwsh: str, server: FixtureServer, exchange: bool) -> Dict[str, object]:
    script = str(ROOT / "a2a_diagnostic.ps1").replace("'", "''")
    url = f"http://127.0.0.1:{server.server_port}/a2a"
    function = "Test-A2AMessageExchange" if exchange else "Test-EndpointAccessibility"
    command = (
        f". '{script}'; "
        f"$result = {function} -Url '{url}' -Token '{SYNTHETIC_TOKEN}'; "
        "$result | ConvertTo-Json -Depth 20 -Compress"
    )
    try:
        process = subprocess.run(
            [pwsh, "-NoProfile", "-Command", command],
            capture_output=True, text=True, check=False, timeout=90,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise RuntimeError("Local PowerShell probe unavailable or timed out") from error
    if process.returncode != 0:
        raise RuntimeError("Local PowerShell probe failed; raw output omitted")
    if any(
        secret in process.stdout + process.stderr
        for secret in (SYNTHETIC_TOKEN, SENTINEL)
    ):
        raise RuntimeError("Local probe redaction assertion failed")
    try:
        result = json.loads(process.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError("Local probe returned malformed JSON") from error
    if (
        not isinstance(result, dict) or not isinstance(result.get("Success"), bool)
        or "StatusCode" not in result or "Category" not in result
    ):
        raise RuntimeError("Local probe returned an unexpected result shape")
    return result


def run_scenario(pwsh: str, scenario: str) -> Dict[str, object]:
    server = FixtureServer()
    server.failure_status = HTTP_SCENARIOS.get(scenario)
    server.rpc_failure = scenario == "rpc-error"
    server.task_state = "TASK_STATE_FAILED" if scenario == "failed-task" else None
    server.malformed_json = scenario == "malformed-json"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        card = invoke_probe(pwsh, server, exchange=False)
        message = invoke_probe(pwsh, server, exchange=True) if card["Success"] else None
        observed = bool(card["Success"] and message and message["Success"])
        expected = scenario == "success"
        failure = card if not card["Success"] else message
        if observed != expected:
            raise RuntimeError("Local scenario outcome did not match its expected result")
        expected_status = HTTP_SCENARIOS.get(scenario, 200)
        if failure is None or failure["StatusCode"] != expected_status:
            raise RuntimeError("Local scenario HTTP status did not match the injected case")
        expected_category = (
            "http-non-2xx" if scenario in HTTP_SCENARIOS else
            "invalid-json" if scenario == "malformed-json" else
            "rpc-error" if scenario == "rpc-error" else
            "task-not-completed" if scenario == "failed-task" else None
        )
        if failure["Category"] != expected_category:
            raise RuntimeError("Local scenario failure category did not match the injected case")
        for request in server.requests:
            if request["version"] != "1.0" or not request["synthetic_auth_matches"]:
                raise RuntimeError("Local wire version/header assertion failed")
        if len(server.requests) != (2 if card["Success"] else 1):
            raise RuntimeError("Unexpected requests or credential-bearing redirect")
        return {
            "scenario": scenario,
            "expected_outcome": "PASS" if expected else "FAIL",
            "observed_outcome": "PASS" if observed else "FAIL",
            "expectation_verified": True,
            "card_http_status": card["StatusCode"],
            "message_http_status": message["StatusCode"] if message else None,
            "category": failure["Category"],
            "version_header_verified": True,
            "synthetic_auth_header_verified": True,
            "reply_text": "A2A diagnostic OK (fixture-authored)" if observed else "OMITTED",
        }
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", choices=("all",) + SCENARIOS, default="all")
    parser.add_argument(
        "--evidence-file", type=Path, default=ROOT / "private-evidence" / "local-demo.json"
    )
    args = parser.parse_args(argv)
    pwsh = shutil.which("pwsh")
    if not pwsh:
        print("ERROR: Install PowerShell 7+; no Azure login is required.", file=sys.stderr)
        return 2
    versions = {"python": platform.python_version(), "os": platform.system()}
    cases: List[Dict[str, object]] = []
    evidence: Dict[str, object] = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "LOCAL_HTTP_FIXTURE_ONLY_NOT_AZURE",
        "identity_context": "Synthetic bearer value; no Entra identity",
        "protocol": "A2A 1.0 JSON-RPC; non-streaming text",
        "versions": versions,
        "cases": cases,
    }
    try:
        version = subprocess.run(
            [pwsh, "-NoProfile", "-Command", "$PSVersionTable.PSVersion.ToString()"],
            capture_output=True, text=True, check=True, timeout=30,
        ).stdout.strip()
        versions["powershell"] = version
        for scenario in SCENARIOS if args.scenario == "all" else (args.scenario,):
            case = run_scenario(pwsh, scenario)
            cases.append(case)
            print(
                f"{scenario}: expected {case['expected_outcome']}, "
                f"observed {case['observed_outcome']}; expectation verified"
            )
        evidence["outcome"] = "ALL_REQUESTED_EXPECTATIONS_VERIFIED"
        args.evidence_file.parent.mkdir(parents=True, exist_ok=True)
        args.evidence_file.write_text(
            json.dumps(evidence, indent=2) + "\n", encoding="utf-8"
        )
    except RuntimeError as error:
        print(f"ERROR: {error}. Evidence was not refreshed.", file=sys.stderr)
        return 1
    except (OSError, subprocess.SubprocessError):
        print(
            "ERROR: Local runtime or evidence write failed. Evidence was not refreshed.",
            file=sys.stderr,
        )
        return 1
    print("Local demo complete. Servers stopped. Azure/Entra/RBAC were NOT tested.")
    print("Sanitized evidence written to the requested evidence file.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
