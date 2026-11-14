"""Opt-in, ownership-checked Foundry A2A sandbox. No third-party Python packages."""

import argparse
import base64
import datetime
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parent
TOOLKIT = "foundry-a2a-troubleshooting"
ARM = "https://management.azure.com"
AUDIENCE = "https://ai.azure.com"
API = "2025-06-01"
FOUNDRY_USER = "53ca6127-db72-4b80-b1b0-d745d6d5456d"
FOUNDRY_OWNER = "c883944f-8b7b-4483-af10-35834be79c4a"
AGENT_CONSUMER = "eed3b665-ab3a-47b6-8f48-c9382fb1dad6"
PROMPT = "Reply with exactly: A2A diagnostic OK"
CONTROLS = ("model", "target-responses", "caller-no-tools", "direct-a2a", "caller-a2a")


class SandboxError(Exception):
    """Only fixed, non-sensitive categories cross the transport boundary."""

    def __init__(self, category, status=None, details=None):
        super().__init__(category)
        self.category = category
        self.status = status
        self.details = details


def timestamp():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def object_value(value):
    if not isinstance(value, dict):
        raise SandboxError("invalid-json-object")
    return value


def write_json(path, value, exclusive=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    if exclusive:
        with path.open("x", encoding="utf-8") as stream:
            json.dump(value, stream, indent=2)
            stream.write("\n")
        return
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        with temporary.open("x", encoding="utf-8") as stream:
            json.dump(value, stream, indent=2)
            stream.write("\n")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def distinct_paths(state_path, evidence_path):
    if state_path.resolve() == evidence_path.resolve() or (
        state_path.exists() and evidence_path.exists()
        and os.path.samefile(state_path, evidence_path)
    ):
        raise SandboxError("state-evidence-path-collision")


def validate_uuid(value):
    try:
        if str(uuid.UUID(value)) != value:
            raise ValueError()
    except (ValueError, TypeError, AttributeError):
        raise SandboxError("invalid-uuid") from None
    return value


def new_state(subscription, location, model, version, sku, capacity):
    validate_uuid(subscription)
    for value in (location, model, version):
        if not isinstance(value, str) or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9.-]{0,79}", value):
            raise SandboxError("invalid-deployment-input")
    if sku not in ("GlobalStandard", "Standard") or type(capacity) is not int or not 1 <= capacity <= 10:
        raise SandboxError("invalid-deployment-input")
    run = uuid.uuid4().hex[:12]
    return {
        "schema_version": 1, "toolkit": TOOLKIT, "run_id": run,
        "subscription": subscription, "location": location,
        "resource_group": "rg-a2a-sandbox-" + run, "account": "a2asb" + run,
        "project": "a2a-demo", "deployment": "diagnostic",
        "target": "diagnostic-target", "caller": "diagnostic-caller",
        "model": model, "model_version": version, "sku": sku, "capacity": capacity,
        "phase": "preflight", "created_at": timestamp(),
    }


def load_state(path):
    state = object_value(json.loads(path.read_text(encoding="utf-8")))
    if state.get("schema_version") != 1 or state.get("toolkit") != TOOLKIT:
        raise SandboxError("invalid-state")
    run = state.get("run_id")
    if not isinstance(run, str) or not re.fullmatch(r"[0-9a-f]{12}", run):
        raise SandboxError("invalid-state")
    validate_uuid(state.get("subscription"))
    expected = {
        "resource_group": "rg-a2a-sandbox-" + run, "account": "a2asb" + run,
        "project": "a2a-demo", "deployment": "diagnostic",
        "target": "diagnostic-target", "caller": "diagnostic-caller",
    }
    if any(state.get(key) != value for key, value in expected.items()):
        raise SandboxError("inconsistent-state-target")
    # Validate all inputs even for cleanup; never trust edited recovery state.
    new_state(state["subscription"], state.get("location"), state.get("model"),
              state.get("model_version"), state.get("sku"), state.get("capacity"))
    return state


def ids(state):
    group = f"/subscriptions/{state['subscription']}/resourceGroups/{state['resource_group']}"
    account = group + f"/providers/Microsoft.CognitiveServices/accounts/{state['account']}"
    project = account + f"/projects/{state['project']}"
    endpoint = f"https://{state['account']}.services.ai.azure.com/api/projects/{state['project']}"
    return group, account, project, endpoint


def tags(state):
    return {"toolkit": TOOLKIT, "sandbox-run": state["run_id"]}


def target_url(state):
    return ids(state)[3] + f"/agents/{state['target']}/endpoint/protocols/a2a"


def cli(*arguments):
    executable = shutil.which("az")
    if not executable:
        raise SandboxError("azure-cli-not-installed")
    try:
        result = subprocess.run(
            [executable, *arguments, "--only-show-errors", "-o", "json"],
            capture_output=True, text=True, timeout=120, check=False,
        )
    except subprocess.TimeoutExpired:
        raise SandboxError("azure-cli-timeout") from None
    if result.returncode:
        raise SandboxError("azure-cli-failed")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        raise SandboxError("azure-cli-invalid-json") from None


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def safe_error_details(raw):
    text = raw.decode("utf-8", errors="replace").lower()
    markers = {
        "authentication": r"\bauthentication\b|\bunauthorized\b|\binvalid.token\b",
        "authorization": r"\bauthorization\b|\bforbidden\b|\bpermission",
        "throttling": r"\brate.limit|\bthrottl|\bquota\b",
        "connection": r"\bconnection\b",
        "agent_card": r"\bagent.card\b",
        "agent_identity": r"\bagentic.identity\b|\binstance.identity\b",
        "timeout": r"\btime.out\b|\btimeout\b|\btimed.out\b",
        "unsupported": r"\bnot.supported\b|\bunsupported\b",
    }
    return {
        "referenced_http_statuses": [
            status for status in (400, 401, 403, 404, 405, 408, 409, 424, 429, 500, 502, 503, 504)
            if re.search(r"\b" + str(status) + r"\b", text)
        ],
        "message_markers": {name: bool(re.search(pattern, text)) for name, pattern in markers.items()},
        "remote_error_text": "OMITTED",
    }


def diagnostic_body(raw):
    try:
        value = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        return {"json_valid": False}
    codes = []

    def visit(item, depth=0):
        if depth > 8:
            return
        if isinstance(item, dict):
            code = item.get("code")
            if isinstance(code, str) and re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]{0,95}", code):
                codes.append(code)
            for key in ("error", "innererror", "inner_error", "details", "output"):
                visit(item.get(key), depth + 1)
        elif isinstance(item, list):
            for child in item[:50]:
                visit(child, depth + 1)

    visit(value)
    result = {"json_valid": True, "error_codes": sorted(set(codes))}
    if isinstance(value, dict):
        result["response_failed"] = value.get("status") == "failed"
        error = value.get("error")
        if isinstance(error, dict):
            additional = error.get("additionalInfo")
            if isinstance(additional, dict):
                source = additional.get("rate_limit_source")
                if isinstance(source, str) and re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]{0,95}", source):
                    result["rate_limit_source"] = source
        output = value.get("output")
        if isinstance(output, list):
            result["output_items"] = [
                {key: item[key] for key in ("type", "status")
                 if isinstance(item.get(key), str)
                 and re.fullmatch(r"[a-z][a-z0-9_]{0,63}", item[key])}
                for item in output[:50] if isinstance(item, dict)
            ]
    return result


class PrivateDiagnostics:
    """Append allowlisted metadata under the ignored private-evidence directory."""

    def __init__(self, path, state_path, evidence_path):
        self.path = path.resolve()
        if not self.path.is_relative_to((ROOT / "private-evidence").resolve()):
            raise SandboxError("diagnostics-must-be-private")
        distinct_paths(self.path, state_path)
        distinct_paths(self.path, evidence_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.run_id = str(uuid.uuid4())
        self.operation = "azure-request"

    def record(self, started, method, status, response_headers, raw, client_id, transport_failed=False):
        identifiers = {}
        for name in ("apim-request-id", "x-request-id", "request-id", "x-ms-request-id",
                     "x-ms-correlation-request-id", "traceparent"):
            value = response_headers.get(name)
            if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_-]{8,128}", value):
                identifiers[name] = value
        rate_headers = {}
        for name in ("retry-after", "retry-after-ms", "x-ratelimit-remaining-requests",
                     "x-ratelimit-remaining-tokens", "x-ratelimit-reset-requests",
                     "x-ratelimit-reset-tokens"):
            value = response_headers.get(name)
            if isinstance(value, str) and re.fullmatch(r"[0-9.ms ]{1,30}", value):
                rate_headers[name] = value
        event = {
            "run_id": self.run_id, "started_at": started, "finished_at": timestamp(),
            "operation": self.operation,
            "method": method, "http_status": status, "client_request_id": client_id,
            "correlation_ids": identifiers, "transport_failed": transport_failed,
            "rate_limit_headers": rate_headers,
            "body_metadata": diagnostic_body(raw), "error_markers": safe_error_details(raw),
        }
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(event) + "\n")


class Azure:
    def __init__(self, subscription, diagnostics=None):
        self.subscription = subscription
        self.diagnostics = diagnostics
        self.opener = urllib.request.build_opener(NoRedirect())

    def token(self, resource):
        result = object_value(cli(
            "account", "get-access-token", "--subscription", self.subscription,
            "--resource", resource,
        ))
        token = result.get("accessToken")
        if not isinstance(token, str) or not token:
            raise SandboxError("missing-access-token")
        return token

    def request(self, method, url, body=None, authenticated=True, headers=None):
        started = timestamp()
        client_id = str(uuid.uuid4())
        options = {"Accept": "application/json", **(headers or {})}
        options["x-ms-client-request-id"] = client_id
        if authenticated:
            resource = ARM + "/" if url.startswith(ARM + "/") else AUDIENCE
            options["Authorization"] = "Bearer " + self.token(resource)
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            options["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=data, headers=options, method=method)
        try:
            with self.opener.open(request, timeout=120) as response:
                status = response.status
                raw = response.read(4 * 1024 * 1024 + 1)
                response_headers = response.headers
        except urllib.error.HTTPError as error:
            status = error.code
            try:
                raw = error.read(65536)
                details = safe_error_details(raw)
                if self.diagnostics:
                    self.diagnostics.record(started, method, status, error.headers, raw, client_id)
            finally:
                error.close()
            raise SandboxError("http-non-2xx", status, details) from None
        except (urllib.error.URLError, TimeoutError):
            if self.diagnostics:
                self.diagnostics.record(started, method, None, {}, b"", client_id, transport_failed=True)
            raise SandboxError("transport-failure") from None
        if self.diagnostics:
            self.diagnostics.record(started, method, status, response_headers, raw, client_id)
        if not 200 <= status < 300:
            raise SandboxError("http-non-2xx", status)
        if not raw:
            return {}
        if len(raw) > 4 * 1024 * 1024:
            raise SandboxError("response-too-large", status)
        try:
            return object_value(json.loads(raw))
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise SandboxError("invalid-json", status) from None

    def arm(self, method, resource, body=None, api=API):
        return self.request(method, ARM + resource + "?api-version=" + api, body)


def wait_read(read, ready, attempts=30, delay=10):
    for attempt in range(attempts):
        try:
            value = read()
            if ready(value):
                return value
        except SandboxError as error:
            if error.status not in (401, 403, 404, 409, 429, 500, 502, 503, 504):
                raise
            if attempt == attempts - 1:
                raise
        if attempt != attempts - 1:
            time.sleep(delay)
    raise SandboxError("readiness-timeout")


def provisioned(value):
    state = object_value(value.get("properties", {})).get("provisioningState")
    if state in ("Failed", "Canceled"):
        raise SandboxError("provisioning-failed")
    return state == "Succeeded"


def verify_owner(azure, state):
    group = azure.arm("GET", ids(state)[0], api="2022-09-01")
    if str(group.get("id", "")).lower() != ids(state)[0].lower():
        raise SandboxError("resource-group-id-mismatch")
    actual = object_value(group.get("tags", {}))
    if any(actual.get(key) != value for key, value in tags(state).items()):
        raise SandboxError("resource-group-ownership-mismatch")
    return group


def model_preflight(azure, state):
    subscription = object_value(cli("account", "show", "--subscription", state["subscription"]))
    if subscription.get("state") != "Enabled":
        raise SandboxError("subscription-not-enabled")
    provider = object_value(cli(
        "provider", "show", "--namespace", "Microsoft.CognitiveServices",
        "--subscription", state["subscription"],
    ))
    if provider.get("registrationState") != "Registered":
        raise SandboxError("provider-not-registered")
    catalog = cli("cognitiveservices", "model", "list",
                  "--subscription", state["subscription"], "--location", state["location"])
    if not isinstance(catalog, list):
        raise SandboxError("invalid-model-catalog")
    candidates = []
    selected = None
    for record in catalog:
        model = object_value(object_value(record).get("model", {}))
        if (model.get("name"), model.get("version"), model.get("format")) != (
            state["model"], state["model_version"], "OpenAI"
        ):
            continue
        capabilities = object_value(model.get("capabilities", {}))
        if any(str(capabilities.get(key)).lower() != "true" for key in ("responses", "agentsV2")):
            continue
        for sku in model.get("skus", []):
            sku = object_value(sku)
            usage = sku.get("usageName")
            if sku.get("name") == state["sku"] and isinstance(usage, str) and not usage.endswith("-finetune"):
                candidates.append(sku)
                selected = model
    if not candidates or selected is None:
        raise SandboxError("model-version-sku-not-supported")
    sku = candidates[0]
    bounds = object_value(sku.get("capacity") or {})
    minimum = bounds.get("minimum") or 1
    maximum = bounds.get("maximum")
    step = bounds.get("step") or 1
    capacity = state["capacity"]
    if capacity < minimum or (maximum is not None and capacity > maximum) or (capacity - minimum) % step:
        raise SandboxError("capacity-out-of-range")
    usage = cli("cognitiveservices", "usage", "list",
                "--subscription", state["subscription"], "--location", state["location"])
    if not isinstance(usage, list):
        raise SandboxError("invalid-quota-response")
    quotas = [item for item in usage if object_value(item.get("name", {})).get("value") == sku["usageName"]]
    if not quotas:
        raise SandboxError("quota-not-found")
    if quotas[0]["limit"] - quotas[0]["currentValue"] < capacity:
        raise SandboxError("insufficient-quota")
    return {
        "model_lifecycle": selected.get("lifecycleStatus"),
        "model_inference_deprecation": object_value(selected.get("deprecation", {})).get("inference"),
        "cli_identity_type": object_value(subscription.get("user", {})).get("type"),
    }


def bootstrap_identity(azure):
    # Read only the object ID claim locally; this is not token validation.
    token = azure.token(ARM + "/")
    try:
        encoded = token.split(".")[1]
        claims = object_value(json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))))
        return validate_uuid(claims.get("oid"))
    except (IndexError, ValueError, UnicodeDecodeError):
        raise SandboxError("bootstrap-principal-unresolved") from None


def assign_role(azure, scope, principal, role, principal_type="ServicePrincipal"):
    validate_uuid(principal)
    name = str(uuid.uuid5(uuid.NAMESPACE_URL, scope.lower() + principal + role))
    return azure.arm("PUT", scope + "/providers/Microsoft.Authorization/roleAssignments/" + name, {
        "properties": {
            "principalId": principal,
            "principalType": principal_type,
            "roleDefinitionId": f"/subscriptions/{azure.subscription}/providers/Microsoft.Authorization/roleDefinitions/{role}",
        },
    }, api="2022-04-01")


def direct_probe(azure, state, send_message):
    pwsh = shutil.which("pwsh")
    if not pwsh:
        raise SandboxError("powershell-not-installed")
    command = (
        "$ErrorActionPreference='Stop'; "
        "$p=[Console]::In.ReadToEnd()|ConvertFrom-Json; . $env:A2A_DIAGNOSTIC_SCRIPT; "
        "& { if ($p.send) {Test-A2AMessageExchange -Url $p.url -Token $p.token} "
        "else {Test-EndpointAccessibility -Url $p.url -Token $p.token} } "
        "|ConvertTo-Json -Depth 20 -Compress"
    )
    # The token is sent through stdin, never command-line arguments or a file.
    payload = {
        "url": target_url(state),
        "token": azure.token(AUDIENCE), "send": send_message,
    }
    try:
        result = subprocess.run(
            [pwsh, "-NoProfile", "-Command", command],
            input=json.dumps(payload), capture_output=True, text=True, timeout=150,
            env={**os.environ, "A2A_DIAGNOSTIC_SCRIPT": str(ROOT / "a2a_diagnostic.ps1")},
            check=False,
        )
    except subprocess.TimeoutExpired:
        raise SandboxError("direct-probe-timeout") from None
    if result.returncode:
        raise SandboxError("direct-probe-process-failed")
    try:
        value = object_value(json.loads(result.stdout))
    except json.JSONDecodeError:
        raise SandboxError("direct-probe-invalid-json") from None
    if type(value.get("Success")) is not bool:
        raise SandboxError("direct-probe-invalid-result")
    return value


def tool_summary(response):
    output = response.get("output")
    if not isinstance(output, list):
        raise SandboxError("invalid-responses-output")
    # GA tool configuration still emits these legacy-named Responses item types.
    calls = [item for item in output if isinstance(item, dict) and item.get("type") == "a2a_preview_call"]
    results = [item for item in output if isinstance(item, dict) and item.get("type") == "a2a_preview_call_output"]
    completed = []
    seen = set()
    for call in calls:
        call_id = call.get("call_id")
        if not isinstance(call_id, str) or not call_id.strip() or call_id in seen:
            continue
        seen.add(call_id)
        paired = [item for item in results if item.get("call_id") == call_id]
        if len(paired) != 1:
            continue
        result = paired[0]
        if any(item.get("status") != "completed" or item.get("error")
               or not isinstance(item.get("id"), str) or not item["id"].strip()
               for item in (call, result)):
            continue
        if not isinstance(call.get("name"), str) or not call["name"].strip() or result.get("name") != call["name"]:
            continue
        text = result.get("output")
        if not isinstance(text, str) or not text.strip():
            continue
        # This synthetic probe deliberately verifies the remote output, not the
        # caller's final answer or a status paired with an embedded error body.
        if text.strip() != "A2A diagnostic OK":
            continue
        completed.append(result)
    return {
        "success": response.get("status") == "completed" and bool(completed)
        and len(completed) == len(calls) == len(results) and not response.get("error"),
        "a2a_calls": len(calls), "completed_a2a_calls": len(completed),
        "matched_call_outputs": len(completed),
        "remote_diagnostic_reply_verified": bool(completed),
        "output_item_types": ["a2a_preview_call", "a2a_preview_call_output"],
        "remote_text": "OMITTED",
    }


def agent_version(value):
    if "versions" in value:
        value = object_value(object_value(value["versions"]).get("latest"))
    version = value.get("version")
    if not isinstance(version, str) or not re.fullmatch(r"[0-9]+(?:\.[0-9]+)*", version):
        raise SandboxError("agent-version-unresolved")
    return version


def responses_text_summary(response):
    output = response.get("output")
    if not isinstance(output, list):
        raise SandboxError("invalid-responses-output")
    text_present = any(
        isinstance(item, dict) and item.get("type") == "message"
        and item.get("role") == "assistant"
        and isinstance(item.get("content"), list)
        and any(isinstance(part, dict) and part.get("type") == "output_text"
                and isinstance(part.get("text"), str) and part["text"].strip()
                for part in item["content"])
        for item in output
    )
    unexpected_tools = any(
        not isinstance(item, dict) or item.get("type") not in ("message", "reasoning")
        for item in output
    )
    return {
        "success": response.get("status") == "completed" and bool(text_present)
        and not response.get("error") and not unexpected_tools,
        "text_present": bool(text_present), "unexpected_tool_output": unexpected_tools,
        "remote_text": "OMITTED",
    }


class Sandbox:
    def __init__(self, state_path, evidence_path=None, diagnostics_path=None):
        self.state_path = state_path
        self.evidence_path = evidence_path
        self.state = {}
        self.recording = False
        self.diagnostics_path = diagnostics_path
        self.diagnostics = None
        self.evidence = {
            "scope": "AZURE_SANDBOX", "recorded_at": timestamp(), "success": False,
            "protocol": "1.0", "python": platform.python_version(),
            "identity_context": {
                "direct": "current Azure CLI principal",
                "two_agent": "calling agent instance identity; app-only",
                "delegation_tested": False,
            },
            "checks": [],
        }

    def phase(self, name):
        self.state["phase"] = name
        if self.diagnostics:
            self.diagnostics.operation = name
        write_json(self.state_path, self.state)
        print("Azure sandbox phase: " + name, flush=True)

    def save_evidence(self):
        if self.evidence_path:
            write_json(self.evidence_path, self.evidence)

    def enable_diagnostics(self):
        if self.diagnostics_path and not self.diagnostics:
            self.diagnostics = PrivateDiagnostics(
                self.diagnostics_path, self.state_path, self.evidence_path,
            )

    def create(self, args):
        if not args.accept_cost:
            raise SandboxError("cost-acceptance-required")
        if self.evidence_path is None:
            raise SandboxError("evidence-path-required")
        distinct_paths(self.state_path, self.evidence_path)
        if self.state_path.exists():
            raise SandboxError("state-already-exists")
        self.enable_diagnostics()
        self.state = new_state(args.subscription, args.location, args.model,
                               args.model_version, args.sku, args.capacity)
        self.recording = True
        print("Azure sandbox phase: checking-prerequisites", flush=True)
        self.evidence.update({
            "location": args.location, "model": args.model, "model_version": args.model_version,
            "sku": args.sku, "capacity": args.capacity,
        })
        self.evidence["powershell"] = powershell_version()
        self.evidence["azure_cli"] = object_value(cli("version")).get("azure-cli")
        azure = Azure(self.state["subscription"], self.diagnostics)
        metadata = model_preflight(azure, self.state)
        self.state.update(metadata)
        self.evidence.update(metadata)
        group, account, project, endpoint = ids(self.state)
        try:
            azure.arm("GET", group, api="2022-09-01")
        except SandboxError as error:
            if error.status != 404:
                raise
        else:
            raise SandboxError("resource-group-collision")
        principal = bootstrap_identity(azure)
        write_json(self.state_path, self.state, exclusive=True)
        self.recording = True
        self.phase("creating-resource-group")
        azure.arm("PUT", group, {"location": self.state["location"], "tags": tags(self.state)}, api="2022-09-01")
        verify_owner(azure, self.state)
        self.phase("creating-foundry-account")
        azure.arm("PUT", account, {
            "location": self.state["location"], "kind": "AIServices", "sku": {"name": "S0"},
            "identity": {"type": "SystemAssigned"}, "tags": tags(self.state),
            "properties": {
                "allowProjectManagement": True, "customSubDomainName": self.state["account"],
                "disableLocalAuth": True, "publicNetworkAccess": "Enabled",
            },
        })
        wait_read(lambda: azure.arm("GET", account), provisioned, attempts=60)
        self.phase("creating-project")
        azure.arm("PUT", project, {
            "location": self.state["location"], "identity": {"type": "SystemAssigned"},
            "tags": tags(self.state),
            "properties": {"displayName": "A2A diagnostic sandbox", "description": "Synthetic disposable A2A diagnostic"},
        })
        project_object = wait_read(lambda: azure.arm("GET", project), provisioned)
        self.phase("assigning-bootstrap-permissions")
        assign_role(azure, account, principal, FOUNDRY_OWNER,
                    "User" if self.state.get("cli_identity_type") == "user" else "ServicePrincipal")
        project_principal = object_value(project_object.get("identity", {})).get("principalId")
        assign_role(azure, account, project_principal, FOUNDRY_USER)
        self.phase("deploying-model")
        azure.arm("PUT", account + "/deployments/" + self.state["deployment"], {
            "sku": {"name": self.state["sku"], "capacity": self.state["capacity"]},
            "properties": {
                "model": {"format": "OpenAI", "name": self.state["model"], "version": self.state["model_version"]},
                "versionUpgradeOption": "NoAutoUpgrade",
            },
        })
        wait_read(lambda: azure.arm("GET", account + "/deployments/" + self.state["deployment"]), provisioned)
        self.phase("waiting-for-project-access")
        wait_read(lambda: azure.request("GET", endpoint + "/agents?api-version=v1"), lambda value: True)
        self.phase("creating-target-agent")
        target = azure.request("POST", endpoint + "/agents?api-version=v1", {
            "name": self.state["target"],
            "definition": {"kind": "prompt", "model": self.state["deployment"],
                           "instructions": "Respond to synthetic diagnostics only. " + PROMPT},
        })
        self.state["target_version"] = agent_version(target)
        azure.request("PATCH", endpoint + f"/agents/{self.state['target']}?api-version=v1", {
            "agent_card": {
                "description": "Synthetic diagnostic responder", "version": "1.0",
                "skills": [{"id": "diagnostic", "name": "Diagnostic",
                            "description": "Responds to a synthetic diagnostic prompt"}],
            },
            "agent_endpoint": {"protocol_configuration": {"responses": {}, "a2a": {}}},
        })
        self.phase("creating-a2a-connection")
        connection = project + "/connections/diagnostic-a2a"
        azure.arm("PUT", connection, {"properties": {
            "authType": "AgenticIdentityToken", "category": "RemoteA2A",
            "target": target_url(self.state),
            "audience": AUDIENCE, "Credentials": {}, "metadata": {},
        }}, api="2025-04-01-preview")
        self.phase("creating-calling-agent")
        caller = azure.request("POST", endpoint + "/agents?api-version=v1", {
            "name": self.state["caller"],
            "definition": {
                "kind": "prompt", "model": self.state["deployment"],
                "instructions": "Always call the remote diagnostic agent once and report its reply.",
                "tools": [{"type": "a2a", "a2a_version": "1.0", "project_connection_id": connection}],
            },
        })
        self.state["caller_version"] = agent_version(caller)
        self.phase("resolving-caller-instance-identity")
        details = wait_read(
            lambda: azure.request("GET", endpoint + f"/agents/{self.state['caller']}?api-version=v1"),
            lambda value: bool(object_value(value.get("instance_identity") or {}).get("principal_id")),
        )
        caller_principal = object_value(details["instance_identity"]).get("principal_id")
        assign_role(azure, project, caller_principal, AGENT_CONSUMER)
        self.state["caller_identity_resolved"] = True
        self.phase("waiting-for-authenticated-card")

        def card_read():
            value = direct_probe(azure, self.state, False)
            if not value["Success"]:
                raise SandboxError("card-not-ready", value.get("StatusCode"))
            return value

        wait_read(card_read, lambda value: True)
        # Role writes are control-plane confirmations, not proof of propagation.
        # Allow a bounded settling interval without replaying billable messages.
        time.sleep(60)
        self.phase("ready")
        if getattr(args, "provision_only", False):
            self.evidence["provisioning_success"] = True
            self.evidence["verification_status"] = "not-run"
            self.save_evidence()
            return self.evidence
        return self.probe(args.accept_cost)

    def probe(self, accept_cost):
        if not accept_cost:
            raise SandboxError("cost-acceptance-required")
        if self.evidence_path is None:
            raise SandboxError("evidence-path-required")
        distinct_paths(self.state_path, self.evidence_path)
        self.enable_diagnostics()
        self.state = load_state(self.state_path)
        if self.state.get("phase") not in ("ready", "probing", "probe-failed", "verified"):
            raise SandboxError("sandbox-not-ready")
        azure = Azure(self.state["subscription"], self.diagnostics)
        verify_owner(azure, self.state)
        self.recording = True
        self.phase("probing")
        context = object_value(cli("account", "show", "--subscription", self.state["subscription"]))
        self.evidence.update({
            "azure_cli": object_value(cli("version")).get("azure-cli"),
            "powershell": powershell_version(), "location": self.state["location"],
            "model": self.state["model"], "model_version": self.state["model_version"],
            "sku": self.state["sku"], "capacity": self.state["capacity"],
            "model_lifecycle": self.state.get("model_lifecycle"),
            "target_agent_version": self.state.get("target_version"),
            "calling_agent_version": self.state.get("caller_version"),
            "cli_identity_type": object_value(context.get("user", {})).get("type"),
        })
        self.save_evidence()
        try:
            azure.request(
                "GET", target_url(self.state) + "/agentCard/v1.0", authenticated=False,
                headers={"A2A-Version": "1.0"},
            )
        except SandboxError as error:
            rejected = error.status in (401, 403)
            self.evidence["checks"].append({
                "name": "anonymous-card-rejected", "expected": "401-or-403",
                "http_status": error.status, "expectation_verified": rejected,
            })
            self.save_evidence()
            if not rejected:
                raise
        else:
            raise SandboxError("anonymous-card-unexpectedly-accessible")
        for name, send in (("authenticated-card", False), ("direct-v1-message", True)):
            result = direct_probe(azure, self.state, send)
            # The existing diagnostic owns protocol validation and redaction.
            self.evidence["checks"].append({"name": name, **result})
            self.save_evidence()
            if not result["Success"]:
                self.phase("probe-failed")
                raise SandboxError(name + "-failed", result.get("StatusCode"))
        endpoint = ids(self.state)[3]
        self.phase("probing-calling-agent")
        response = azure.request("POST", endpoint + "/openai/v1/responses", {
            "input": "Call the remote diagnostic agent once. " + PROMPT,
            "tool_choice": "required", "parallel_tool_calls": False,
            "max_output_tokens": 512, "max_tool_calls": 1,
            "agent_reference": {"name": self.state["caller"], "type": "agent_reference"},
        })
        summary = tool_summary(response)
        self.evidence["checks"].append({"name": "agent-to-agent", **summary})
        self.evidence["success"] = summary["success"]
        self.save_evidence()
        self.phase("verified" if summary["success"] else "probe-failed")
        if not summary["success"]:
            raise SandboxError("successful-a2a-tool-call-not-observed")
        return self.evidence

    def cleanup(self, confirm):
        if not confirm:
            raise SandboxError("delete-confirmation-required")
        self.state = load_state(self.state_path)
        azure = Azure(self.state["subscription"])
        try:
            verify_owner(azure, self.state)
        except SandboxError as error:
            if error.status == 404:
                self.phase("deleted")
                return
            raise
        self.phase("deleting")
        azure.arm("DELETE", ids(self.state)[0], api="2022-09-01")

        def deleted():
            try:
                verify_owner(azure, self.state)
            except SandboxError as error:
                if error.status == 404:
                    return {"deleted": True}
                raise
            return {"deleted": False}

        wait_read(deleted, lambda value: value["deleted"], attempts=90)
        self.phase("deleted")

    def diagnose(self, accept_cost, control):
        if not accept_cost:
            raise SandboxError("cost-acceptance-required")
        if self.evidence_path is None:
            raise SandboxError("evidence-path-required")
        distinct_paths(self.state_path, self.evidence_path)
        self.enable_diagnostics()
        self.state = load_state(self.state_path)
        if self.state.get("phase") not in ("ready", "probe-failed", "verified", "diagnosing"):
            raise SandboxError("sandbox-not-ready")
        azure = Azure(self.state["subscription"], self.diagnostics)
        verify_owner(azure, self.state)
        self.recording = True
        self.phase("diagnosing")
        self.evidence.update({
            "scope": "AZURE_ISOLATION_CONTROLS",
            "model": self.state["model"], "model_version": self.state["model_version"],
            "location": self.state["location"], "sku": self.state["sku"],
            "capacity": self.state["capacity"], "model_lifecycle": self.state.get("model_lifecycle"),
            "target_agent_version": self.state.get("target_version"),
            "calling_agent_version": self.state.get("caller_version"),
            "powershell": powershell_version(),
            "azure_cli": object_value(cli("version")).get("azure-cli"),
            "cli_identity_type": object_value(object_value(cli(
                "account", "show", "--subscription", self.state["subscription"],
            )).get("user", {})).get("type"),
        })
        selected = CONTROLS if control == "all" else (control,)
        for name in selected:
            print("Azure isolation control: " + name, flush=True)
            if self.diagnostics:
                self.diagnostics.operation = name
            started = timestamp()
            try:
                if name == "direct-a2a":
                    result = direct_probe(azure, self.state, True)
                    summary = {"success": result["Success"], "http_status": result.get("StatusCode"),
                               "category": result.get("Category"), "remote_text": "OMITTED"}
                else:
                    body = {"input": PROMPT, "max_output_tokens": 512}
                    if name == "model":
                        body["model"] = self.state["deployment"]
                    else:
                        agent = self.state["target"] if name == "target-responses" else self.state["caller"]
                        body["agent_reference"] = {"name": agent, "type": "agent_reference"}
                    if name == "caller-a2a":
                        body.update(tool_choice="required", parallel_tool_calls=False, max_tool_calls=1)
                    else:
                        body.update(tools=[], tool_choice="none")
                    response = azure.request("POST", ids(self.state)[3] + "/openai/v1/responses", body)
                    summary = tool_summary(response) if name == "caller-a2a" else responses_text_summary(response)
            except SandboxError as error:
                summary = {"success": False, "category": error.category, "http_status": error.status}
                if error.details:
                    summary["details"] = error.details
            self.evidence["checks"].append({"name": name, "started_at": started,
                                            "finished_at": timestamp(), **summary})
            self.save_evidence()
        self.evidence["success"] = all(item["success"] for item in self.evidence["checks"])
        self.phase("ready" if self.evidence["success"] else "probe-failed")
        self.save_evidence()
        if not self.evidence["success"]:
            raise SandboxError("isolation-control-failed")
        return self.evidence


def powershell_version():
    pwsh = shutil.which("pwsh")
    if not pwsh:
        raise SandboxError("powershell-not-installed")
    process = subprocess.run(
        [pwsh, "-NoProfile", "-Command", "$PSVersionTable.PSVersion.ToString()"],
        capture_output=True, text=True, check=False, timeout=30,
    )
    if process.returncode or not re.fullmatch(r"\d+\.\d+\.\d+(?:[-+\w.]*)?", process.stdout.strip()):
        raise SandboxError("powershell-version-failed")
    return process.stdout.strip()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    for action in ("create", "probe", "diagnose", "cleanup"):
        command = commands.add_parser(action)
        command.add_argument("--state-file", type=Path, default=ROOT / "private-evidence" / "sandbox-state.json")
        if action == "cleanup":
            command.add_argument("--confirm-delete", action="store_true")
        else:
            command.add_argument("--accept-cost", action="store_true")
            command.add_argument("--evidence-file", type=Path, default=ROOT / "private-evidence" / "azure-sandbox.json")
            command.add_argument("--diagnostics-file", type=Path,
                                 help="Append private codes/correlation metadata under private-evidence.")
        if action == "create":
            command.add_argument("--provision-only", action="store_true",
                                 help="Create and check readiness without sending inference probes.")
            for name in ("subscription", "location", "model", "model-version"):
                command.add_argument("--" + name, required=True)
            command.add_argument("--sku", choices=("GlobalStandard", "Standard"), default="GlobalStandard")
            command.add_argument("--capacity", type=int, default=1)
        if action == "diagnose":
            command.add_argument("--control", choices=("all", *CONTROLS), default="all")
    args = parser.parse_args(argv)
    sandbox = Sandbox(args.state_file, getattr(args, "evidence_file", None),
                      getattr(args, "diagnostics_file", None))
    try:
        if args.action == "create":
            sandbox.create(args)
        elif args.action == "probe":
            sandbox.probe(args.accept_cost)
        elif args.action == "diagnose":
            sandbox.diagnose(args.accept_cost, args.control)
        else:
            sandbox.cleanup(args.confirm_delete)
    except (SandboxError, OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired) as error:
        category = error.category if isinstance(error, SandboxError) else "local-state-or-runtime-failure"
        status = error.status if isinstance(error, SandboxError) else None
        print(f"Azure sandbox failed: {category}; HTTP status: {status or 'not available'}. "
              "Preserve private state for diagnosis/cleanup.", file=sys.stderr)
        if sandbox.recording and sandbox.evidence_path:
            failed_phase = sandbox.state.get("phase", "preflight")
            sandbox.evidence["failure"] = {
                "phase": failed_phase, "category": category, "http_status": status,
            }
            if isinstance(error, SandboxError) and error.details:
                sandbox.evidence["failure"]["details"] = error.details
            sandbox.evidence["success"] = False
            try:
                if failed_phase.startswith("probing"):
                    sandbox.phase("probe-failed")
                sandbox.save_evidence()
            except OSError:
                print("Evidence write failed; private state was preserved.", file=sys.stderr)
        return 1
    print("Azure sandbox " + args.action + " completed. Review sanitized evidence and cleanup state.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
