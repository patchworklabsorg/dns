# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a DNS management repository using OctoDNS to manage DNS records for `patchworklabs.org`.

The repository uses OctoDNS with Cloudflare as the DNS provider and YAML configuration files to define DNS records declaratively. The setup mirrors `WITCodingClub/dns`. `README.md`, `CONTRIBUTING.md` and `docs/runbook.md` are the full reference.

## Architecture

- **Configuration**: `config/config.yaml` defines providers, processors and zone mappings. `enforce_order` with `order_mode: natural` is on.
- **DNS Records**: The zone file `patchworklabs.org.yaml` contains DNS record definitions. Every record needs an owner (an email, a Patchwork id such as `PWL7A1CE1F3CB`, or both; a GitHub team for team-owned records) in a comment on the same line as its name.
- **Scripts**: Shell scripts in `bin/` handle DNS operations. They read the zone list from `config/config.yaml` through `bin/zones`.
- **Tools**: `tools/merge_live.py` merges live Cloudflare state back into the zone files and keeps comments. `tools/check_zones.py` checks the repository rules (owner comment on every record, TTL of 120 or more, no apex NS, no `octodns-meta`, proxy only on A/AAAA/CNAME). `./bin/validate` runs it. Tests are in `tools/test_*.py`.
- **Workflows**: `validate` (no secrets), `plan` (`pull_request_target`, posts the plan and checks drift), `deploy` (push to `main`), `sync-from-cloudflare` (nightly).
- **Dependencies**: Python dependencies pinned in `requirements.txt`.

## Essential Commands

### DNS Operations
- **Validate (no token needed)**: `./bin/validate`
- **List zones**: `./bin/zones`
- **Plan (preview changes)**: `./bin/plan` (`./bin/dry-run` is an alias)
- **Dump live Cloudflare state**: `./bin/dump .live`
- **Apply DNS changes**: `./bin/sync`. Only the `deploy` workflow should run it.
- **Run tool tests**: `python -m unittest discover -s tools -p 'test_*.py' -v`

### Environment Setup
```bash
python3 -m venv env
./env/bin/pip install -r requirements.txt
export CLOUDFLARE_TOKEN=YOUR_READ_ONLY_TOKEN_HERE
```

## Configuration Structure

- **Provider Config**: Cloudflare provider configured in `config/config.yaml` with API token from the `CLOUDFLARE_TOKEN` environment variable
- **Zone Sources**: The zone uses the YAML provider as source and Cloudflare as target
- **Meta record**: The `meta` processor writes an `octodns-meta` TXT record on each deploy. Do not add it to a zone file.
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
"": # @patchworklabsorg/infra
  ttl: 3600
  type: MX
  values:
    - exchange: mx1.example.com.
      preference: 10
```

## Important Notes

- Always run `./bin/plan` before applying changes to preview DNS modifications
- Never change DNS in the Cloudflare dashboard. Use a pull request. The nightly sync opens a `cloudflare-sync` pull request for any dashboard change.
- The `--force` flag bypasses safety checks and should be used carefully
- DNS records include critical configurations like DMARC, Google Site Verification, and email routing
- The domain is owned by Patchwork Labs Inc