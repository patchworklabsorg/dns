#!/usr/bin/env python3
"""Check the zone files for the rules that octoDNS does not know about.

``octodns-validate`` checks that each record is valid DNS. It does not know the
rules of this repository, so this script checks them:

1. Every record has an owner in a comment on the same line as its name. An
   owner is an email address or a Patchwork id, or both, for example
   ``# PWL7A1CE1F3CB / ada@patchworklabs.org``. A record that a team owns can
   name a GitHub team instead, for example ``# @patchworklabsorg/infra``. A
   personal GitHub handle is not an owner. A ``TODO owner unknown`` comment
   from the nightly sync is not an owner.
2. Every TTL is at least the Cloudflare minimum of 120 seconds. A lower value
   is silently raised by Cloudflare, so the zone file would never match it.
3. No zone file holds the apex NS records. Cloudflare owns them.
4. No zone file holds the ``octodns-meta`` record. octoDNS writes it.
5. Only A, AAAA and CNAME records are behind the Cloudflare proxy.
6. Every zone in ``config/config.yaml`` has a zone file, and every YAML file
   at the repository root belongs to a zone.
7. No record name appears twice in one file.
8. Every CAA record names a CA in ``KNOWN_CAS``, uses a known tag and flag,
   and gives ``iodef`` a ``mailto:`` or ``https://`` address. If the apex has
   CAA ``issue`` records, they include ``letsencrypt.org``. A typo such
   as ``letsencrypt.com`` then fails here, not at the next certificate renewal.

Usage:

    python3 tools/check_zones.py [--repo-dir .]

Exits 0 when every file passes and 1 when any rule fails. Each failure is
printed as ``file:line: message``.
"""

import argparse
import re
import sys
from pathlib import Path

import yaml

MIN_TTL = 120
PROXIABLE = {"A", "AAAA", "CNAME"}
META_RECORD = "octodns-meta"
# The CAs that a CAA `issue` or `issuewild` record can name. Add a CA here in
# the same pull request that first allows it in a zone file.
KNOWN_CAS = {
    "letsencrypt.org",  # Vercel, Traefik on alastor, the thimble VPN
    "pki.goog",  # Cloudflare Universal SSL
    "sectigo.com",  # Cloudflare backup certificates
    "ssl.com",  # Cloudflare Universal SSL
}
# Vercel, Traefik on alastor and the thimble VPN get certificates from it, so
# an apex CAA set without it stops their renewals.
REQUIRED_APEX_CA = "letsencrypt.org"
CAA_TAGS = {"issue", "issuewild", "iodef"}
CAA_FLAGS = {0, 128}

# A top level key: `name:`, `"name":` or `'name':`, then an optional comment.
_TOP_LEVEL = re.compile(
    r"""^(?:"(?P<dq>[^"]*)"|'(?P<sq>[^']*)'|(?P<bare>[^\s#"'-][^:#]*?))\s*:"""
    r"""(?:\s+(?P<rest>.*))?$"""
)
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
# A Patchwork id: `PWL` and ten upper case hex digits.
_PWL_ID = re.compile(r"\bPWL[0-9A-F]{10}\b")
# A GitHub team, `@org/team`. A personal handle does not count.
_TEAM = re.compile(r"(?:^|[\s,/])@[A-Za-z0-9][A-Za-z0-9-]*/[\w.-]+")


def _owner_comment(rest):
    """Return the comment on a key line, or None."""
    if not rest:
        return None
    if rest.startswith("#"):
        return rest[1:].strip()
    match = re.search(r"\s#(.*)$", rest)
    return match.group(1).strip() if match else None


def has_owner(comment):
    """True when the comment names at least one owner."""
    if not comment or comment.lower().startswith("todo"):
        return False
    return bool(
        _EMAIL.search(comment) or _PWL_ID.search(comment) or _TEAM.search(comment)
    )


def _top_level_keys(text):
    """Yield (line number, name, comment) for each record in a zone file."""
    for number, line in enumerate(text.split("\n"), start=1):
        if line == "---":
            continue
        match = _TOP_LEVEL.match(line)
        if not match:
            continue
        name = next(
            g for g in (match.group("dq"), match.group("sq"), match.group("bare"))
            if g is not None
        )
        yield number, name, _owner_comment(match.group("rest"))


def _records(value):
    """A record name holds one record or a list of them."""
    if isinstance(value, list):
        return value
    return [value]


def _record_values(record):
    values = record["values"] if "values" in record else record.get("value")
    if values is None:
        return []
    return values if isinstance(values, list) else [values]


def _caa_ca(value):
    """The CA domain of a CAA issue or issuewild value, in lower case.

    The parameters after `;` are dropped. DNS names do not depend on case, and
    a trailing dot is the same name.
    """
    return str(value).split(";")[0].strip().strip('"').rstrip(".").lower()


def _caa_errors(where, label, record):
    """Return the errors for one CAA record."""
    errors = []
    for caa in _record_values(record):
        if not isinstance(caa, dict):
            errors.append(f"{where}: `{label}` CAA value is not a mapping")
            continue
        tag = caa.get("tag")
        value = str(caa.get("value", ""))
        flags = caa.get("flags", 0)
        if isinstance(flags, bool) or not isinstance(flags, int) or flags not in CAA_FLAGS:
            errors.append(
                f"{where}: `{label}` CAA has flags {flags!r}. Use the number 0 or 128"
            )
        if tag not in CAA_TAGS:
            errors.append(
                f"{where}: `{label}` CAA has tag `{tag}`. Use one of "
                f"{', '.join(sorted(CAA_TAGS))}"
            )
        elif tag == "iodef":
            if not value.lower().startswith(("mailto:", "https://")):
                errors.append(
                    f"{where}: `{label}` CAA iodef `{value}` must start with "
                    f"mailto: or https://"
                )
        else:
            # An empty CA (`;`) is allowed: it means that no CA can issue.
            ca = _caa_ca(value)
            if ca and ca not in KNOWN_CAS:
                errors.append(
                    f"{where}: `{label}` CAA {tag} `{ca}` is not a known CA. "
                    f"Fix the name or add it to KNOWN_CAS in tools/check_zones.py"
                )
    return errors


def check_file(path):
    """Return a list of `file:line: message` strings for one zone file."""
    text = path.read_text()
    errors = []

    lines = {}
    for number, name, comment in _top_level_keys(text):
        if name in lines:
            errors.append(
                f"{path.name}:{number}: `{name or '@'}` is already defined on "
                f"line {lines[name]}"
            )
            continue
        lines[name] = number
        if not has_owner(comment):
            errors.append(
                f"{path.name}:{number}: `{name or '@'}` has no owner. Add an "
                f"email, a Patchwork id or both in a comment on the same line"
            )

    data = yaml.safe_load(text) or {}
    if not isinstance(data, dict):
        return errors + [f"{path.name}:1: the file is not a mapping of records"]

    for name, value in data.items():
        number = lines.get(name, 1)
        label = name or "@"
        apex_cas = None
        if name == META_RECORD:
            errors.append(
                f"{path.name}:{number}: `{META_RECORD}` is written by octoDNS. "
                f"Remove it from the zone file"
            )
        for record in _records(value):
            if not isinstance(record, dict):
                continue
            rtype = str(record.get("type", "")).upper()
            ttl = record.get("ttl")
            if ttl is not None and ttl < MIN_TTL:
                errors.append(
                    f"{path.name}:{number}: `{label}` {rtype} has ttl {ttl}. "
                    f"The Cloudflare minimum is {MIN_TTL}"
                )
            if name == "" and rtype == "NS":
                errors.append(
                    f"{path.name}:{number}: the apex NS records belong to "
                    f"Cloudflare. Remove them from the zone file"
                )
            if rtype == "CAA":
                errors.extend(_caa_errors(f"{path.name}:{number}", label, record))
                if name == "":
                    apex_cas = (apex_cas or set()) | {
                        _caa_ca(caa.get("value", ""))
                        for caa in _record_values(record)
                        if isinstance(caa, dict) and caa.get("tag") == "issue"
                    }
            octodns = record.get("octodns") or {}
            proxied = (octodns.get("cloudflare") or {}).get("proxied")
            if proxied and rtype not in PROXIABLE:
                errors.append(
                    f"{path.name}:{number}: `{label}` {rtype} cannot be "
                    f"proxied. Only {', '.join(sorted(PROXIABLE))} can"
                )
        # Without an `issue` property every CA can issue (RFC 8659), so only an
        # `issue` list that leaves Let's Encrypt out is a problem.
        if apex_cas and REQUIRED_APEX_CA not in apex_cas:
            errors.append(
                f"{path.name}:{number}: the apex CAA records do not allow "
                f"{REQUIRED_APEX_CA}. Vercel, Traefik on alastor and the thimble "
                f"VPN could not renew their certificates"
            )
    return errors


def _config_zones(repo_dir):
    with open(Path(repo_dir) / "config" / "config.yaml") as fh:
        return [z.rstrip(".") for z in yaml.safe_load(fh)["zones"]]


def check_repo(repo_dir):
    """Return every error for the repository."""
    repo = Path(repo_dir)
    zones = _config_zones(repo)
    errors = []

    files = {p.name for p in repo.glob("*.yaml")} | {
        p.name for p in repo.glob("*.yml")
    }
    expected = {f"{zone}.yaml" for zone in zones}
    for name in sorted(expected - files):
        errors.append(f"{name}:1: the zone is in config/config.yaml but the file is missing")
    for name in sorted(files - expected):
        errors.append(
            f"{name}:1: this file is not a zone in config/config.yaml, so "
            f"octoDNS would ignore it"
        )

    for name in sorted(expected & files):
        errors.extend(check_file(repo / name))
    return errors


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--repo-dir", default=".", help="where the zone files live")
    args = parser.parse_args(argv)

    errors = check_repo(args.repo_dir)
    for error in errors:
        print(error)
    if errors:
        print(f"\n{len(errors)} problem(s). See README.md for the rules.")
        return 1
    print("Every zone file follows the repository rules.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
