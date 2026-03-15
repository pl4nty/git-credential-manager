#!/usr/bin/env python3
"""
Generate Windows Group Policy ADMX/ADML files for Git Credential Manager.

This script generates ADMX and ADML files that can be used by system
administrators to configure Git Credential Manager via Windows Group Policy.

The generated files should be placed in:
  ADMX: %SystemRoot%\\PolicyDefinitions\\GitCredentialManager.admx
  ADML: %SystemRoot%\\PolicyDefinitions\\en-US\\GitCredentialManager.adml

Or for domain-wide deployment:
  ADMX: \\\\<domain>\\SYSVOL\\<domain>\\Policies\\PolicyDefinitions\\GitCredentialManager.admx
  ADML: \\\\<domain>\\SYSVOL\\<domain>\\Policies\\PolicyDefinitions\\en-US\\GitCredentialManager.adml

Settings are derived from:
  - docs/configuration.md
  - docs/enterprise-config.md

Registry key path used by GCM for enterprise defaults:
  HKEY_LOCAL_MACHINE\\SOFTWARE\\GitCredentialManager\\Configuration
"""

import os
import sys
from xml.dom import minidom
import xml.etree.ElementTree as ET

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

REGISTRY_KEY = r"SOFTWARE\GitCredentialManager\Configuration"

# Category definitions – name, display string ID, optional parent name
CATEGORIES = [
    {
        "name": "GitCredentialManager",
        "displayName": "$(string.Cat_GitCredentialManager)",
    },
    {
        "name": "GCM_General",
        "displayName": "$(string.Cat_General)",
        "parent": "GitCredentialManager",
    },
    {
        "name": "GCM_Tracing",
        "displayName": "$(string.Cat_Tracing)",
        "parent": "GitCredentialManager",
    },
    {
        "name": "GCM_Credentials",
        "displayName": "$(string.Cat_Credentials)",
        "parent": "GitCredentialManager",
    },
    {
        "name": "GCM_Authentication",
        "displayName": "$(string.Cat_Authentication)",
        "parent": "GitCredentialManager",
    },
    {
        "name": "GCM_AzureRepos",
        "displayName": "$(string.Cat_AzureRepos)",
        "parent": "GitCredentialManager",
    },
    {
        "name": "GCM_GitHub",
        "displayName": "$(string.Cat_GitHub)",
        "parent": "GitCredentialManager",
    },
    {
        "name": "GCM_Bitbucket",
        "displayName": "$(string.Cat_Bitbucket)",
        "parent": "GitCredentialManager",
    },
    {
        "name": "GCM_GitLab",
        "displayName": "$(string.Cat_GitLab)",
        "parent": "GitCredentialManager",
    },
]

# Policy (setting) definitions.
#
# Fields:
#   name        – unique policy name (used as XML id)
#   valueName   – registry value name (same as the git config key suffix)
#   category    – parent category name
#   displayName – short human-readable name (string ID prefix)
#   explain     – longer description shown in Group Policy editor
#   type        – "text" | "decimal" | "bool" | "enum"
#   values      – (enum only) list of (registryValue, displayStringId) tuples
SETTINGS = [
    # ------------------------------------------------------------------
    # General
    # ------------------------------------------------------------------
    {
        "name": "GCM_Interactive",
        "valueName": "interactive",
        "category": "GCM_General",
        "displayName": "Interactive prompt mode",
        "explain": (
            "Permit or disable GCM from interacting with the user (showing GUI or TTY "
            "prompts). If interaction is required but has been disabled, an error is "
            "returned.\n\n"
            "This can be helpful when using GCM in headless and unattended environments, "
            "such as build servers, where it would be preferable to fail than to hang "
            "indefinitely waiting for a non-existent user.\n\n"
            "Corresponds to the git config key: credential.interactive\n\n"
            "Defaults to auto (enabled)."
        ),
        "type": "enum",
        "values": [
            ("auto", "Auto – prompt if required (default)"),
            ("true", "True – prompt if required (same as auto)"),
            ("false", "False – never prompt; fail if interaction is required"),
        ],
    },
    {
        "name": "GCM_Provider",
        "valueName": "provider",
        "category": "GCM_General",
        "displayName": "Host provider",
        "explain": (
            "Define the host provider to use when authenticating.\n\n"
            "Automatic provider selection is based on the remote URL. This setting is "
            "typically used with a scoped URL to map a particular set of remote URLs to "
            "providers, for example to mark a host as a GitHub Enterprise instance.\n\n"
            "Corresponds to the git config key: credential.provider\n\n"
            "Defaults to auto."
        ),
        "type": "enum",
        "values": [
            ("auto", "Auto – automatic detection (default)"),
            ("azure-repos", "Azure Repos"),
            ("github", "GitHub"),
            ("bitbucket", "Bitbucket"),
            ("gitlab", "GitLab"),
            ("generic", "Generic"),
        ],
    },
    {
        "name": "GCM_GuiPrompt",
        "valueName": "guiPrompt",
        "category": "GCM_General",
        "displayName": "GUI prompt",
        "explain": (
            "Permit or disable GCM from presenting GUI prompts. If an equivalent "
            "terminal/text-based prompt is available that will be shown instead.\n\n"
            "To disable all interactivity see the Interactive prompt mode policy.\n\n"
            "Corresponds to the git config key: credential.guiPrompt\n\n"
            "Defaults to enabled (true)."
        ),
        "type": "bool",
    },
    {
        "name": "GCM_GuiSoftwareRendering",
        "valueName": "guiSoftwareRendering",
        "category": "GCM_General",
        "displayName": "GUI software rendering",
        "explain": (
            "Force the use of software rendering for GUI prompts. This is currently only "
            "applicable on Windows.\n\n"
            "Note: Windows on ARM devices defaults to using software rendering to work "
            "around a known Avalonia issue.\n\n"
            "Corresponds to the git config key: credential.guiSoftwareRendering\n\n"
            "Defaults to false (use hardware acceleration where available)."
        ),
        "type": "bool",
    },
    {
        "name": "GCM_AllowUnsafeRemotes",
        "valueName": "allowUnsafeRemotes",
        "category": "GCM_General",
        "displayName": "Allow unsafe remote URLs",
        "explain": (
            "Allow transmitting credentials to unsafe remote URLs such as unencrypted "
            "HTTP URLs. This setting is not recommended for general use and should only "
            "be used when necessary.\n\n"
            "Corresponds to the git config key: credential.allowUnsafeRemotes\n\n"
            "Defaults to false (disallow unsafe remote URLs)."
        ),
        "type": "bool",
    },
    {
        "name": "GCM_AutoDetectTimeout",
        "valueName": "autoDetectTimeout",
        "category": "GCM_General",
        "displayName": "Auto-detect timeout (ms)",
        "explain": (
            "Set the maximum length of time, in milliseconds, that GCM should wait for a "
            "network response during host provider auto-detection probing.\n\n"
            "Use a negative or zero value to disable probing altogether.\n\n"
            "Corresponds to the git config key: credential.autoDetectTimeout\n\n"
            "Defaults to 2000 milliseconds (2 seconds)."
        ),
        "type": "text",
    },
    {
        "name": "GCM_AllowWindowsAuth",
        "valueName": "allowWindowsAuth",
        "category": "GCM_General",
        "displayName": "Allow Windows Integrated Authentication",
        "explain": (
            "Allow detection of Windows Integrated Authentication (WIA) support for "
            "generic host providers. Setting this value to false will prevent the use of "
            "WIA and force a basic authentication prompt when using the Generic host "
            "provider.\n\n"
            "Note: WIA is only supported on Windows. WIA is an umbrella term for NTLM "
            "and Kerberos (and Negotiate).\n\n"
            "Corresponds to the git config key: credential.allowWindowsAuth\n\n"
            "Defaults to true (permitted)."
        ),
        "type": "bool",
    },
    {
        "name": "GCM_Namespace",
        "valueName": "namespace",
        "category": "GCM_General",
        "displayName": "Credential namespace",
        "explain": (
            "Use a custom namespace prefix for credentials read and written in the OS "
            "credential store. Credentials will be stored in the format "
            "{namespace}:{service}.\n\n"
            "Corresponds to the git config key: credential.namespace\n\n"
            'Defaults to "git".'
        ),
        "type": "text",
    },
    {
        "name": "GCM_UseHttpPath",
        "valueName": "useHttpPath",
        "category": "GCM_General",
        "displayName": "Use full HTTP path for credentials",
        "explain": (
            "Tells Git to pass the entire repository URL, rather than just the hostname, "
            "when calling out to a credential provider.\n\n"
            "Note: GCM sets this value to true for dev.azure.com (Azure Repos) hosts "
            "after installation by default.\n\n"
            "Corresponds to the git config key: credential.useHttpPath\n\n"
            "Defaults to false."
        ),
        "type": "bool",
    },
    # ------------------------------------------------------------------
    # Tracing
    # ------------------------------------------------------------------
    {
        "name": "GCM_Trace",
        "valueName": "trace",
        "category": "GCM_Tracing",
        "displayName": "Trace logging",
        "explain": (
            "Enables trace logging of all activities.\n\n"
            "If the value is a full path to a file in an existing directory, logs are "
            'appended to the file. If the value is "true" or "1", logs are written to '
            "standard error.\n\n"
            "Corresponds to the git config key: credential.trace\n\n"
            "Defaults to disabled."
        ),
        "type": "text",
    },
    {
        "name": "GCM_TraceSecrets",
        "valueName": "traceSecrets",
        "category": "GCM_Tracing",
        "displayName": "Trace secrets",
        "explain": (
            "Enables tracing of secret and sensitive information, which is by default "
            "masked in trace output. Requires that trace logging is also enabled.\n\n"
            "Corresponds to the git config key: credential.traceSecrets\n\n"
            "Defaults to disabled (false)."
        ),
        "type": "bool",
    },
    {
        "name": "GCM_TraceMsAuth",
        "valueName": "traceMsAuth",
        "category": "GCM_Tracing",
        "displayName": "Trace Microsoft Authentication library",
        "explain": (
            "Enables inclusion of Microsoft Authentication library (MSAL) logs in GCM "
            "trace output. Requires that trace logging is also enabled.\n\n"
            "Corresponds to the git config key: credential.traceMsAuth\n\n"
            "Defaults to disabled (false)."
        ),
        "type": "bool",
    },
    {
        "name": "GCM_Debug",
        "valueName": "debug",
        "category": "GCM_Tracing",
        "displayName": "Debug mode",
        "explain": (
            "Pauses execution of GCM at launch to wait for a debugger to be attached.\n\n"
            "Corresponds to the git config key: credential.debug\n\n"
            "Defaults to disabled (false)."
        ),
        "type": "bool",
    },
    # ------------------------------------------------------------------
    # Credential storage
    # ------------------------------------------------------------------
    {
        "name": "GCM_CredentialStore",
        "valueName": "credentialStore",
        "category": "GCM_Credentials",
        "displayName": "Credential store",
        "explain": (
            "Select the type of credential store to use on supported platforms.\n\n"
            "Available values:\n"
            "  wincredman   – Windows Credential Manager (Windows only, not available over SSH)\n"
            "  dpapi        – DPAPI protected files (Windows only)\n"
            "  keychain     – macOS Keychain (macOS only)\n"
            "  secretservice– freedesktop.org Secret Service API via libsecret (Linux only)\n"
            "  gpg          – GPG encrypted files compatible with pass (macOS, Linux)\n"
            "  cache        – Git's built-in credential cache (macOS, Linux)\n"
            "  plaintext    – Store credentials in plaintext files (UNSECURE; all platforms)\n"
            "  none         – Do not store credentials via GCM (all platforms)\n\n"
            "Corresponds to the git config key: credential.credentialStore\n\n"
            "Default: wincredman on Windows, keychain on macOS, unset on Linux."
        ),
        "type": "enum",
        "values": [
            ("wincredman", "Windows Credential Manager (default on Windows)"),
            ("dpapi", "DPAPI protected files (Windows only)"),
            ("keychain", "macOS Keychain (macOS only)"),
            ("secretservice", "Secret Service API via libsecret (Linux only)"),
            ("gpg", "GPG encrypted files / pass (macOS, Linux)"),
            ("cache", "Git's built-in credential cache (macOS, Linux)"),
            ("plaintext", "Plaintext files (UNSECURE; all platforms)"),
            ("none", "Do not store credentials"),
        ],
    },
    {
        "name": "GCM_CacheOptions",
        "valueName": "cacheOptions",
        "category": "GCM_Credentials",
        "displayName": "Credential cache options",
        "explain": (
            'Pass options to the Git credential cache when credential store is set to "cache". '
            "This allows you to select a different amount of time to cache credentials "
            '(the default is 900 seconds) by passing "--timeout <seconds>".\n\n'
            "Corresponds to the git config key: credential.cacheOptions\n\n"
            "Defaults to empty."
        ),
        "type": "text",
    },
    {
        "name": "GCM_PlaintextStorePath",
        "valueName": "plaintextStorePath",
        "category": "GCM_Credentials",
        "displayName": "Plaintext credential store path",
        "explain": (
            'Specify a custom directory to store plaintext credential files in when credential store is set to "plaintext".\n\n'
            "Corresponds to the git config key: credential.plaintextStorePath\n\n"
            r"Defaults to %USERPROFILE%\.gcm\store on Windows."
        ),
        "type": "text",
    },
    {
        "name": "GCM_DpapiStorePath",
        "valueName": "dpapiStorePath",
        "category": "GCM_Credentials",
        "displayName": "DPAPI credential store path",
        "explain": (
            'Specify a custom directory to store DPAPI protected credential files in when credential store is set to "dpapi".\n\n'
            "Corresponds to the git config key: credential.dpapiStorePath\n\n"
            r"Defaults to %USERPROFILE%\.gcm\dpapi_store on Windows."
        ),
        "type": "text",
    },
    {
        "name": "GCM_GpgPassStorePath",
        "valueName": "gpgPassStorePath",
        "category": "GCM_Credentials",
        "displayName": "GPG pass credential store path",
        "explain": (
            "Specify a custom directory to store GPG-encrypted pass-compatible credential "
            'files in when credential store is set to "gpg".\n\n'
            "Corresponds to the git config key: credential.gpgPassStorePath\n\n"
            r"Defaults to ~/.password-store or %USERPROFILE%\.password-store."
        ),
        "type": "text",
    },
    # ------------------------------------------------------------------
    # Authentication (Microsoft)
    # ------------------------------------------------------------------
    {
        "name": "GCM_MsauthFlow",
        "valueName": "msauthFlow",
        "category": "GCM_Authentication",
        "displayName": "Microsoft authentication flow",
        "explain": (
            "Specify which authentication flow should be used when performing Microsoft "
            "authentication and an interactive flow is required.\n\n"
            "Note: If msauthUseBroker is set to true and the operating system "
            "authentication broker is available, all flows will be delegated to the "
            "broker and this value has no effect.\n\n"
            "Corresponds to the git config key: credential.msauthFlow\n\n"
            "Defaults to auto."
        ),
        "type": "enum",
        "values": [
            ("auto", "Auto – select best option for current environment (default)"),
            ("embedded", "Embedded web view"),
            ("system", "System – open user's default web browser"),
            ("devicecode", "Device code"),
        ],
    },
    {
        "name": "GCM_MsauthUseBroker",
        "valueName": "msauthUseBroker",
        "category": "GCM_Authentication",
        "displayName": "Use OS authentication broker (experimental)",
        "explain": (
            "Use the operating system account manager where available.\n\n"
            "Note: Before enabling this option on Windows, review the Windows Broker "
            "details for what this means to your local Windows user account.\n\n"
            "Corresponds to the git config key: credential.msauthUseBroker\n\n"
            "Defaults to false. In certain cloud hosted environments when using a work or "
            "school account (such as Microsoft DevBox), the default is true."
        ),
        "type": "bool",
    },
    {
        "name": "GCM_MsauthUseDefaultAccount",
        "valueName": "msauthUseDefaultAccount",
        "category": "GCM_Authentication",
        "displayName": "Use OS default account (experimental)",
        "explain": (
            "Use the current operating system account by default when the broker is "
            "enabled.\n\n"
            "Corresponds to the git config key: credential.msauthUseDefaultAccount\n\n"
            "Defaults to false. In certain cloud hosted environments when using a work or "
            "school account (such as Microsoft DevBox), the default is true."
        ),
        "type": "bool",
    },
    # ------------------------------------------------------------------
    # Azure Repos
    # ------------------------------------------------------------------
    {
        "name": "GCM_AzreposCredentialType",
        "valueName": "azreposCredentialType",
        "category": "GCM_AzureRepos",
        "displayName": "Azure Repos credential type",
        "explain": (
            "Specify the type of credential the Azure Repos host provider should return.\n\n"
            "Corresponds to the git config key: credential.azreposCredentialType\n\n"
            "Defaults to pat (personal access token). In certain cloud hosted environments "
            "when using a work or school account (such as Microsoft DevBox), the default "
            "value is oauth."
        ),
        "type": "enum",
        "values": [
            ("pat", "Personal Access Token (PAT) (default)"),
            ("oauth", "Microsoft identity OAuth tokens (AAD or MSA tokens)"),
        ],
    },
    {
        "name": "GCM_AzreposManagedIdentity",
        "valueName": "azreposManagedIdentity",
        "category": "GCM_AzureRepos",
        "displayName": "Azure Repos Managed Identity",
        "explain": (
            "Use a Managed Identity to authenticate with Azure Repos.\n\n"
            'The value "system" uses the system-assigned Managed Identity.\n\n'
            'To specify a user-assigned Managed Identity use the format "id://{clientId}" '
            "where {clientId} is the client ID of the Managed Identity.\n\n"
            'To specify a Managed Identity associated with an Azure resource use '
            '"resource://{resourceId}" where {resourceId} is the resource ID.\n\n'
            "Corresponds to the git config key: credential.azreposManagedIdentity"
        ),
        "type": "text",
    },
    {
        "name": "GCM_AzreposServicePrincipal",
        "valueName": "azreposServicePrincipal",
        "category": "GCM_AzureRepos",
        "displayName": "Azure Repos service principal",
        "explain": (
            "Specify the client and tenant IDs of a service principal to use when "
            "performing Microsoft authentication for Azure Repos.\n\n"
            "The value of this setting should be in the format: {tenantId}/{clientId}.\n\n"
            "You must also configure at least one authentication mechanism: "
            "azreposServicePrincipalSecret or azreposServicePrincipalCertificateThumbprint.\n\n"
            "Corresponds to the git config key: credential.azreposServicePrincipal"
        ),
        "type": "text",
    },
    {
        "name": "GCM_AzreposServicePrincipalSecret",
        "valueName": "azreposServicePrincipalSecret",
        "category": "GCM_AzureRepos",
        "displayName": "Azure Repos service principal secret",
        "explain": (
            "Specifies the client secret for the service principal when performing "
            "Microsoft authentication for Azure Repos with azreposServicePrincipal set.\n\n"
            "Note: Storing secrets in Group Policy is not recommended for security "
            "reasons. Consider using certificate-based authentication instead.\n\n"
            "Corresponds to the git config key: credential.azreposServicePrincipalSecret"
        ),
        "type": "text",
    },
    {
        "name": "GCM_AzreposServicePrincipalCertificateThumbprint",
        "valueName": "azreposServicePrincipalCertificateThumbprint",
        "category": "GCM_AzureRepos",
        "displayName": "Azure Repos service principal certificate thumbprint",
        "explain": (
            "Specifies the thumbprint of a certificate to use when authenticating as a "
            "service principal for Azure Repos when azreposServicePrincipal is set.\n\n"
            "Corresponds to the git config key: "
            "credential.azreposServicePrincipalCertificateThumbprint"
        ),
        "type": "text",
    },
    {
        "name": "GCM_AzreposServicePrincipalCertificateSendX5C",
        "valueName": "azreposServicePrincipalCertificateSendX5C",
        "category": "GCM_AzureRepos",
        "displayName": "Azure Repos service principal certificate send X5C",
        "explain": (
            "When using a certificate for service principal authentication, specifies "
            "whether the X5C claim should be sent to the STS. Sending the x5c enables "
            "easy certificate rollover in Azure AD: the public certificate is sent to "
            "Azure AD along with the token request so that Azure AD can validate the "
            "subject name based on a trusted issuer policy.\n\n"
            "Corresponds to the git config key: "
            "credential.azreposServicePrincipalCertificateSendX5C\n\n"
            "Defaults to false."
        ),
        "type": "bool",
    },
    # ------------------------------------------------------------------
    # GitHub
    # ------------------------------------------------------------------
    {
        "name": "GCM_GitHubAuthModes",
        "valueName": "gitHubAuthModes",
        "category": "GCM_GitHub",
        "displayName": "GitHub authentication modes",
        "explain": (
            "Override the available authentication modes presented during GitHub "
            "authentication. If this option is not set, the available authentication "
            "modes will be automatically detected.\n\n"
            "Multiple values can be specified separated by commas.\n\n"
            "Available values: oauth (expands to browser,device), browser, device, "
            "basic, pat\n\n"
            "Corresponds to the git config key: credential.gitHubAuthModes"
        ),
        "type": "text",
    },
    {
        "name": "GCM_GitHubAccountFiltering",
        "valueName": "gitHubAccountFiltering",
        "category": "GCM_GitHub",
        "displayName": "GitHub account filtering",
        "explain": (
            "Enable or disable automatic account filtering for GitHub based on server "
            "hints when there are multiple available accounts. This setting is only "
            "applicable to GitHub.com with Enterprise Managed Users.\n\n"
            "Corresponds to the git config key: credential.gitHubAccountFiltering\n\n"
            "Defaults to true (filter available accounts based on server hints)."
        ),
        "type": "bool",
    },
    # ------------------------------------------------------------------
    # Bitbucket
    # ------------------------------------------------------------------
    {
        "name": "GCM_BitbucketAuthModes",
        "valueName": "bitbucketAuthModes",
        "category": "GCM_Bitbucket",
        "displayName": "Bitbucket authentication modes",
        "explain": (
            "Override the available authentication modes presented during Bitbucket "
            "authentication. If this option is not set, the available authentication "
            "modes will be automatically detected.\n\n"
            "Note: This setting only applies to Bitbucket.org, not Server or DC "
            "instances.\n\n"
            "Multiple values can be specified separated by commas.\n\n"
            "Available values: oauth, basic\n\n"
            "Corresponds to the git config key: credential.bitbucketAuthModes"
        ),
        "type": "text",
    },
    {
        "name": "GCM_BitbucketAlwaysRefreshCredentials",
        "valueName": "bitbucketAlwaysRefreshCredentials",
        "category": "GCM_Bitbucket",
        "displayName": "Bitbucket always refresh credentials",
        "explain": (
            "Forces GCM to ignore any existing stored Basic Auth or OAuth access tokens "
            "and always run through the process to refresh the credentials before "
            "returning them to Git.\n\n"
            "This is especially relevant to OAuth credentials. Bitbucket.org access "
            "tokens expire after 2 hours, after which the refresh token must be used to "
            "get a new access token.\n\n"
            "Corresponds to the git config key: credential.bitbucketAlwaysRefreshCredentials\n\n"
            "Defaults to false."
        ),
        "type": "bool",
    },
    {
        "name": "GCM_BitbucketValidateStoredCredentials",
        "valueName": "bitbucketValidateStoredCredentials",
        "category": "GCM_Bitbucket",
        "displayName": "Bitbucket validate stored credentials",
        "explain": (
            "Forces GCM to validate any stored credentials before returning them to Git "
            "by calling a REST API resource that requires authentication.\n\n"
            "Corresponds to the git config key: credential.bitbucketValidateStoredCredentials\n\n"
            "Defaults to true (always validate)."
        ),
        "type": "bool",
    },
    {
        "name": "GCM_BitbucketDataCenterOAuthClientId",
        "valueName": "bitbucketDataCenterOAuthClientId",
        "category": "GCM_Bitbucket",
        "displayName": "Bitbucket Data Center OAuth Client ID",
        "explain": (
            "To use OAuth with Bitbucket Data Center it is necessary to create an "
            "external incoming AppLink and configure GCM with both the OAuth Client ID "
            "and Client Secret from the AppLink.\n\n"
            "Corresponds to the git config key: credential.bitbucketDataCenterOAuthClientId\n\n"
            "Defaults to undefined."
        ),
        "type": "text",
    },
    {
        "name": "GCM_BitbucketDataCenterOAuthClientSecret",
        "valueName": "bitbucketDataCenterOAuthClientSecret",
        "category": "GCM_Bitbucket",
        "displayName": "Bitbucket Data Center OAuth Client Secret",
        "explain": (
            "To use OAuth with Bitbucket Data Center it is necessary to create an "
            "external incoming AppLink and configure GCM with both the OAuth Client ID "
            "and Client Secret from the AppLink.\n\n"
            "Note: Storing secrets in Group Policy is not recommended for security "
            "reasons.\n\n"
            "Corresponds to the git config key: credential.bitbucketDataCenterOAuthClientSecret\n\n"
            "Defaults to undefined."
        ),
        "type": "text",
    },
    # ------------------------------------------------------------------
    # GitLab
    # ------------------------------------------------------------------
    {
        "name": "GCM_GitLabAuthModes",
        "valueName": "gitLabAuthModes",
        "category": "GCM_GitLab",
        "displayName": "GitLab authentication modes",
        "explain": (
            "Override the available authentication modes presented during GitLab "
            "authentication. If this option is not set, the available authentication "
            "modes will be automatically detected.\n\n"
            "Multiple values can be specified separated by commas.\n\n"
            "Available values: browser, basic, pat\n\n"
            "Corresponds to the git config key: credential.gitLabAuthModes"
        ),
        "type": "text",
    },
]

# ---------------------------------------------------------------------------
# ADMX generation
# ---------------------------------------------------------------------------

ADMX_XMLNS = "http://schemas.microsoft.com/GroupPolicy/2006/07/PolicyDefinitions"
ADMX_XMLNS_XSD = "http://www.w3.org/2001/XMLSchema"
ADMX_XMLNS_XSI = "http://www.w3.org/2001/XMLSchema-instance"

GCM_NAMESPACE = "Git.Policies.GitCredentialManager"
GCM_PREFIX = "GCM"
WINDOWS_NAMESPACE = "Microsoft.Policies.Windows"
WINDOWS_PREFIX = "windows"


def _pretty(element: ET.Element) -> str:
    """Return a pretty-printed XML string for *element*."""
    raw = ET.tostring(element, encoding="unicode")
    reparsed = minidom.parseString(raw)
    return reparsed.toprettyxml(indent="  ", encoding="utf-8").decode("utf-8")


def build_admx() -> ET.Element:
    """Build and return the root element of the ADMX XML document."""
    root = ET.Element(
        "policyDefinitions",
        attrib={
            "xmlns:xsd": ADMX_XMLNS_XSD,
            "xmlns:xsi": ADMX_XMLNS_XSI,
            "revision": "1.0",
            "schemaVersion": "1.0",
            "xmlns": ADMX_XMLNS,
        },
    )

    # --- policyNamespaces ---
    ns_el = ET.SubElement(root, "policyNamespaces")
    ET.SubElement(
        ns_el,
        "target",
        attrib={"prefix": GCM_PREFIX, "namespace": GCM_NAMESPACE},
    )
    ET.SubElement(
        ns_el,
        "using",
        attrib={"prefix": WINDOWS_PREFIX, "namespace": WINDOWS_NAMESPACE},
    )

    # --- supersededAdm ---
    ET.SubElement(root, "supersededAdm", attrib={"fileName": ""})

    # --- resources ---
    ET.SubElement(root, "resources", attrib={"minRequiredRevision": "1.0"})

    # --- supportedOn ---
    supported_on = ET.SubElement(root, "supportedOn")
    definitions = ET.SubElement(supported_on, "definitions")
    ET.SubElement(
        definitions,
        "definition",
        attrib={
            "name": "SUPPORTED_GCM",
            "displayName": "$(string.SUPPORTED_GCM)",
        },
    )

    # --- categories ---
    categories_el = ET.SubElement(root, "categories")
    for cat in CATEGORIES:
        cat_el = ET.SubElement(
            categories_el,
            "category",
            attrib={"name": cat["name"], "displayName": cat["displayName"]},
        )
        if "parent" in cat:
            ET.SubElement(
                cat_el,
                "parentCategory",
                attrib={"ref": cat["parent"]},
            )

    # --- policies ---
    policies_el = ET.SubElement(root, "policies")
    for setting in SETTINGS:
        _add_policy(policies_el, setting)

    return root


def _add_policy(policies_el: ET.Element, setting: dict) -> None:
    """Append a <policy> element for *setting* to *policies_el*."""
    name = setting["name"]
    value_name = setting["valueName"]
    policy_attrib = {
        "name": name,
        "class": "Machine",
        "displayName": f"$(string.{name})",
        "explainText": f"$(string.{name}_Explain)",
        "key": REGISTRY_KEY,
    }

    stype = setting["type"]

    # Boolean policies use enabledValue/disabledValue; others need valueName
    # at the policy level only when there are no child elements with it.
    if stype != "bool":
        policy_attrib["valueName"] = value_name

    policy_el = ET.SubElement(policies_el, "policy", attrib=policy_attrib)

    ET.SubElement(policy_el, "parentCategory", attrib={"ref": setting["category"]})
    ET.SubElement(policy_el, "supportedOn", attrib={"ref": "SUPPORTED_GCM"})

    if stype == "bool":
        enabled_val = ET.SubElement(policy_el, "enabledValue")
        ET.SubElement(enabled_val, "decimal", attrib={"value": "1"})
        disabled_val = ET.SubElement(policy_el, "disabledValue")
        ET.SubElement(disabled_val, "decimal", attrib={"value": "0"})
        # Boolean policies need the valueName in the policy element itself
        policy_el.set("valueName", value_name)

    elif stype == "text":
        elements_el = ET.SubElement(policy_el, "elements")
        ET.SubElement(
            elements_el,
            "text",
            attrib={"id": f"{name}_Text", "valueName": value_name},
        )

    elif stype == "decimal":
        elements_el = ET.SubElement(policy_el, "elements")
        ET.SubElement(
            elements_el,
            "decimal",
            attrib={"id": f"{name}_Decimal", "valueName": value_name},
        )

    elif stype == "enum":
        elements_el = ET.SubElement(policy_el, "elements")
        enum_el = ET.SubElement(
            elements_el,
            "enum",
            attrib={"id": f"{name}_Enum", "valueName": value_name},
        )
        for reg_value, display_str_id in setting["values"]:
            item_el = ET.SubElement(
                enum_el,
                "item",
                attrib={"displayName": f"$(string.{name}_{_safe_id(reg_value)})"},
            )
            val_el = ET.SubElement(item_el, "value")
            ET.SubElement(val_el, "string").text = reg_value


def _safe_id(value: str) -> str:
    """Convert a registry value string to a safe XML identifier fragment."""
    return value.replace("-", "_").replace(" ", "_")


# ---------------------------------------------------------------------------
# ADML generation
# ---------------------------------------------------------------------------


def build_adml() -> ET.Element:
    """Build and return the root element of the ADML XML document."""
    root = ET.Element(
        "policyDefinitionResources",
        attrib={
            "xmlns:xsd": ADMX_XMLNS_XSD,
            "xmlns:xsi": ADMX_XMLNS_XSI,
            "revision": "1.0",
            "schemaVersion": "1.0",
            "xmlns": ADMX_XMLNS,
        },
    )

    ET.SubElement(root, "displayName").text = "Git Credential Manager Policy Settings"
    ET.SubElement(root, "description").text = (
        "This file contains the Group Policy settings for Git Credential Manager."
    )

    resources_el = ET.SubElement(root, "resources")
    string_table = ET.SubElement(resources_el, "stringTable")

    def s(id_: str, text: str) -> None:
        el = ET.SubElement(string_table, "string", attrib={"id": id_})
        el.text = text

    # Supported-on string
    s("SUPPORTED_GCM", "Git Credential Manager (any version)")

    # Category strings
    cat_display = {
        "Cat_GitCredentialManager": "Git Credential Manager",
        "Cat_General": "General",
        "Cat_Tracing": "Tracing",
        "Cat_Credentials": "Credential Storage",
        "Cat_Authentication": "Authentication",
        "Cat_AzureRepos": "Azure Repos",
        "Cat_GitHub": "GitHub",
        "Cat_Bitbucket": "Bitbucket",
        "Cat_GitLab": "GitLab",
    }
    for id_, text in cat_display.items():
        s(id_, text)

    # Per-setting strings
    for setting in SETTINGS:
        name = setting["name"]
        s(name, setting["displayName"])
        s(f"{name}_Explain", setting["explain"])

        if setting["type"] == "enum":
            for reg_value, display_text in setting["values"]:
                s(f"{name}_{_safe_id(reg_value)}", display_text)

    return root


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> int:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    en_us_dir = os.path.join(script_dir, "en-US")
    os.makedirs(en_us_dir, exist_ok=True)

    admx_path = os.path.join(script_dir, "GitCredentialManager.admx")
    adml_path = os.path.join(en_us_dir, "GitCredentialManager.adml")

    admx_root = build_admx()
    adml_root = build_adml()

    with open(admx_path, "w", encoding="utf-8") as f:
        f.write(_pretty(admx_root))
    print(f"Written: {admx_path}")

    with open(adml_path, "w", encoding="utf-8") as f:
        f.write(_pretty(adml_root))
    print(f"Written: {adml_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
