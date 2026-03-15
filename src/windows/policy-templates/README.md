# Git Credential Manager – Group Policy Templates

This directory contains Windows Group Policy Administrative Templates (ADMX/ADML)
for Git Credential Manager (GCM).

These templates allow system administrators to configure GCM defaults for all
users on a machine using Windows Group Policy.

## Files

| File | Description |
|------|-------------|
| `GitCredentialManager.admx` | Policy definition file |
| `en-US/GitCredentialManager.adml` | English language resource file |
| `generate-admx.py` | Python script used to regenerate the above files |

## Deployment

### Local machine

Copy the files to the local policy definitions folder:

```
GitCredentialManager.admx  →  %SystemRoot%\PolicyDefinitions\
en-US\GitCredentialManager.adml  →  %SystemRoot%\PolicyDefinitions\en-US\
```

### Domain (Active Directory)

Copy the files to the domain's central policy store on the SYSVOL share:

```
GitCredentialManager.admx  →  \\<domain>\SYSVOL\<domain>\Policies\PolicyDefinitions\
en-US\GitCredentialManager.adml  →  \\<domain>\SYSVOL\<domain>\Policies\PolicyDefinitions\en-US\
```

After copying the files, open the **Group Policy Management Editor**, navigate to:

```
Computer Configuration
  └─ Administrative Templates
       └─ Git Credential Manager
```

## Registry path

All GCM enterprise defaults set via Group Policy are stored under:

```
HKEY_LOCAL_MACHINE\SOFTWARE\GitCredentialManager\Configuration
```

The setting names and values match those described in the
[Git configuration reference](../../docs/configuration.md).

> **Note:** Values written to this registry key act as *default* values that
> can always be overridden by environment variables or Git configuration files
> set by the user. See [enterprise configuration](../../docs/enterprise-config.md)
> for details.

## Regenerating the templates

If the GCM configuration options change, regenerate the templates by running:

```sh
python3 generate-admx.py
```

Python 3.6 or later is required. No third-party packages are needed.
