# External Test Environments

This project currently treats external test machines as publish-readiness targets, not as part of the repo itself. Credentials stay outside the repository.

The example environment file under `examples/` uses placeholders only. Replace them locally when running smoke tests.

## Ubuntu SSH target

Use the Linux host to validate that the portable release archive works on a clean machine.

Example:

```bash
python3 scripts/run_remote_linux_smoke.py \
  --ssh user@linux-host \
  --identity-file ~/.ssh/id_ed25519 \
  --artifact dist/ai-proxy-hub-0.3.2.tar.gz
```

What it verifies:

- archive upload works
- archive extracts cleanly
- `python3 -m ai_proxy_hub --version` runs on the remote host
- `python3 -m ai_proxy_hub --print-paths` resolves the embedded `web/` directory
- the remote service can boot with `--serve` and return a healthy `/health` response on a loopback port

Recommended extra manual checks on the Linux host:

- start `python3 -m ai_proxy_hub --serve`
- confirm the Web UI opens from a browser
- confirm one real upstream request succeeds

Useful options:

- `--identity-file` to pass a dedicated SSH key
- `--ssh-option` repeated for custom SSH settings such as host key policy or jump-host configuration
- `--runtime-port` if the default smoke port is occupied on the remote machine
- `--skip-runtime-check` if you only want archive extraction and metadata verification

## Windows 11 RDP target

The Windows guest can be a virtual machine. It does not need to be a physical PC, as long as it is reachable over RDP from the maintainer network. It is best used for interactive checks that are hard to automate without adding dependencies.

Recommended manual checklist:

1. Copy the `.zip` release artifact to the VM.
2. Extract it to a non-admin directory.
3. Open PowerShell in the extracted directory.
4. Run `py -3 -m ai_proxy_hub --version`.
5. Run `py -3 -m ai_proxy_hub --serve`.
6. Open the Web UI and confirm the dashboard renders correctly.
7. Optionally run `py -3 -m ai_proxy_hub` once to verify the interactive CLI on Windows.
8. Verify one Codex / Claude / Gemini path from the local machine or from the VM itself.

## Credential policy

- Keep SSH targets, usernames, passwords, and RDP credentials in your password manager or local shell profile.
- Never commit lab credentials to the repository, release notes, or example config files.
