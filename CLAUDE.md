# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a DNS management repository using OctoDNS to manage DNS records for two domains:
- `patchworklabs.org`
- `hackathon.help`

The repository uses OctoDNS with Hetzner as the DNS provider and YAML configuration files to define DNS records declaratively.

## Architecture

- **Configuration**: `config/main.yaml` defines providers and zone mappings
- **DNS Records**: Domain-specific YAML files (`patchworklabs.org.yaml`, `hackathon.help.yaml`) contain DNS record definitions
- **Scripts**: Shell scripts in `bin/` directory handle DNS operations
- **Dependencies**: Python dependencies managed via `requirements.txt` with OctoDNS ecosystem

## Essential Commands

### DNS Operations
- **Dry run (preview changes)**: `./bin/dry-run`
- **Dry run with force**: `./bin/dry-run-force`
- **Apply DNS changes**: `./bin/sync`
- **Apply DNS changes with force**: `./bin/sync-force`

### Environment Setup
```bash
pip install -r requirements.txt
export HETZNER_KEY=your_hetzner_api_key
```

## Configuration Structure

- **Provider Config**: Hetzner DNS provider configured in `config/main.yaml` with API token from `HETZNER_KEY` environment variable
- **Zone Sources**: Both domains use YAML provider as source and Hetzner as target
- **DNS Records**: Defined in domain-specific YAML files with standard DNS record types (MX, TXT, CNAME, etc.)

## TTL Management Standards

Use appropriate TTL values based on record type and change frequency:

- **A/AAAA Records**: 300 seconds (5 minutes) for frequently changing IPs, 3600 seconds (1 hour) for stable services
- **CNAME Records**: 3600 seconds (1 hour) standard, 300 seconds for testing/development
- **MX Records**: 3600 seconds (1 hour) - email routing should be stable
- **TXT Records**: 
  - Verification records (Google, etc.): 86400 seconds (24 hours) - rarely change
  - SPF/DMARC: 3600 seconds (1 hour) - may need adjustments
  - General purpose: 3600 seconds (1 hour)
- **NS Records**: 86400 seconds (24 hours) - nameservers change infrequently

### TTL Guidelines
- Lower TTLs (300-900s) for records under active development or testing
- Higher TTLs (3600-86400s) for stable, production records
- Always consider propagation time vs. flexibility trade-offs
- Document TTL choices for critical records with inline comments

## Documentation Standards

### YAML File Documentation
- Add comments above critical record groups explaining their purpose
- Document any non-standard configurations or complex setups
- Include references to external services (Google Workspace, email providers)
- Use consistent formatting and indentation

### Change Documentation
- All DNS changes should include clear commit messages explaining the business purpose
- Reference related tickets, issues, or requests in commit messages
- Document TTL changes and reasoning in commit messages

### Record Comments Format
```yaml
# Google Workspace email routing - DO NOT MODIFY without IT approval
mx:
  values:
    - exchange: mx1.example.com
      priority: 10
  ttl: 3600
```

## Important Notes

- Always run dry-run commands before applying changes to preview DNS modifications
- The `--force` flag bypasses safety checks and should be used carefully
- DNS records include critical configurations like DMARC, Google Site Verification, and email routing
- Both domains are owned by Patchwork Labs Inc with similar DNS configurations