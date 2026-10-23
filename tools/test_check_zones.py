"""Tests for tools/check_zones.py.

Run them with:

    python3 -m unittest discover -s tools -p 'test_*.py' -v
"""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from check_zones import check_file, check_repo, has_owner  # noqa: E402
from merge_live import merge_zone  # noqa: E402

CONFIG = """---
zones:
  patchworklabs.org.:
    sources: [config]
    targets: [cloudflare]
"""

GOOD = """---
"": # @patchworklabsorg/infra
  - ttl: 120
    type: MX
    values:
      - exchange: aspmx.l.google.com.
        preference: 1

# A comment above a record is fine as well.
api: # ada@patchworklabs.org, @grace
  - octodns:
      cloudflare:
        proxied: true
    ttl: 300
    type: CNAME
    value: api.example.com.

docs: # grace@patchworklabs.org
  type: TXT
  value: no-ttl-uses-the-default
"""


class HasOwnerTest(unittest.TestCase):
    def test_email(self):
        self.assertTrue(has_owner("ada@patchworklabs.org"))

    def test_pwl_id(self):
        self.assertTrue(has_owner("PWL7A1CE1F3CB"))

    def test_pwl_id_and_email(self):
        self.assertTrue(has_owner("PWL7A1CE1F3CB / jasper@patchworklabs.org"))

    def test_malformed_pwl_id(self):
        self.assertFalse(has_owner("PWL123"))
        self.assertFalse(has_owner("pwl7a1ce1f3cb"))

    def test_github_user_is_not_an_owner(self):
        self.assertFalse(has_owner("@jaspermayone"))

    def test_github_team(self):
        self.assertTrue(has_owner("@patchworklabsorg/infra"))

    def test_several(self):
        self.assertTrue(has_owner("ada@patchworklabs.org, @patchworklabsorg/infra"))

    def test_none(self):
        self.assertFalse(has_owner(None))
        self.assertFalse(has_owner(""))

    def test_free_text(self):
        self.assertFalse(has_owner("Google Workspace DKIM"))

    def test_todo_from_the_nightly_sync(self):
        self.assertFalse(
            has_owner("TODO owner unknown, added from Cloudflare on 2026-09-21")
        )


class CheckFileTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "patchworklabs.org.yaml"

    def check(self, body):
        self.path.write_text(body)
        return check_file(self.path)

    def assertOneError(self, body, fragment):
        errors = self.check(body)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn(fragment, errors[0])

    def test_good_file_passes(self):
        self.assertEqual(self.check(GOOD), [])

    def test_missing_owner(self):
        self.assertOneError(
            "---\napi:\n  ttl: 300\n  type: A\n  value: 192.0.2.1\n",
            "patchworklabs.org.yaml:2: `api` has no owner",
        )

    def test_owner_on_the_line_above_does_not_count(self):
        self.assertOneError(
            "---\n# ada@patchworklabs.org\napi:\n  ttl: 300\n  type: A\n"
            "  value: 192.0.2.1\n",
            "`api` has no owner",
        )

    def test_apex_without_owner_is_named_at(self):
        self.assertOneError(
            '---\n"":\n  ttl: 300\n  type: A\n  value: 192.0.2.1\n',
            "`@` has no owner",
        )

    def test_single_quoted_apex(self):
        body = "---\n'': # PWL7A1CE1F3CB\n  ttl: 300\n  type: A\n  value: 192.0.2.1\n"
        self.assertEqual(self.check(body), [])

    def test_todo_owner_fails(self):
        self.assertOneError(
            "---\napi: # TODO owner unknown, added from Cloudflare on 2026-09-21\n"
            "  ttl: 300\n  type: A\n  value: 192.0.2.1\n",
            "has no owner",
        )

    def test_low_ttl(self):
        self.assertOneError(
            "---\napi: # ada@patchworklabs.org\n  ttl: 1\n  type: A\n  value: 192.0.2.1\n",
            "`api` A has ttl 1. The Cloudflare minimum is 120",
        )

    def test_low_ttl_inside_a_list(self):
        self.assertOneError(
            "---\napi: # ada@patchworklabs.org\n  - ttl: 300\n    type: A\n    value: 192.0.2.1\n"
            "  - ttl: 60\n    type: TXT\n    value: hello\n",
            "`api` TXT has ttl 60",
        )

    def test_apex_ns(self):
        self.assertOneError(
            '---\n"": # ada@patchworklabs.org\n  ttl: 3600\n  type: NS\n  values:\n'
            "    - ns1.example.com.\n",
            "apex NS records belong to Cloudflare",
        )

    def test_ns_on_a_subdomain_is_fine(self):
        body = (
            "---\nsub: # ada@patchworklabs.org\n  ttl: 3600\n  type: NS\n  values:\n"
            "    - ns1.example.com.\n"
        )
        self.assertEqual(self.check(body), [])

    def test_meta_record(self):
        self.assertOneError(
            "---\noctodns-meta: # ada@patchworklabs.org\n  ttl: 120\n  type: TXT\n  value: x\n",
            "`octodns-meta` is written by octoDNS",
        )

    def test_proxied_txt(self):
        self.assertOneError(
            "---\napi: # ada@patchworklabs.org\n  octodns:\n    cloudflare:\n      proxied: true\n"
            "  ttl: 300\n  type: TXT\n  value: x\n",
            "`api` TXT cannot be proxied",
        )

    def caa(self, name, *entries):
        """A zone file with one CAA record of (flags, tag, value) entries."""
        values = "".join(
            f"    - flags: {flags}\n      tag: {tag}\n      value: {value}\n"
            for flags, tag, value in entries
        )
        return f"---\n{name}: # ada@patchworklabs.org\n  ttl: 3600\n  type: CAA\n  values:\n{values}"

    def test_good_caa(self):
        body = self.caa(
            '""',
            (0, "iodef", "mailto:security@patchworklabs.org"),
            (0, "issue", "letsencrypt.org"),
            (0, "issue", "pki.goog"),
            (128, "issuewild", "ssl.com"),
        )
        self.assertEqual(self.check(body), [])

    def test_caa_single_value(self):
        body = (
            '---\n"": # ada@patchworklabs.org\n  ttl: 3600\n  type: CAA\n  value:\n'
            "    flags: 0\n    tag: issue\n    value: letsencrypt.org\n"
        )
        self.assertEqual(self.check(body), [])

    def test_caa_inside_a_list(self):
        body = (
            '---\n"": # ada@patchworklabs.org\n  - ttl: 120\n    type: A\n'
            "    value: 192.0.2.1\n  - ttl: 3600\n    type: CAA\n    values:\n"
            "      - flags: 0\n        tag: issue\n        value: letsencrypt.com\n"
        )
        errors = self.check(body)
        self.assertTrue(any("`letsencrypt.com` is not a known CA" in e for e in errors), errors)

    def test_caa_unknown_ca(self):
        errors = self.check(
            self.caa('""', (0, "issue", "letsencrypt.org"), (0, "issue", "letsencrypt.com"))
        )
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("`@` CAA issue `letsencrypt.com` is not a known CA", errors[0])

    def test_caa_parameters_after_the_ca(self):
        body = self.caa('""', (0, "issue", '"letsencrypt.org; validationmethods=dns-01"'))
        self.assertEqual(self.check(body), [])

    def test_caa_unknown_issuewild_ca(self):
        self.assertOneError(
            self.caa("sub", (0, "issuewild", "example-ca.com")),
            "`sub` CAA issuewild `example-ca.com` is not a known CA",
        )

    def test_caa_empty_ca_on_a_subdomain(self):
        self.assertEqual(self.check(self.caa("sub", (0, "issue", '";"'))), [])

    def test_caa_bad_tag(self):
        self.assertOneError(
            self.caa("sub", (0, "isue", "letsencrypt.org")),
            "`sub` CAA has tag `isue`",
        )

    def test_caa_bad_flags(self):
        self.assertOneError(
            self.caa("sub", (1, "issue", "letsencrypt.org")),
            "`sub` CAA has flags 1",
        )

    def test_caa_bad_iodef(self):
        self.assertOneError(
            self.caa("sub", (0, "iodef", "security@patchworklabs.org")),
            "iodef `security@patchworklabs.org` must start with mailto: or https://",
        )

    def test_apex_caa_without_letsencrypt(self):
        self.assertOneError(
            self.caa('""', (0, "issue", "pki.goog")),
            "the apex CAA records do not allow letsencrypt.org",
        )

    def test_apex_caa_with_only_issuewild_letsencrypt(self):
        self.assertOneError(
            self.caa('""', (0, "issue", "pki.goog"), (0, "issuewild", "letsencrypt.org")),
            "the apex CAA records do not allow letsencrypt.org",
        )

    def test_apex_caa_without_issue_allows_every_ca(self):
        body = self.caa(
            '""',
            (0, "iodef", "mailto:security@patchworklabs.org"),
            (0, "issuewild", "pki.goog"),
        )
        self.assertEqual(self.check(body), [])

    def test_caa_ca_case_and_trailing_dot(self):
        body = self.caa('""', (0, "issue", "LetsEncrypt.org."), (0, "issue", "PKI.goog"))
        self.assertEqual(self.check(body), [])

    def test_caa_iodef_scheme_case(self):
        self.assertEqual(self.check(self.caa("sub", (0, "iodef", "MAILTO:a@patchworklabs.org"))), [])

    def test_caa_missing_flags(self):
        body = (
            "---\nsub: # ada@patchworklabs.org\n  ttl: 3600\n  type: CAA\n  value:\n"
            "    tag: issue\n    value: letsencrypt.org\n"
        )
        self.assertEqual(self.check(body), [])

    def test_caa_flags_that_are_not_a_number(self):
        for flags in ('"0"', "[0]", "{}", "true"):
            with self.subTest(flags=flags):
                self.assertOneError(
                    self.caa("sub", (flags, "issue", "letsencrypt.org")),
                    "`sub` CAA has flags",
                )

    def test_caa_values_as_one_string(self):
        body = (
            "---\nsub: # ada@patchworklabs.org\n  ttl: 3600\n  type: CAA\n"
            "  values: letsencrypt.org\n"
        )
        self.assertOneError(body, "`sub` CAA value is not a mapping")

    def test_apex_caa_that_forbids_every_ca(self):
        self.assertOneError(
            self.caa('""', (0, "issue", '";"')),
            "the apex CAA records do not allow letsencrypt.org",
        )

    def test_subdomain_caa_does_not_need_letsencrypt(self):
        self.assertEqual(self.check(self.caa("sub", (0, "issue", "pki.goog"))), [])

    def test_duplicate_name(self):
        errors = self.check(
            "---\napi: # ada@patchworklabs.org\n  ttl: 300\n  type: A\n  value: 192.0.2.1\n\n"
            "api: # ada@patchworklabs.org\n  ttl: 300\n  type: A\n  value: 192.0.2.2\n"
        )
        self.assertTrue(
            any("`api` is already defined on line 2" in e for e in errors), errors
        )

    def test_errors_carry_the_line_number(self):
        errors = self.check(GOOD.replace("api: # ada@patchworklabs.org, @grace", "api:"))
        self.assertEqual(len(errors), 1, errors)
        self.assertTrue(errors[0].startswith("patchworklabs.org.yaml:10:"), errors)


class CheckRepoTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name)
        (self.repo / "config").mkdir()
        (self.repo / "config" / "config.yaml").write_text(CONFIG)

    def test_good_repo(self):
        (self.repo / "patchworklabs.org.yaml").write_text(GOOD)
        self.assertEqual(check_repo(self.repo), [])

    def test_missing_zone_file(self):
        errors = check_repo(self.repo)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("the file is missing", errors[0])

    def test_stray_yaml_file(self):
        (self.repo / "patchworklabs.org.yaml").write_text(GOOD)
        (self.repo / "patchworklabs.com.yaml").write_text(GOOD)
        errors = check_repo(self.repo)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("patchworklabs.com.yaml:1: this file is not a zone", errors[0])


class NightlySyncTest(unittest.TestCase):
    """The file that the nightly sync writes must be readable by this check."""

    def test_new_record_from_cloudflare_needs_an_owner(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "live").mkdir()
            (root / "repo").mkdir()
            (root / "repo" / "patchworklabs.org.yaml").write_text(GOOD)
            live = GOOD + "\nnew:\n  ttl: 300\n  type: A\n  value: 192.0.2.9\n"
            (root / "live" / "patchworklabs.org.yaml").write_text(live)

            merge_zone(
                "patchworklabs.org.", root / "live", root / "repo",
                {"octodns-meta"}, "2026-09-21",
            )
            errors = check_file(root / "repo" / "patchworklabs.org.yaml")

        self.assertEqual(len(errors), 1, errors)
        self.assertIn("`new` has no owner", errors[0])


if __name__ == "__main__":
    unittest.main()
