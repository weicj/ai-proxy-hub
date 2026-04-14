import importlib.util
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SMOKE_SPEC = importlib.util.spec_from_file_location(
    "remote_linux_smoke_module", PROJECT_ROOT / "scripts" / "run_remote_linux_smoke.py"
)
assert SMOKE_SPEC and SMOKE_SPEC.loader
remote_linux_smoke_module = importlib.util.module_from_spec(SMOKE_SPEC)
SMOKE_SPEC.loader.exec_module(remote_linux_smoke_module)


class RemoteLinuxSmokeTest(unittest.TestCase):
    def test_build_ssh_common_args_includes_identity_and_options(self):
        args = remote_linux_smoke_module.build_ssh_common_args(
            "~/id_demo",
            ["StrictHostKeyChecking=no", "UserKnownHostsFile=/dev/null"],
        )
        self.assertEqual(args[0], "-i")
        self.assertIn("IdentitiesOnly=yes", args)
        self.assertEqual(args.count("-o"), 3)
        self.assertIn("StrictHostKeyChecking=no", args)
        self.assertIn("UserKnownHostsFile=/dev/null", args)

    def test_build_remote_script_includes_runtime_health_check(self):
        args = SimpleNamespace(
            remote_dir="/tmp/demo",
            python="python3",
            bind_host="127.0.0.1",
            runtime_port=18987,
            skip_runtime_check=False,
        )
        script = remote_linux_smoke_module.build_remote_script(args, "ai-proxy-hub-demo.tar.gz")
        self.assertIn("python3 -m ai_proxy_hub --version", script)
        self.assertIn("python3 -m ai_proxy_hub --print-paths", script)
        self.assertIn("--serve --host 127.0.0.1 --port 18987", script)
        self.assertIn("http://127.0.0.1:18987/health", script)
        self.assertIn("trap cleanup EXIT INT TERM", script)

    def test_main_uses_identity_args_for_scp_and_ssh(self):
        with tempfile.TemporaryDirectory() as tempdir:
            artifact = Path(tempdir) / "ai-proxy-hub-0.3.0.tar.gz"
            artifact.write_text("stub", encoding="utf-8")
            parsed = SimpleNamespace(
                ssh="user@example-host",
                artifact=str(artifact),
                remote_dir="/tmp/remote-smoke",
                python="python3",
                identity_file="~/.ssh/id_ed25519",
                ssh_option=["StrictHostKeyChecking=no"],
                bind_host="127.0.0.1",
                runtime_port=19001,
                skip_runtime_check=True,
            )
            with mock.patch.object(remote_linux_smoke_module, "parse_args", return_value=parsed):
                with mock.patch.object(remote_linux_smoke_module, "run") as run_mock:
                    remote_linux_smoke_module.main()
        self.assertEqual(run_mock.call_count, 3)
        prepare_cmd = run_mock.call_args_list[0].args[0]
        scp_cmd = run_mock.call_args_list[1].args[0]
        ssh_cmd = run_mock.call_args_list[2].args[0]
        self.assertEqual(prepare_cmd[0], "ssh")
        self.assertEqual(scp_cmd[0], "scp")
        self.assertEqual(ssh_cmd[0], "ssh")
        self.assertIn("mkdir -p /tmp/remote-smoke", prepare_cmd[-1])
        self.assertIn("user@example-host:/tmp/remote-smoke/ai-proxy-hub-0.3.0.tar.gz", scp_cmd)
        self.assertIn("user@example-host", ssh_cmd)
        self.assertIn("IdentitiesOnly=yes", scp_cmd)
        self.assertIn("StrictHostKeyChecking=no", ssh_cmd)


if __name__ == "__main__":
    unittest.main()
