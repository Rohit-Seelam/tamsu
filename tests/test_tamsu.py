"""Checks for the tamsu repo. Run: python3 -m unittest discover tests"""

import json
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "oskiv"
TEMPLATES = PLUGIN / "templates"


class Manifests(unittest.TestCase):
    def test_versions_match(self):
        """A version bump in only one manifest serves stale code from the plugin cache."""
        market = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text())
        plugin = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text())
        entry = next(p for p in market["plugins"] if p["name"] == "oskiv")
        self.assertEqual(entry["version"], plugin["version"])

    def test_versions_md_lists_current_version(self):
        """A release with no VERSIONS.md entry leaves no record of what changed or was verified."""
        version = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text())["version"]
        self.assertIn(f"## {version}", (ROOT / "VERSIONS.md").read_text())


class Templates(unittest.TestCase):
    def test_json_templates_parse(self):
        """A malformed template would be copied into every repo init touches."""
        for path in [*TEMPLATES.rglob("*.json"), ROOT / "user" / "settings.json"]:
            with self.subTest(path=path.relative_to(ROOT)):
                json.loads(path.read_text())

    def test_init_names_only_existing_templates(self):
        """init.md points at template files by name; a rename would silently break init."""
        rows = [line.split("|") for line in (PLUGIN / "commands" / "init.md").read_text().splitlines()
                if line.startswith("| `")]
        names = {name for row in rows for name in re.findall(r"`([^`]+)`", row[2])}
        self.assertTrue(names)
        for name in names:
            with self.subTest(name=name):
                path = TEMPLATES / name.rstrip("/")
                if "{" in name:  # build/{a, b, c}
                    base, inner = name.split("{")
                    for part in inner.rstrip("}").split(","):
                        self.assertTrue((TEMPLATES / base / part.strip()).exists(), part)
                else:
                    self.assertTrue(path.exists(), name)

    def test_rules_have_paths_frontmatter(self):
        """A rule whose frontmatter doesn't parse loads in every session instead of on match."""
        for path in [*TEMPLATES.rglob("rules/*.md"), *(ROOT / "user" / "rules").glob("*.md")]:
            with self.subTest(path=path.relative_to(ROOT)):
                text = path.read_text()
                self.assertTrue(text.startswith("---\npaths:\n"), "missing paths: frontmatter")


class LinkUser(unittest.TestCase):
    def run_script(self, home, *args):
        return subprocess.run(
            ["sh", str(ROOT / "scripts" / "link-user.sh"), *args],
            env={"CLAUDE_CONFIG_DIR": home, "PATH": "/usr/bin:/bin"},
            capture_output=True, text=True, input="",
        )

    def test_links_then_check_passes(self):
        """After linking into an empty config dir, --check reports every file as linked."""
        with tempfile.TemporaryDirectory() as home:
            self.assertEqual(self.run_script(home).returncode, 0)
            check = self.run_script(home, "--check")
            self.assertEqual(check.returncode, 0, check.stdout)
            self.assertTrue((Path(home) / "CLAUDE.md").is_symlink())

    def test_check_flags_link_replaced_by_plain_file(self):
        """An app that saves by replacing the file turns the link into a plain file; --check must notice."""
        with tempfile.TemporaryDirectory() as home:
            self.run_script(home)
            target = Path(home) / "settings.json"
            target.unlink()
            target.write_text("{}\n")
            check = self.run_script(home, "--check")
            self.assertEqual(check.returncode, 1)
            self.assertIn("NOT LINKED", check.stdout)

    def test_does_not_replace_differing_file_without_yes(self):
        """A real config file that differs is only replaced after an explicit 'y'."""
        with tempfile.TemporaryDirectory() as home:
            (Path(home) / "CLAUDE.md").write_text("mine\n")
            result = self.run_script(home)
            self.assertEqual(result.returncode, 0, result.stderr)  # skipping must not abort the rest
            self.assertTrue((Path(home) / "rules" / "python.md").is_symlink())
            self.assertFalse((Path(home) / "CLAUDE.md").is_symlink())
            self.assertEqual((Path(home) / "CLAUDE.md").read_text(), "mine\n")


if __name__ == "__main__":
    unittest.main()
