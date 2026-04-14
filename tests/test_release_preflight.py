import importlib.util
import io
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PREFLIGHT_SPEC = importlib.util.spec_from_file_location(
    "release_preflight_module", PROJECT_ROOT / "scripts" / "release_preflight.py"
)
assert PREFLIGHT_SPEC and PREFLIGHT_SPEC.loader
release_preflight_module = importlib.util.module_from_spec(PREFLIGHT_SPEC)
PREFLIGHT_SPEC.loader.exec_module(release_preflight_module)


def write_tree(root: Path) -> None:
    for relative in release_preflight_module.REQUIRED_DIRS:
        (root / relative).mkdir(parents=True, exist_ok=True)
    for relative in release_preflight_module.REQUIRED_FILES:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if relative == "pyproject.toml":
            path.write_text('[project]\nversion = "0.3.0"\n', encoding="utf-8")
        elif relative == "CHANGELOG.md":
            path.write_text("# Changelog\n\n## [Unreleased]\n", encoding="utf-8")
        elif relative == "CONTRIBUTING.md":
            path.write_text("# Contributing\n", encoding="utf-8")
        else:
            path.write_text("ok\n", encoding="utf-8")
    constants = root / "ai_proxy_hub" / "constants.py"
    constants.write_text(
        'APP_REPOSITORY_URL = "https://example.invalid/repo"\nAPP_RELEASES_URL = "https://example.invalid/releases"\n',
        encoding="utf-8",
    )
    for relative in release_preflight_module.REQUIRED_SCREENSHOTS:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("stub", encoding="utf-8")


class ReleasePreflightTest(unittest.TestCase):
    def test_gather_failures_accepts_complete_tree(self):
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            write_tree(root)
            args = mock.Mock(version="0.3.0", allow_missing_public_links=False)
            with mock.patch.object(release_preflight_module, "find_tracked_runtime_leaks", return_value=[]):
                failures = release_preflight_module.gather_failures(root, args)
        self.assertEqual(failures, [])

    def test_gather_failures_reports_placeholders_and_missing_links(self):
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            write_tree(root)
            (root / "CONTRIBUTING.md").write_text("git clone https://github.com/<owner>/repo.git\n", encoding="utf-8")
            (root / "CHANGELOG.md").write_text("## [0.3.0] - 2024-01-XX\n", encoding="utf-8")
            (root / "ai_proxy_hub" / "constants.py").write_text(
                'APP_REPOSITORY_URL = ""\nAPP_RELEASES_URL = ""\n',
                encoding="utf-8",
            )
            args = mock.Mock(version="0.3.1", allow_missing_public_links=False)
            with mock.patch.object(release_preflight_module, "find_tracked_runtime_leaks", return_value=["config_8830.json"]):
                failures = release_preflight_module.gather_failures(root, args)
        self.assertTrue(any("placeholder still present in CONTRIBUTING.md" in item for item in failures))
        self.assertTrue(any("placeholder still present in CHANGELOG.md" in item for item in failures))
        self.assertIn("APP_REPOSITORY_URL is empty", failures)
        self.assertIn("APP_RELEASES_URL is empty", failures)
        self.assertTrue(any("pyproject version mismatch" in item for item in failures))
        self.assertIn("tracked runtime artifact should not be committed: config_8830.json", failures)

    def test_find_tracked_runtime_leaks_filters_git_index(self):
        completed = subprocess.CompletedProcess(
            args=["git"],
            returncode=0,
            stdout="README.md\nconfig_8830.json\ntmp/runtime-8820.log\nbuild/output.txt\n",
            stderr="",
        )
        with mock.patch.object(release_preflight_module.subprocess, "run", return_value=completed):
            leaks = release_preflight_module.find_tracked_runtime_leaks(PROJECT_ROOT)
        self.assertEqual(leaks, ["config_8830.json", "tmp/runtime-8820.log", "build/output.txt"])

    def test_main_uses_temporary_output_dir_when_default_output_is_not_writable(self):
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            write_tree(root)
            args = mock.Mock(
                root=str(root),
                version="0.3.0",
                allow_missing_public_links=False,
                skip_tests=True,
                skip_build=False,
            )
            commands: list[list[str]] = []
            with mock.patch.object(release_preflight_module, "parse_args", return_value=args):
                with mock.patch.object(release_preflight_module, "gather_failures", return_value=[]):
                    with mock.patch.object(release_preflight_module, "directory_supports_writes", return_value=False):
                        with mock.patch.object(release_preflight_module, "run_checked", side_effect=lambda cmd, _root: commands.append(cmd)):
                            with mock.patch("sys.stderr", new_callable=io.StringIO) as stderr:
                                release_preflight_module.main()
            self.assertEqual(len(commands), 2)
            build_cmd, verify_cmd = commands
            output_dir = build_cmd[build_cmd.index("--output-dir") + 1]
            dist_dir = verify_cmd[verify_cmd.index("--dist-dir") + 1]
            self.assertEqual(output_dir, dist_dir)
            self.assertTrue(Path(output_dir).is_absolute())
            self.assertNotEqual(Path(output_dir).name, "dist-preflight")
            self.assertIn("temporary preflight output dir", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
