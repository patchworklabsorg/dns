#!/usr/bin/env python3
"""Merge the live Cloudflare state back into the repository zone files.

People sometimes add or change a record in the Cloudflare dashboard instead of
opening a pull request. The nightly workflow dumps the live zones with
``bin/dump`` and then runs this script to fold those changes into the zone
files at the repository root.

A plain ``octodns-dump`` overwrite would work, but it would delete every
comment in the file, and this repository keeps the owner of each subdomain in a
comment. So this script edits the existing file in place with ruamel.yaml,
which keeps comments attached to their record.

Usage:

    python3 tools/merge_live.py --live-dir .live --repo-dir . \
        --zone patchworklabs.org. --summary-out summary.md

The script writes a Markdown summary to ``--summary-out`` and prints one line
per zone to stdout. It exits 0 when nothing changed and 0 when something did.
Use ``git status`` to find out which files it touched.
"""

import argparse
import io
import re
import sys
from datetime import date
from pathlib import Path

from natsort import natsort_keygen
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap

# octoDNS checks record order with a natural sort, so `ns2` comes before
# `ns10`. Plain `sorted` gets that backwards and would write a file that
# `bin/validate` then rejects. Use the same key octoDNS uses.
_natsort_key = natsort_keygen()

# Records that octoDNS itself manages. They live in Cloudflare but never in the
# zone files, so merging them back would create an endless nightly diff.
DEFAULT_IGNORED = ("octodns-meta",)


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
    kept = [r for r in records if r.get("type") != "NS"]
    if kept:
        live[""] = kept
    else:
        del live[""]
    return live


def _yaml():
    """A YAML handler that reads and writes the octoDNS zone file style."""
    handler = YAML()
    handler.explicit_start = True
    handler.preserve_quotes = True
    handler.width = 4096
    handler.indent(mapping=2, sequence=4, offset=2)
    return handler


def _normalize(value):
    """Strip ruamel types so that live and repo values compare as plain data."""
    if isinstance(value, dict):
        return {k: _normalize(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_normalize(v) for v in value]
    return value


def _zone_file(zone):
    """`patchworklabs.org.` -> `patchworklabs.org.yaml`."""
    return f"{zone.rstrip('.')}.yaml"


def _space_records(text):
    """Put exactly one blank line between top level records.

    ruamel keeps a comment with its own record but does not reliably keep the
    blank lines around it once records are reordered. Normalizing the spacing
    afterwards is simpler and gives a stable diff.
    """
    lines = text.split("\n")
    out = []
    top_level = re.compile(r"^[^\s#-][^:]*:")
    for line in lines:
        if top_level.match(line) and out:
            while out and out[-1].strip() == "":
                out.pop()
            if out and out[-1].strip() != "---":
                out.append("")
        out.append(line)
    text = "\n".join(out)
    return re.sub(r"\n{3,}", "\n\n", text).rstrip("\n") + "\n"


def merge_zone(zone, live_dir, repo_dir, ignored, today, keep_root_ns=False):
    """Merge one zone. Returns (added, updated, removed) record name lists."""
    handler = _yaml()
    name = _zone_file(zone)
    live_path = Path(live_dir) / name
    repo_path = Path(repo_dir) / name

    if not live_path.exists():
        raise FileNotFoundError(f"no dump for {zone} at {live_path}")

    live = handler.load(live_path.read_text()) or CommentedMap()
    live = {k: v for k, v in live.items() if k not in ignored}
    if not keep_root_ns:
        live = _strip_root_ns(live)

    existing = CommentedMap()
    doc_comment = None
    if repo_path.exists():
        loaded = handler.load(repo_path.read_text())
        if isinstance(loaded, CommentedMap):
            existing = loaded
            doc_comment = loaded.ca.comment

    added, updated, removed = [], [], []
    for key in live:
        if key not in existing:
            added.append(key)
        elif _normalize(existing[key]) != _normalize(live[key]):
            updated.append(key)
    for key in existing:
        if key not in live and key not in ignored:
            removed.append(key)

    if not (added or updated or removed):
        return [], [], []

    merged = CommentedMap()
    # The apex record, whose name is the empty string, sorts first by itself.
    for key in sorted(live, key=_natsort_key):
        merged[key] = live[key]
        carried = existing.ca.items.get(key)
        if carried is not None:
            merged.ca.items[key] = carried
        elif key in added:
            merged.yaml_add_eol_comment(
                f"TODO owner unknown, added from Cloudflare on {today}", key
            )
    if doc_comment is not None:
        merged.ca.comment = doc_comment

    buffer = io.StringIO()
    handler.dump(merged, buffer)
    repo_path.write_text(_space_records(buffer.getvalue()))
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
