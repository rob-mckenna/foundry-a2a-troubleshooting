#!/usr/bin/env python3
"""Static checks for Foundry A2A targets, not a live authorization test."""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlsplit


BASE_PATTERN = re.compile(
    r"/api/projects/([A-Za-z0-9_-]+)/agents/([A-Za-z0-9_-]+)/endpoint/protocols/a2a"
)
HOST_PATTERN = re.compile(r"([a-z0-9][a-z0-9-]*)\.services\.ai\.azure\.com")
AUTH_TYPES = {
    "AgenticIdentityToken",
    "ProjectManagedIdentity",
    "UserEntraToken",
    "AgentOnBehalfOfUser",
    "ServicePrincipal",
}
EXAMPLE = {
    "mode": "foundry_connection",
    "server_url": (
        "https://example.services.ai.azure.com/api/projects/example-project/"
        "agents/example-agent/endpoint/protocols/a2a"
    ),
    "tool_url": (
        "https://example.services.ai.azure.com/api/projects/example-project/"
        "agents/example-agent/endpoint/protocols/a2a"
    ),
    "auth_type": "AgenticIdentityToken",
    "audience": "https://ai.azure.com",
    "protocol_version": "1.0",
}


class A2AValidator:
    def __init__(self) -> None:
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.info: List[str] = []

    def validate_url_format(self, url: str, context: str = "URL") -> bool:
        try:
            parsed = urlsplit(url)
            if (
                parsed.scheme != "https"
                or not parsed.hostname
                or parsed.username is not None
                or parsed.password is not None
                or parsed.port is not None
                or "?" in url
                or "#" in url
                or any(character.isspace() for character in url)
                or "\\" in url
            ):
                self.errors.append(
                    f"{context}: require HTTPS without credentials, port, whitespace, "
                    "query, fragment, or backslash."
                )
                return False
        except ValueError:
            self.errors.append(f"{context}: malformed URL.")
            return False
        return True

    def validate_a2a_server_url(
        self, url: str
    ) -> Tuple[Optional[str], Optional[str], Optional[str], bool]:
        if not self.validate_url_format(url, "A2A target"):
            return None, None, None, False
        parsed = urlsplit(url)
        host_match = HOST_PATTERN.fullmatch(parsed.hostname or "")
        path_match = BASE_PATTERN.fullmatch(parsed.path.rstrip("/"))
        if not host_match or not path_match or parsed.path.endswith("//"):
            self.errors.append(
                "A2A target: expected a public-cloud Foundry A2A base URL "
                "using project and agent names, with no extra path segments."
            )
            return None, None, None, False
        if parsed.path.endswith("/"):
            self.warnings.append(
                "A2A target: trailing slash is normalized for comparison; "
                "use the documented base URL without it."
            )
        return host_match.group(1), path_match.group(1), path_match.group(2), True

    def validate_card_path(self, card_path: str) -> bool:
        if card_path not in ("agentCard/v1.0", "agentCard/v0.3"):
            self.errors.append(
                "Direct SDK card path must be agentCard/v1.0 or agentCard/v0.3, "
                "relative to the A2A base URL."
            )
            return False
        return True

    def compare_urls_consistency(
        self, server_url: str, tool_url: str, card_path: str = ""
    ) -> bool:
        server = self.validate_a2a_server_url(server_url)
        tool = self.validate_a2a_server_url(tool_url)
        if not server[3] or not tool[3]:
            return False
        if server[:3] != tool[:3]:
            self.errors.append("Server and tool URLs must identify the same target agent.")
            return False
        if card_path:
            resolved = urljoin(server_url.rstrip("/") + "/", card_path)
            allowed = {
                server_url.rstrip("/") + "/agentCard/v1.0",
                server_url.rstrip("/") + "/agentCard/v0.3",
            }
            if resolved not in allowed:
                self.errors.append(
                    "Resolved agent card must target the same host, project, and agent "
                    "and a supported discovery path."
                )
                return False
        self.info.append("Configured server and tool values identify the same target.")
        return True

    def validate_authentication_config(
        self, auth_type: str, managed_identity_type: str = ""
    ) -> bool:
        if auth_type not in AUTH_TYPES:
            self.errors.append(
                "Use an explicit auth_type: " + ", ".join(sorted(AUTH_TYPES)) + ". "
                "Entra/Azure AD/Managed Identity alone do not identify a caller."
            )
            return False
        expected_identity = {
            "AgenticIdentityToken": "Agent Identity",
            "ProjectManagedIdentity": "Project Managed Identity",
            "ServicePrincipal": "Service Principal",
            "UserEntraToken": "User",
            "AgentOnBehalfOfUser": "Agent Identity",
        }[auth_type]
        if managed_identity_type and managed_identity_type != expected_identity:
            self.errors.append("identity_type conflicts with auth_type.")
            return False
        if auth_type == "AgentOnBehalfOfUser":
            self.warnings.append(
                "AgentOnBehalfOfUser is preview; the source endpoint must use "
                "AgentBlueprint authorization and an appropriate incoming audience."
            )
        return True

    def check_rbac_requirements(self, auth_type: str, identity_type: str) -> None:
        self.info.append(
            "RBAC is NOT checked. The actual token principal needs Foundry Agent "
            "Consumer or equivalent endpoint permission on the target project or agent. "
            "Service calls and delegated user calls can represent different principals."
        )

    def validate_full_configuration(self, config: Dict[str, object]) -> bool:
        self.errors.clear()
        self.warnings.clear()
        self.info.clear()
        fields: Dict[str, str] = {}
        for key in (
            "mode", "server_url", "tool_url", "card_path", "auth_type",
            "identity_type", "audience", "protocol_version",
        ):
            value = config.get(key, "")
            if not isinstance(value, str):
                self.errors.append(f"{key}: must be a string.")
                fields[key] = ""
            else:
                fields[key] = value.strip()

        mode = fields["mode"]
        if mode not in ("foundry_connection", "direct_client"):
            self.errors.append("mode must be foundry_connection or direct_client.")
        server_url, tool_url = fields["server_url"], fields["tool_url"]
        if not server_url or not tool_url:
            self.errors.append("server_url and tool_url are required target values.")
        else:
            self.compare_urls_consistency(server_url, tool_url, fields["card_path"])

        version = fields["protocol_version"]
        if version not in ("1.0", "0.3"):
            self.errors.append("protocol_version must explicitly select 1.0 or 0.3.")
        elif version == "0.3":
            self.warnings.append("A2A 0.3 is preview; use 1.0 for new integrations.")

        card_path = fields["card_path"]
        if mode == "foundry_connection" and card_path:
            self.errors.append(
                "Omit card_path for a Foundry target connection; discovery is automatic."
            )
        elif mode == "direct_client":
            if self.validate_card_path(card_path) and card_path != "agentCard/v" + version:
                self.errors.append("card_path version conflicts with protocol_version.")

        auth_type = fields["auth_type"]
        self.validate_authentication_config(auth_type, fields["identity_type"])
        if mode == "foundry_connection" and auth_type == "ServicePrincipal":
            self.errors.append(
                "ServicePrincipal describes a direct client, not a RemoteA2A "
                "connection authType."
            )
        if fields["audience"] != "https://ai.azure.com":
            self.errors.append("Foundry target audience must be https://ai.azure.com.")
        self.check_rbac_requirements(auth_type, fields["identity_type"])
        self.info.append(
            "Static checks only: no credential, deployment, consent, DNS, RBAC, "
            "or message exchange was tested. URL checks target Azure public cloud only."
        )
        for heading, messages in (
            ("ERROR", self.errors), ("WARNING", self.warnings), ("INFO", self.info)
        ):
            for message in messages:
                print(f"{heading}: {message}")
        print("STATIC RESULT: " + ("FAIL" if self.errors else "PASS"))
        return not self.errors


def get_user_config() -> Dict[str, object]:
    config: Dict[str, object] = {}
    for field, prompt in (
        ("mode", "Mode (foundry_connection/direct_client)"),
        ("server_url", "Target server URL"),
        ("tool_url", "Target URL configured on caller"),
        ("card_path", "Card path (omit for foundry_connection)"),
        ("auth_type", "Auth type (AgenticIdentityToken/ProjectManagedIdentity/"
         "UserEntraToken/AgentOnBehalfOfUser/ServicePrincipal)"),
        ("identity_type", "Identity type (optional; must match auth_type)"),
        ("audience", "Target audience (https://ai.azure.com)"),
        ("protocol_version", "Protocol version (1.0 recommended)"),
    ):
        config[field] = input(prompt + ": ").strip()
    return config


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--interactive", action="store_true")
    source.add_argument("--config", type=Path, help="JSON configuration object")
    source.add_argument("--example", action="store_true", help="Print a sample, not validation")
    args = parser.parse_args(argv)
    if args.example:
        print(json.dumps(EXAMPLE, indent=2))
        return 0
    try:
        if args.interactive:
            config = get_user_config()
        else:
            with args.config.open(encoding="utf-8") as handle:
                config = json.load(handle)
        if not isinstance(config, dict):
            print("ERROR: configuration must be a JSON object.", file=sys.stderr)
            return 2
    except (OSError, UnicodeError, json.JSONDecodeError, EOFError):
        print("ERROR: unable to read a JSON object or complete input.", file=sys.stderr)
        return 2
    return 0 if A2AValidator().validate_full_configuration(config) else 1


if __name__ == "__main__":
    sys.exit(main())
