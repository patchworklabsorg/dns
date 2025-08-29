---
name: DNS Change Request
about: Request a DNS record change or addition
title: '[DNS] '
labels: dns-change
assignees: ''
---

## Domain
- [ ] patchworklabs.org
- [ ] hackathon.help

## Change Type
- [ ] Add new record
- [ ] Modify existing record
- [ ] Delete record
- [ ] TTL change only

## Record Details
**Record Type:** (A, AAAA, CNAME, MX, TXT, etc.)
**Name:** (subdomain or @ for root)
**Value:** (IP address, domain name, or text value)
**TTL:** (in seconds, see CLAUDE.md for standards)

## Current Record (if modifying/deleting)
```
# Paste current record configuration here
```

## Business Justification
<!-- Why is this change needed? Reference any related projects, services, or requirements -->

## Impact Assessment
- [ ] This change affects email routing
- [ ] This change affects website availability
- [ ] This change affects third-party integrations
- [ ] This is a low-risk change

## Testing Plan
- [ ] I will verify the change using DNS lookup tools
- [ ] I will test affected services after the change
- [ ] This change requires coordination with other teams

## Rollback Plan
<!-- How can this change be reverted if needed? -->

## Additional Context
<!-- Any additional information, screenshots, or references -->