## What does this change?

<!-- One line. For example: add docs.patchworklabs.org for the handbook. -->

## Who owns the records?

<!--
Every record needs an owner in a comment on the same line as its name, so we
know who to ask when it breaks. For example:

    docs: # yourname@patchworklabs.org
      - ttl: 600
        type: CNAME
        value: docs-site.netlify.app.
-->

## Checklist

- [ ] The record is for a Patchwork project, event, or service.
- [ ] Every record I added or changed has an owner in a comment: an email or a
      GitHub handle.
- [ ] `./bin/validate` passes, so the records are in the order octoDNS wants.
- [ ] CNAME values end with a dot. A and AAAA values do not.
- [ ] I have read the `octoDNS plan` comment on this pull request and it
      changes only what I expected.

## Anything else a reviewer should know?

<!-- Delete this section if there is nothing. -->
