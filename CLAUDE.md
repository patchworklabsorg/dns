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

## Important Notes

- Always run dry-run commands before applying changes to preview DNS modifications
- The `--force` flag bypasses safety checks and should be used carefully
- DNS records include critical configurations like DMARC, Google Site Verification, and email routing
- Both domains are owned by Patchwork Labs Inc with similar DNS configurations