<#
.SYNOPSIS
    Generates Windows Group Policy ADMX/ADML templates for Git Credential Manager.

.DESCRIPTION
    Parses docs/configuration.md to extract all GCM configuration settings and
    generates GitCredentialManager.admx and en-US/GitCredentialManager.adml in
    the same directory as this script.

    Settings, their descriptions, and available values are read directly from
    the documentation so that the templates stay in sync with the docs.

.EXAMPLE
    ./generate-admx.ps1

.EXAMPLE
    ./generate-admx.ps1 -ConfigurationMd ../../../docs/configuration.md
#>

param(
    [string]$ConfigurationMd = (Join-Path $PSScriptRoot '../../../docs/configuration.md'),
    [string]$OutputDir       = $PSScriptRoot
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

# ── Constants ─────────────────────────────────────────────────────────────────

$REGISTRY_KEY   = 'SOFTWARE\GitCredentialManager\Configuration'
$GP_NS          = 'http://schemas.microsoft.com/GroupPolicy/2006/07/PolicyDefinitions'
$XSD_NS         = 'http://www.w3.org/2001/XMLSchema'
$XSI_NS         = 'http://www.w3.org/2001/XMLSchema-instance'
$XMLNS_NS       = 'http://www.w3.org/2000/xmlns/'

# ── Category definitions ──────────────────────────────────────────────────────
# Categories are derived from setting-name prefixes; display names are defined
# here as the only piece of static data in this script.

$categories = @(
    [ordered]@{ Name = 'GitCredentialManager'; Display = 'Git Credential Manager'; Parent = $null }
    [ordered]@{ Name = 'GCM_General';          Display = 'General';                Parent = 'GitCredentialManager' }
    [ordered]@{ Name = 'GCM_Tracing';          Display = 'Tracing';                Parent = 'GitCredentialManager' }
    [ordered]@{ Name = 'GCM_Credentials';      Display = 'Credential Storage';     Parent = 'GitCredentialManager' }
    [ordered]@{ Name = 'GCM_Authentication';   Display = 'Authentication';         Parent = 'GitCredentialManager' }
    [ordered]@{ Name = 'GCM_AzureRepos';       Display = 'Azure Repos';            Parent = 'GitCredentialManager' }
    [ordered]@{ Name = 'GCM_GitHub';           Display = 'GitHub';                 Parent = 'GitCredentialManager' }
    [ordered]@{ Name = 'GCM_Bitbucket';        Display = 'Bitbucket';              Parent = 'GitCredentialManager' }
    [ordered]@{ Name = 'GCM_GitLab';           Display = 'GitLab';                 Parent = 'GitCredentialManager' }
    [ordered]@{ Name = 'GCM_Trace2';           Display = 'Trace2';                 Parent = 'GitCredentialManager' }
)

# ── Markdown helpers ──────────────────────────────────────────────────────────

function ConvertFrom-Markdown {
    <#
    .SYNOPSIS
        Converts markdown text to plain text suitable for ADMX explain strings.
    #>
    param([string]$Text)

    # Remove fenced code blocks
    $t = $Text -replace '(?ms)```[^`]*?```', ''
    # Remove inline code backticks (keep the content)
    $t = $t -replace '`([^`]+)`', '$1'
    # Convert markdown links [text][ref] and [text](url) to just the text
    $t = $t -replace '\[([^\]]+)\]\[[^\]]*\]', '$1'
    $t = $t -replace '\[([^\]]+)\]\([^\)]*\)', '$1'
    # Remove auto-links <url>
    $t = $t -replace '<https?://[^>]+>', ''
    # Unescape only markdown bracket escapes (\[ and \]) that appear in this doc;
    # avoid the general \\(.) pattern which would corrupt Windows path separators.
    $t = $t -replace '\\\[', '['
    $t = $t -replace '\\\]', ']'
    # Remove bold markers (non-greedy to handle adjacent bold spans)
    $t = $t -replace '\*\*(.+?)\*\*', '$1'
    # Remove italic markers *text* and _text_ (non-greedy)
    $t = $t -replace '(?<!\*)\*(.+?)(?<!\*)\*(?!\*)', '$1'
    $t = $t -replace '(?<![_\w])_(.+?)_(?![_\w])', '$1'
    # Remove blockquote markers and GitHub-flavoured alert directives
    $t = $t -replace '(?m)^> ?', ''
    $t = $t -replace '(?m)^\[!(?:NOTE|WARNING|TIP|IMPORTANT|CAUTION)\]\s*$', {
        switch -Regex ($_.Value) {
            'NOTE'      { 'Note:' }
            'WARNING'   { 'Warning:' }
            'IMPORTANT' { 'Important:' }
            'CAUTION'   { 'Caution:' }
            default     { 'Note:' }
        }
    }
    # Convert markdown table separators (keep pipes as column delimiters)
    $t = $t -replace '(?m)^[\-|: ]+$', ''        # Remove separator rows like -|-
    $t = $t -replace '\|', '  '                   # Replace pipes with spaces
    # Normalise line endings and trim trailing whitespace from each line
    $t = ($t -split '\r?\n' | ForEach-Object { $_.TrimEnd() }) -join "`n"
    # Collapse runs of 3+ blank lines to two
    $t = [regex]::Replace($t, '\n{3,}', "`n`n")
    return $t.Trim()
}

function ConvertTo-DisplayName {
    <#
    .SYNOPSIS
        Converts a camelCase setting name to a human-readable title.
    #>
    param([string]$CamelCase)
    # Insert spaces before uppercase letters that follow lowercase letters/digits
    $spaced = [regex]::Replace($CamelCase, '(?<=[a-z0-9])(?=[A-Z])', ' ')
    # Capitalise the first character
    return $spaced.Substring(0, 1).ToUpper() + $spaced.Substring(1)
}

# ── Category assignment ───────────────────────────────────────────────────────

function Get-SettingCategory {
    <#
    .SYNOPSIS
        Assigns a category to a setting based on its value-name prefix pattern.
    #>
    param([string]$ValueName, [string]$Namespace)

    if ($Namespace -eq 'trace2')              { return 'GCM_Trace2' }
    if ($ValueName -match '^trace')           { return 'GCM_Tracing' }
    if ($ValueName -match '^msauth')          { return 'GCM_Authentication' }
    if ($ValueName -match '^azrepos')         { return 'GCM_AzureRepos' }
    if ($ValueName -match '^github')          { return 'GCM_GitHub' }
    if ($ValueName -match '^bitbucket')       { return 'GCM_Bitbucket' }
    if ($ValueName -match '^gitlab')          { return 'GCM_GitLab' }
    if ($ValueName -match 'Store(Path)?$|^cacheOptions$') { return 'GCM_Credentials' }
    return 'GCM_General'
}

# ── Parse configuration.md ───────────────────────────────────────────────────

$content = Get-Content -LiteralPath $ConfigurationMd -Raw

$settings = [System.Collections.Generic.List[hashtable]]::new()

# Setting sections are delimited by '---' horizontal rules
foreach ($section in ($content -split '\n---\n')) {

    # Only process sections that contain a credential.* or trace2.* heading.
    # The heading format is: ### namespace.valueName [_(optional annotation)_]
    if ($section -notmatch '(?m)^### ((?:credential|trace2)\.(\S+?))(?:\s+_\([^)]+\)_)*\s*$') {
        continue
    }

    $fullKey    = $Matches[1]   # e.g. credential.interactive
    $valueName  = $Matches[2]   # e.g. interactive
    $namespace  = ($fullKey -split '\.')[0]   # credential | trace2
    $deprecated = $section -match '_\(deprecated\)_'

    # Extract the description body: everything between the heading line and the
    # first level-4 subheading (#### Example, #### Compatibility, etc.)
    $descBody = ''
    if ($section -match '(?ms)^### [^\n]+\n\n(.*?)(?=\n####|\Z)') {
        $descBody = $Matches[1]
    }

    $explainText = ConvertFrom-Markdown $descBody
    if ($explainText) {
        $explainText += "`n`nCorresponds to git config key: $fullKey"
    } else {
        $explainText = "Corresponds to git config key: $fullKey"
    }
    if ($deprecated) {
        $explainText = "DEPRECATED. $explainText"
    }

    # Unique XML policy name; prefix trace2 settings to avoid collisions
    $policyName = if ($namespace -eq 'trace2') {
        "GCM_trace2_$($valueName -replace '[^A-Za-z0-9]', '_')"
    } else {
        "GCM_$($valueName -replace '[^A-Za-z0-9]', '_')"
    }

    $settings.Add(@{
        PolicyName  = $policyName
        FullKey     = $fullKey
        ValueName   = $valueName
        Namespace   = $namespace
        Category    = (Get-SettingCategory $valueName $namespace)
        DisplayName = (ConvertTo-DisplayName $valueName)
        Explain     = $explainText
        Deprecated  = $deprecated
    })
}

Write-Host "Parsed $($settings.Count) settings from $(Split-Path $ConfigurationMd -Leaf)"

# ── XML writer factory ────────────────────────────────────────────────────────

function New-XmlWriter {
    param([string]$Path)
    $xs = [System.Xml.XmlWriterSettings]::new()
    $xs.Indent          = $true
    $xs.IndentChars     = '  '
    $xs.Encoding        = [System.Text.UTF8Encoding]::new($false)  # UTF-8, no BOM
    $xs.NewLineHandling = [System.Xml.NewLineHandling]::Replace
    return [System.Xml.XmlWriter]::Create($Path, $xs)
}

# ── Generate ADMX ─────────────────────────────────────────────────────────────

$admxPath = Join-Path $OutputDir 'GitCredentialManager.admx'
$xw = New-XmlWriter $admxPath

$xw.WriteStartDocument()
$xw.WriteStartElement('policyDefinitions', $GP_NS)
$xw.WriteAttributeString('xmlns', 'xsd', $XMLNS_NS, $XSD_NS)
$xw.WriteAttributeString('xmlns', 'xsi', $XMLNS_NS, $XSI_NS)
$xw.WriteAttributeString('revision', '1.0')
$xw.WriteAttributeString('schemaVersion', '1.0')

# policyNamespaces
$xw.WriteStartElement('policyNamespaces')
  $xw.WriteStartElement('target')
  $xw.WriteAttributeString('prefix', 'GCM')
  $xw.WriteAttributeString('namespace', 'Git.Policies.GitCredentialManager')
  $xw.WriteEndElement()
  $xw.WriteStartElement('using')
  $xw.WriteAttributeString('prefix', 'windows')
  $xw.WriteAttributeString('namespace', 'Microsoft.Policies.Windows')
  $xw.WriteEndElement()
$xw.WriteEndElement()

# supersededAdm / resources
$xw.WriteStartElement('supersededAdm')
$xw.WriteAttributeString('fileName', '')
$xw.WriteEndElement()
$xw.WriteStartElement('resources')
$xw.WriteAttributeString('minRequiredRevision', '1.0')
$xw.WriteEndElement()

# supportedOn
$xw.WriteStartElement('supportedOn')
  $xw.WriteStartElement('definitions')
    $xw.WriteStartElement('definition')
    $xw.WriteAttributeString('name', 'SUPPORTED_GCM')
    $xw.WriteAttributeString('displayName', '$(string.SUPPORTED_GCM)')
    $xw.WriteEndElement()
  $xw.WriteEndElement()
$xw.WriteEndElement()

# categories
$xw.WriteStartElement('categories')
foreach ($cat in $categories) {
    $xw.WriteStartElement('category')
    $xw.WriteAttributeString('name', $cat.Name)
    $xw.WriteAttributeString('displayName', "`$(string.Cat_$($cat.Name))")
    if ($cat.Parent) {
        $xw.WriteStartElement('parentCategory')
        $xw.WriteAttributeString('ref', $cat.Parent)
        $xw.WriteEndElement()
    }
    $xw.WriteEndElement()
}
$xw.WriteEndElement()

# policies (one text policy per setting)
$xw.WriteStartElement('policies')
foreach ($s in $settings) {
    $xw.WriteStartElement('policy')
    $xw.WriteAttributeString('name', $s.PolicyName)
    $xw.WriteAttributeString('class', 'Machine')
    $xw.WriteAttributeString('displayName', "`$(string.$($s.PolicyName))")
    $xw.WriteAttributeString('explainText', "`$(string.$($s.PolicyName)_Explain)")
    $xw.WriteAttributeString('key', $REGISTRY_KEY)
    $xw.WriteAttributeString('valueName', $s.ValueName)

    $xw.WriteStartElement('parentCategory')
    $xw.WriteAttributeString('ref', $s.Category)
    $xw.WriteEndElement()

    $xw.WriteStartElement('supportedOn')
    $xw.WriteAttributeString('ref', 'SUPPORTED_GCM')
    $xw.WriteEndElement()

    $xw.WriteStartElement('elements')
      $xw.WriteStartElement('text')
      $xw.WriteAttributeString('id', "$($s.PolicyName)_Text")
      $xw.WriteAttributeString('valueName', $s.ValueName)
      $xw.WriteEndElement()
    $xw.WriteEndElement()

    $xw.WriteEndElement()   # policy
}
$xw.WriteEndElement()       # policies

$xw.WriteEndElement()       # policyDefinitions
$xw.WriteEndDocument()
$xw.Flush()
$xw.Close()

Write-Host "Written: $admxPath"

# ── Generate ADML ─────────────────────────────────────────────────────────────

$enUsDir = Join-Path $OutputDir 'en-US'
if (-not (Test-Path $enUsDir)) { New-Item -ItemType Directory -Path $enUsDir | Out-Null }
$admlPath = Join-Path $enUsDir 'GitCredentialManager.adml'

$xw = New-XmlWriter $admlPath

$xw.WriteStartDocument()
$xw.WriteStartElement('policyDefinitionResources', $GP_NS)
$xw.WriteAttributeString('xmlns', 'xsd', $XMLNS_NS, $XSD_NS)
$xw.WriteAttributeString('xmlns', 'xsi', $XMLNS_NS, $XSI_NS)
$xw.WriteAttributeString('revision', '1.0')
$xw.WriteAttributeString('schemaVersion', '1.0')

$xw.WriteElementString('displayName', 'Git Credential Manager Policy Settings')
$xw.WriteElementString('description', 'Group Policy settings for Git Credential Manager.')

$xw.WriteStartElement('resources')
$xw.WriteStartElement('stringTable')

function Write-AdmlString {
    param($Writer, [string]$Id, [string]$Value)
    $Writer.WriteStartElement('string')
    $Writer.WriteAttributeString('id', $Id)
    $Writer.WriteString($Value)
    $Writer.WriteEndElement()
}

Write-AdmlString $xw 'SUPPORTED_GCM' 'Git Credential Manager (any version)'

foreach ($cat in $categories) {
    Write-AdmlString $xw "Cat_$($cat.Name)" $cat.Display
}

foreach ($s in $settings) {
    Write-AdmlString $xw $s.PolicyName $s.DisplayName
    Write-AdmlString $xw "$($s.PolicyName)_Explain" $s.Explain
}

$xw.WriteEndElement()   # stringTable
$xw.WriteEndElement()   # resources
$xw.WriteEndElement()   # policyDefinitionResources
$xw.WriteEndDocument()
$xw.Flush()
$xw.Close()

Write-Host "Written: $admlPath"
Write-Host ""
Write-Host "Done. Generated $($settings.Count) policy settings."
