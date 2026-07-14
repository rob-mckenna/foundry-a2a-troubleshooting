#!/usr/bin/env python3
"""
Foundry A2A Configuration Validator
Helps troubleshoot Agent-to-Agent communication issues in Microsoft Foundry
"""

import re
import sys
import json
from urllib.parse import urlparse
from typing import Tuple, List, Dict

class A2AValidator:
    def __init__(self):
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.info: List[str] = []
    
    def validate_url_format(self, url: str, context: str = "") -> bool:
        """Validate URL format and structure"""
        try:
            parsed = urlparse(url)
            
            # Check basic URL structure
            if not parsed.scheme:
                self.errors.append(f"{context}: Missing URL scheme (http/https)")
                return False
            if parsed.scheme not in ['http', 'https']:
                self.errors.append(f"{context}: Invalid scheme '{parsed.scheme}', must be http or https")
                return False
            if not parsed.netloc:
                self.errors.append(f"{context}: Missing hostname/netloc")
                return False
            
            # Check for trailing slashes (can cause issues)
            if url.endswith('/') and context.endswith('URL'):
                self.warnings.append(f"{context}: Contains trailing slash, might cause path matching issues")
            
            return True
        except Exception as e:
            self.errors.append(f"{context}: Invalid URL format - {str(e)}")
            return False
    
    def validate_a2a_server_url(self, url: str) -> Tuple[str, str, str, bool]:
        """
        Extract and validate A2A endpoint URL components
        Expected format: https://{account}.services.ai.azure.com/api/projects/{project}/agents/{agent}/endpoint/protocols/a2a
        """
        # Regex pattern for A2A endpoint URL
        pattern = r'https://([^.]+)\.services\.ai\.azure\.com/api/projects/([^/]+)/agents/([^/]+)/endpoint/protocols/a2a'
        
        match = re.match(pattern, url.rstrip('/'))
        
        if not match:
            self.errors.append(f"A2A Server URL does not match expected format: {url}")
            self.info.append("Expected: https://{account}.services.ai.azure.com/api/projects/{project}/agents/{agent}/endpoint/protocols/a2a")
            return None, None, None, False
        
        account, project, agent = match.groups()
        return account, project, agent, True
    
    def validate_card_path(self, card_path: str) -> bool:
        """Validate agent card path format"""
        if not card_path:
            self.errors.append("Card path is empty")
            return False
        
        # Card path should be relative (no http/https)
        if card_path.startswith('http://') or card_path.startswith('https://'):
            self.warnings.append("Card path appears to be absolute URL, should be relative path like 'agentCard/v1.0'")
            return True  # Not necessarily an error, just unusual
        
        # Common valid patterns
        valid_patterns = [
            r'^agentCard/v1\.0$',
            r'^agentCard$',
            r'^card$',
        ]
        
        if not any(re.match(pattern, card_path) for pattern in valid_patterns):
            self.warnings.append(f"Card path '{card_path}' doesn't match common patterns (agentCard/v1.0, agentCard, card)")
        
        return True
    
    def compare_urls_consistency(self, server_url: str, tool_url: str, card_path: str) -> bool:
        """Verify that server URL and tool URL reference the same host/project/agent"""
        # Extract components from server URL
        server_account, server_project, server_agent, server_valid = self.validate_a2a_server_url(server_url)
        
        if not server_valid:
            return False
        
        # Verify tool URL contains the same host/project/agent
        if server_account not in tool_url:
            self.errors.append(f"Tool URL account '{tool_url}' doesn't match server account '{server_account}'")
            return False
        
        if server_project not in tool_url:
            self.errors.append(f"Tool URL project '{tool_url}' doesn't match server project '{server_project}'")
            return False
        
        if server_agent not in tool_url:
            self.errors.append(f"Tool URL agent '{tool_url}' doesn't match server agent '{server_agent}'")
            return False
        
        self.info.append(f"✓ URL consistency verified - Account: {server_account}, Project: {server_project}, Agent: {server_agent}")
        return True
    
    def validate_authentication_config(self, auth_type: str, managed_identity_type: str = "") -> bool:
        """Validate authentication configuration"""
        valid_auth_types = ["Entra", "Azure AD", "Managed Identity", "Service Principal"]
        
        if auth_type not in valid_auth_types:
            self.errors.append(f"Invalid auth type '{auth_type}'. Must be one of: {', '.join(valid_auth_types)}")
            return False
        
        if auth_type in ["Entra", "Azure AD"]:
            if managed_identity_type not in ["Agent Identity", "Project Managed Identity", ""]:
                self.errors.append(f"Invalid managed identity type '{managed_identity_type}'")
                return False
            self.info.append(f"✓ Authentication configured as Entra with {managed_identity_type or 'system-assigned identity'}")
        
        return True
    
    def check_rbac_requirements(self, auth_type: str, identity_type: str) -> None:
        """Provide RBAC requirement guidance"""
        rbac_msg = """
        RBAC Requirements for A2A:
        - If using Project Managed Identity: Must have 'Cognitive Services User' role on sub-agent's project
        - If using Agent Identity: Agent must be assigned a managed identity with appropriate permissions
        - Both agents should be in accessible projects (same subscription recommended)
        - Verify with: az role assignment list --scope /subscriptions/{sub}/resourceGroups/{rg}/providers/Microsoft.CognitiveServices/accounts/{account}
        """
        self.info.append(rbac_msg)
    
    def validate_full_configuration(self, config: Dict) -> bool:
        """Validate entire A2A configuration"""
        print("\n" + "="*80)
        print("FOUNDRY A2A CONFIGURATION VALIDATOR")
        print("="*80 + "\n")
        
        # Extract and validate required fields
        server_url = config.get('server_url', '').strip()
        tool_url = config.get('tool_url', '').strip()
        card_path = config.get('card_path', '').strip()
        auth_type = config.get('auth_type', '').strip()
        identity_type = config.get('identity_type', '').strip()
        
        print("INPUT CONFIGURATION:")
        print(f"  Server URL: {server_url or '(missing)'}")
        print(f"  Tool URL: {tool_url or '(missing)'}")
        print(f"  Card Path: {card_path or '(missing)'}")
        print(f"  Auth Type: {auth_type or '(missing)'}")
        print(f"  Identity Type: {identity_type or '(missing)'}\n")
        
        # Validate each component
        all_valid = True
        
        if not server_url:
            self.errors.append("Server URL is required")
            all_valid = False
        else:
            self.validate_url_format(server_url, "Server URL")
            self.validate_a2a_server_url(server_url)
        
        if not tool_url:
            self.errors.append("Tool URL is required")
            all_valid = False
        else:
            self.validate_url_format(tool_url, "Tool URL")
        
        if not card_path:
            self.errors.append("Card path is required")
            all_valid = False
        else:
            self.validate_card_path(card_path)
        
        if not auth_type:
            self.errors.append("Authentication type is required")
            all_valid = False
        else:
            self.validate_authentication_config(auth_type, identity_type)
        
        # Cross-validation
        if server_url and tool_url and card_path:
            self.compare_urls_consistency(server_url, tool_url, card_path)
            self.check_rbac_requirements(auth_type, identity_type)
        
        # Print results
        print("\n" + "-"*80)
        print("VALIDATION RESULTS")
        print("-"*80)
        
        if self.errors:
            print("\n❌ ERRORS (must fix):")
            for error in self.errors:
                print(f"   • {error}")
            all_valid = False
        else:
            print("\n✅ No configuration errors found")
        
        if self.warnings:
            print("\n⚠️  WARNINGS (review):")
            for warning in self.warnings:
                print(f"   • {warning}")
        
        if self.info:
            print("\nℹ️  INFORMATION:")
            for info in self.info:
                print(f"   • {info}")
        
        print("\n" + "-"*80)
        print("NEXT STEPS:")
        print("-"*80)
        
        if all_valid and not self.warnings:
            print("✅ Configuration looks good! If still experiencing issues:")
            print("   1. Test endpoint accessibility with: curl -H 'Authorization: Bearer <token>' <server_url>")
            print("   2. Verify RBAC roles are assigned correctly")
            print("   3. Check Azure Activity Logs for detailed error information")
            print("   4. Enable Application Insights tracing on both agents")
        elif all_valid:
            print("⚠️  Review warnings above and verify your setup matches expectations")
        else:
            print("❌ Please fix the errors above before attempting A2A communication")
        
        print("\n" + "="*80 + "\n")
        return all_valid and not self.errors

def get_user_config() -> Dict:
    """Interactive configuration input"""
    print("Enter your A2A configuration details (or press Enter to skip validation):\n")
    
    config = {}
    
    config['server_url'] = input("Server URL (sub-agent A2A endpoint): ").strip()
    if not config['server_url']:
        return None
    
    config['tool_url'] = input("Tool URL (as configured in main agent): ").strip()
    config['card_path'] = input("Card Path (e.g., agentCard/v1.0): ").strip()
    config['auth_type'] = input("Auth Type (Entra/Managed Identity/Service Principal): ").strip()
    config['identity_type'] = input("Identity Type (Agent Identity/Project Managed Identity): ").strip()
    
    return config

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--interactive":
        config = get_user_config()
        if config:
            validator = A2AValidator()
            validator.validate_full_configuration(config)
    else:
        print("Foundry A2A Configuration Validator")
        print("Usage: python a2a_validator.py --interactive")
        print("\nExample configuration to validate:")
        
        example_config = {
            'server_url': 'https://myaccount.services.ai.azure.com/api/projects/myproject/agents/subagent/endpoint/protocols/a2a',
            'tool_url': 'https://myaccount.services.ai.azure.com/api/projects/myproject/agents/subagent/endpoint/protocols/a2a',
            'card_path': 'agentCard/v1.0',
            'auth_type': 'Entra',
            'identity_type': 'Project Managed Identity'
        }
        
        validator = A2AValidator()
        validator.validate_full_configuration(example_config)
