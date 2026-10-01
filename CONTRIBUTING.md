# Contributing

Thank you for helping run the Patchwork Labs DNS. This file covers the rules. The
[README](./README.md) covers how to add a record.

## For everybody

1. Fork the repository and make your change on a branch.
2. One pull request does one thing. Do not add three unrelated subdomains in
   one pull request.
3. Keep records in order inside a zone file. The `dns records` check enforces
   it. The order is natural, so `ns2` comes before `ns10`, and inside a record
   `octodns` comes before `ttl`, `type` and `value`. Run `./bin/validate`.
4. Give every record an owner in a comment on the same line as its name. Use
   an email, a Patchwork id (`PWL...`), or both. The `dns records` check
   enforces it.
5. Read the `octoDNS plan` comment on your pull request before you ask for a
   review. It is the exact list of changes the merge will make.
6. Answer review comments on the same pull request. Do not close it and open a
   new one.

### Commit messages

Use [Conventional Commits](https://www.conventionalcommits.org/):

```
feat: add docs.patchworklabs.org for the handbook
fix: point api.patchworklabs.org at the new host
chore: bump octodns to 1.14.0
```

Pull requests are squash merged, so the pull request title becomes the commit
message on `main`. Write the title the same way.

## For code owners

You are on the [infra](https://github.com/orgs/patchworklabsorg/teams/infra)
or [dns-frens](https://github.com/orgs/patchworklabsorg/teams/dns-frens) team.
A pull request cannot merge without an approving review from one of you.

### Reviews go to the whole team

`CODEOWNERS` makes both teams required reviewers, so GitHub asks all of you on
every pull request. Whoever gets to it first reviews it.

Nobody is assigned. That means a pull request can sit while each of you assumes
the other has it. If you start a review, say so on the pull request, and if you
cannot get to one, say that too.

To change who reviews, change who is on the teams.

### What to check in a review

- **Read the plan comment.** It is the truth about what merging will do. The
  diff is not. A small diff can produce a large plan.
- **Does the record have an owner?** Reject it if not. An unowned record is one
  nobody can clean up later.
- **Does the name belong to a Patchwork project?** See the README.
- **Does the plan delete anything?** A delete that the author did not mention
  is the most common sign of a mistake or a stale branch.
- **Did the pull request touch `config/`, `bin/`, `.github/` or `tools/`?**
  Those are not in the plan comment. Read them by hand.

Approve, then squash merge. The deploy runs by itself.

### Never change DNS in the Cloudflare dashboard

Use a pull request. A dashboard change is invisible to everybody who is not
looking at the dashboard, and the next deploy would undo it.

The nightly sync catches a dashboard change and opens a pull request for it.
That is a safety net, not a workflow. Treat a `cloudflare-drift` pull request
as a thing to explain, not a thing to rubber stamp.

If you need an emergency change and you cannot wait for a review, make it in
the dashboard, then tell the `infra` team straight away. Merge the sync
pull request the next morning.

## Changing the tooling

`tools/` has tests. Run them and keep them passing:

```console
$ python -m unittest discover -s tools -p 'test_*.py' -v
```

Add a test with any change to `tools/merge_live.py` or `tools/check_zones.py`. That script edits the zone
files by itself every night, so a bug in it is a bug in production DNS.

Never loosen the security note at the top of
[`.github/workflows/plan.yml`](./.github/workflows/plan.yml) without
understanding it. That workflow can read secrets on a pull request from a fork.
