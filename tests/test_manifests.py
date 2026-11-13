"""Tests that the plugin manifests agree with package.json and the skills folder.

CI used to check only that these files parse. The plugin version stayed at
1.0.0 through three releases, and the marketplace entry carried a `skills`
list of objects that `claude plugin validate` rejects. These tests fail on
either, and on a documented skill count that no longer matches `skills/`.

Run: python3 -m unittest discover -s tests -v
"""

import json
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
PLUGIN_MANIFEST = ".claude-plugin/plugin.json"
MARKETPLACE_MANIFEST = ".claude-plugin/marketplace.json"

# Each pattern captures a skill count that a reader is told to expect.
COUNT_CLAIMS = {
    MARKETPLACE_MANIFEST: [r"(\d+) slash commands"],
    "README.md": [r"installs all (\d+) skills", r"The (\d+) Claude Code Slash Commands"],
}


def load_json(relative_path):
    return json.loads((ROOT / relative_path).read_text(encoding="utf-8"))


def bundled_skill_names():
    return sorted(path.parent.name for path in (ROOT / "skills").glob("*/SKILL.md"))


class ManifestVersionTest(unittest.TestCase):
    def setUp(self):
        self.package_version = load_json("package.json")["version"]

    def test_plugin_manifest_version_matches_package_json(self):
        self.assertEqual(load_json(PLUGIN_MANIFEST)["version"], self.package_version)

    def test_marketplace_metadata_version_matches_package_json(self):
        marketplace = load_json(MARKETPLACE_MANIFEST)

        self.assertEqual(marketplace["metadata"]["version"], self.package_version)

    def test_every_marketplace_plugin_version_matches_package_json(self):
        plugins = load_json(MARKETPLACE_MANIFEST)["plugins"]

        self.assertTrue(plugins, "marketplace.json lists no plugins")
        for plugin in plugins:
            with self.subTest(plugin=plugin["name"]):
                self.assertEqual(plugin["version"], self.package_version)


class MarketplaceShapeTest(unittest.TestCase):
    def test_plugin_skills_field_holds_paths_not_objects(self):
        # Claude Code accepts a path or a list of paths here. Skills under
        # skills/ are discovered without the field, so leaving it out is fine.
        for plugin in load_json(MARKETPLACE_MANIFEST)["plugins"]:
            if "skills" not in plugin:
                continue
            skills = plugin["skills"]
            paths = [skills] if isinstance(skills, str) else skills
            with self.subTest(plugin=plugin["name"]):
                self.assertIsInstance(paths, list)
                for path in paths:
                    self.assertIsInstance(path, str, f"skills entry is not a path: {path!r}")


class SkillCountTest(unittest.TestCase):
    def test_documented_skill_counts_match_the_skills_folder(self):
        actual = len(bundled_skill_names())

        self.assertGreater(actual, 0, "no skills found under skills/")
        for relative_path, patterns in COUNT_CLAIMS.items():
            text = (ROOT / relative_path).read_text(encoding="utf-8")
            for pattern in patterns:
                for claimed in re.findall(pattern, text):
                    with self.subTest(file=relative_path, pattern=pattern):
                        self.assertEqual(int(claimed), actual)


if __name__ == "__main__":
    unittest.main()
