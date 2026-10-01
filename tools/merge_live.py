#!/usr/bin/env python3
"""Merge the live Cloudflare state back into the repository zone files.

People sometimes add or change a record in the Cloudflare dashboard instead of
opening a pull request. The nightly workflow dumps the live zones with
``bin/dump`` and then runs this script to fold those changes into the zone
files at the repository root.

A plain ``octodns-dump`` overwrite would work, but it would delete every
comment in the file, and this repository keeps the owner of each subdomain in a
comment. So this script edits only the records that really differ, and leaves
every other line of the file as it is.

A record differs when octoDNS would change it on the next deploy. The script
asks the Cloudflare provider, the same code that the deploy uses. So a TTL that
Cloudflare ignores on a proxied record, a TXT value in a different order, or a
TTL that the dump leaves out because it is the default, is not a difference.

Usage:

    python3 tools/merge_live.py --live-dir .live --repo-dir . \
        --zone patchworklabs.org. --summary-out summary.md

The script writes a Markdown summary to ``--summary-out`` and prints one line
per zone to stdout. It exits 0 when nothing changed and 0 when something did.
Use ``git status`` to find out which files it touched.
"""

import argparse
import io
import sys
import tempfile
from datetime import date
from pathlib import Path

from natsort import natsort_keygen
from octodns.provider.yaml import YamlProvider
from octodns.zone import Zone
from octodns_cloudflare import CloudflareProvider
from ruamel.yaml import YAML

from check_zones import _top_level_keys

# octoDNS checks record order with a natural sort, so `ns2` comes before
# `ns10`. Plain `sorted` gets that backwards and would write a file that
# `bin/validate` then rejects. Use the same key octoDNS uses.
_natsort_key = natsort_keygen()

# Records that octoDNS itself manages. They live in Cloudflare but never in the
# zone files, so merging them back would create an endless nightly diff.
DEFAULT_IGNORED = ("octodns-meta",)

# `octodns-dump` writes its files with the YamlProvider default TTL, so a record
# with this TTL has no `ttl` key in the dump.
DUMP_DEFAULT_TTL = 3600

# Used when the repository has no config/config.yaml, as in the tests.
REPO_DEFAULT_TTL = 3600
CLOUDFLARE_MIN_TTL = 120


def _settings(repo_dir):
    """Read the default TTL and the Cloudflare minimum TTL from the config."""
    path = Path(repo_dir) / "config" / "config.yaml"
    if not path.exists():
        return REPO_DEFAULT_TTL, CLOUDFLARE_MIN_TTL
    providers = YAML(typ="safe").load(path.read_text()).get("providers", {})
    default_ttl = providers.get("config", {}).get("default_ttl", REPO_DEFAULT_TTL)
    min_ttl = providers.get("cloudflare", {}).get("min_ttl", CLOUDFLARE_MIN_TTL)
    return default_ttl, min_ttl


def _load_zone(zone, directory, default_ttl):
    """Load one zone file into an octoDNS Zone."""
    loaded = Zone(zone, [])
    YamlProvider(
        "merge-live",
        str(directory),
        default_ttl=default_ttl,
        enforce_order=False,
        escaped_semicolons=True,
    ).populate(loaded, lenient=True)
    return loaded


def _changed_names(zone, live_records, repo_dir, names):
    """The names, out of `names`, that the next deploy would change.

    This is the comparison that `octoDNS plan` makes against Cloudflare, with
    the live dump standing in for the Cloudflare API. `live_records` is the
    dump after the ignored records and the root NS records are taken out.
    """
    default_ttl, min_ttl = _settings(repo_dir)
    with tempfile.TemporaryDirectory() as live_dir:
        with open(Path(live_dir) / _zone_file(zone), "w") as handle:
            YAML().dump(dict(live_records), handle)
        live = _load_zone(zone, live_dir, DUMP_DEFAULT_TTL)
    repo = _load_zone(zone, repo_dir, default_ttl)
    for loaded in (live, repo):
        for record in list(loaded.records):
            if record.name not in names:
                loaded.remove_record(record)

    # The token is never used. Nothing here calls the Cloudflare API.
    cloudflare = CloudflareProvider("cloudflare", token="unused", min_ttl=min_ttl)
    changes = [c for c in live.changes(repo, cloudflare) if cloudflare._include_change(c)]
    changes += cloudflare._extra_changes(existing=live, desired=repo, changes=changes)
    return {c.record.name for c in changes}


def _is_root_ns(record):
    return record.get("type") == "NS"


def _strip_root_ns(live):
    """Drop the NS records at the apex of the zone.

    Cloudflare assigns the nameservers for a zone and reports them over the
    API. octoDNS refuses to apply a plan that changes the apex NS records
    without `--force`, so pulling them into the zone files would break every
    later deploy. Cloudflare owns them. Leave them alone.
    """
    root = live.get("")
    if root is None:
        return live
    records = root if isinstance(root, list) else [root]
    kept = [r for r in records if not _is_root_ns(r)]
    if kept:
        live[""] = kept
    else:
        del live[""]
    return live


def _yaml():
    """A YAML handler that writes the octoDNS zone file style."""
    handler = YAML()
    handler.preserve_quotes = True
    handler.width = 4096
    handler.indent(mapping=2, sequence=4, offset=2)
    return handler


def _zone_file(zone):
    """`patchworklabs.org.` -> `patchworklabs.org.yaml`."""
    return f"{zone.rstrip('.')}.yaml"


def _blocks(lines):
    """Split a zone file into a head and one block per record.

    A block starts at the comment lines directly above a record name and ends
    at the blank line before the next block. Returns (head, {name: (start,
    end)}), where `head` is the index of the first block.
    """
    keys = [(number - 1, name) for number, name, _ in _top_level_keys("\n".join(lines))]
    starts = []
    for index, _ in keys:
        start = index
        while start > 0 and lines[start - 1].startswith("#"):
            start -= 1
        starts.append(start)
    blocks = {}
    for position, (index, name) in enumerate(keys):
        end = starts[position + 1] if position + 1 < len(keys) else len(lines)
        while end > index + 1 and lines[end - 1].strip() == "":
            end -= 1
        blocks[name] = (starts[position], end)
    head = starts[0] if starts else len(lines)
    return head, blocks


def _with_ttl(value):
    """Give every record in a dumped value an explicit TTL.

    The dump leaves out a TTL of 3600, its own default. The zone files have a
    different default, so a record copied without its TTL would change.
    """
    for record in value if isinstance(value, list) else [value]:
        if "ttl" not in record:
            record.insert(1 if "octodns" in record else 0, "ttl", DUMP_DEFAULT_TTL)
    return value


def _render(handler, name, value, comment_line):
    """Write one record as zone file lines, with `comment_line` as its key line."""
    value = _with_ttl(value)
    buffer = io.StringIO()
    handler.dump({name: value}, buffer)
    body = buffer.getvalue().rstrip("\n").split("\n")[1:]
    return [comment_line, *body]


def _key_line(name, comment):
    key = '""' if name == "" else name
    return f"{key}: # {comment}" if comment else f"{key}:"


def merge_zone(zone, live_dir, repo_dir, ignored, today, keep_root_ns=False):
    """Merge one zone. Returns (added, updated, removed) record name lists."""
    handler = _yaml()
    name = _zone_file(zone)
    live_path = Path(live_dir) / name
    repo_path = Path(repo_dir) / name

    if not live_path.exists():
        raise FileNotFoundError(f"no dump for {zone} at {live_path}")

    live = YAML().load(live_path.read_text()) or {}
    live = {k: v for k, v in live.items() if k not in ignored}
    if not keep_root_ns:
        live = _strip_root_ns(live)

    text = repo_path.read_text() if repo_path.exists() else "---\n"
    lines = text.rstrip("\n").split("\n")
    head, blocks = _blocks(lines)
    comments = {n: c for _, n, c in _top_level_keys(text)}

    added = sorted((k for k in live if k not in blocks), key=_natsort_key)
    removed = sorted(
        (k for k in blocks if k not in live and k not in ignored), key=_natsort_key
    )
    common = {k for k in live if k in blocks}
    updated = []
    if common:
        changed = _changed_names(zone, live, repo_dir, common)
        updated = sorted(changed, key=_natsort_key)

    if not (added or updated or removed):
        return [], [], []

    replacements = {}
    for key in updated:
        replacements[key] = _render(handler, key, live[key], _key_line(key, comments.get(key)))
    for key in added:
        owner = f"TODO owner unknown, added from Cloudflare on {today}"
        replacements[key] = _render(handler, key, live[key], _key_line(key, owner))

    # Rebuild the file block by block, in natural order. A block that did not
    # change is copied as it was, comments and all.
    kept = [k for k in blocks if k not in removed]
    names = sorted(set(kept) | set(added), key=_natsort_key)
    out = lines[:head]
    while out and out[-1].strip() == "":
        out.pop()
    for key in names:
        if key in replacements:
            start, end = blocks.get(key, (None, None))
            above = []
            if start is not None:
                key_index = next(i for i in range(start, end) if not lines[i].startswith("#"))
                above = lines[start:key_index]
            block = above + replacements[key]
        else:
            start, end = blocks[key]
            block = lines[start:end]
        if out and out[-1].strip() != "---":
            out.append("")
        out.extend(block)
    repo_path.write_text("\n".join(out).rstrip("\n") + "\n")
    return added, updated, removed


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--live-dir", required=True, help="output of bin/dump")
    parser.add_argument("--repo-dir", default=".", help="where the zone files live")
    parser.add_argument(
        "--zone",
        dest="zones",
        action="append",
        required=True,
        help="a zone to merge, with the trailing dot, repeatable",
    )
    parser.add_argument(
        "--ignore-record",
        dest="ignored",
        action="append",
        default=[],
        help="a record name to leave out of the merge, repeatable",
    )
    parser.add_argument(
        "--keep-root-ns",
        action="store_true",
        help="pull the apex NS records in too. Cloudflare owns them, so this "
        "will make later deploys fail. Only use it to inspect a zone.",
    )
    parser.add_argument("--summary-out", help="write a Markdown summary here")
    args = parser.parse_args(argv)

    ignored = set(DEFAULT_IGNORED) | set(args.ignored)
    today = date.today().isoformat()

    summary = []
    changed = False
    for zone in args.zones:
        added, updated, removed = merge_zone(
            zone, args.live_dir, args.repo_dir, ignored, today, args.keep_root_ns
        )
        if not (added or updated or removed):
            print(f"{zone} in sync")
            continue
        changed = True
        print(
            f"{zone} {len(added)} added, {len(updated)} updated, "
            f"{len(removed)} removed"
        )
        summary.append(f"### `{zone.rstrip('.')}`\n")
        for label, names in (
            ("Added in Cloudflare", added),
            ("Changed in Cloudflare", updated),
            ("Removed in Cloudflare", removed),
        ):
            if names:
                summary.append(f"**{label}**\n")
                summary.extend(f"- `{n or '@'}`" for n in sorted(names))
                summary.append("")

    if args.summary_out:
        text = "\n".join(summary) if changed else "No drift found.\n"
        if any("Removed in Cloudflare" in line for line in summary):
            text += (
                "\n> **Check the removals.** A record is listed as removed "
                "because it is in the zone file but not in Cloudflare. That "
                "usually means somebody deleted it in the dashboard. It can "
                "also mean the last deploy failed. Confirm which one it is "
                "before you merge.\n"
            )
        Path(args.summary_out).write_text(text)

    return 0


if __name__ == "__main__":
    sys.exit(main())
