# Security

## Reporting a problem

Do not open a public issue for a security problem. Use
[private vulnerability
reporting](https://github.com/patchworklabsorg/dns/security/advisories/new)
instead.

Tell us what you found and how to reproduce it. We will reply within a few
days.

## What matters here

This repository controls DNS for `patchworklabs.org` and `hackathon.help`.
Somebody who can change a record can point a Patchwork name at a host they
control. Treat these
as serious:

- A way to make a workflow run code from a pull request while it holds a
  Cloudflare token.
- A way to merge to `main` without an approving review from a code owner.
- A leaked Cloudflare token.

## How the workflows protect the tokens

`plan.yml` runs on `pull_request_target`, so it can read secrets even for a
pull request from a fork. It only stays safe because of one rule:

> It checks out `main` and runs `main`'s scripts. From the pull request it
> copies only the zone files at the repository root, which are data.

Anything that runs code, an action, or a dependency install from the pull
request breaks that rule and hands the Cloudflare token to whoever opened the
pull request. `validate.yml` is the workflow that runs against pull request
code, and it holds no secrets.

The token used for a plan is read only. Only `deploy.yml`, which runs after a
merge, uses a token that can write.

## If a token leaks

1. Delete the token in the Cloudflare dashboard. This takes effect at once.
2. Create a new one and update the repository secret.
3. Compare Cloudflare against this repository:

   ```console
   $ gh workflow run sync-from-cloudflare.yml
   ```

   Any record an attacker added shows up in the pull request it opens.
4. Check the Cloudflare audit log for what the token did.
