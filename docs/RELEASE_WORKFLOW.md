# AI Proxy Hub Release Workflow

This project uses two parallel directory trees on the maintainer machine:

- `/Users/max/ai-proxy-hub`
  Development workspace. All coding, debugging, and local verification happen here.
- `~/Develop/AI Proxy Hub/releases/<version>`
  Local release workspace. This is the staging area for source snapshots, release artifacts, and publish notes.

## Recommended flow

1. Verify the development workspace.

```bash
python3 scripts/release_preflight.py --version 0.3.0
```

2. Sync the current source into the local release workspace.

```bash
python3 scripts/sync_release_snapshot.py --version 0.3.0
```

3. Copy or rebuild artifacts into the release workspace.

Suggested layout:

- `releases/v0.3.0/source-snapshot`
- `releases/v0.3.0/artifacts/github-release`
- `releases/v0.3.0/artifacts/homebrew`
- `releases/v0.3.0/artifacts/winget`
- `releases/v0.3.0/artifacts/linux`

4. Run external smoke tests.

- Linux: use [run_remote_linux_smoke.py](/Users/max/ai-proxy-hub/scripts/run_remote_linux_smoke.py) with `--identity-file` and optional repeated `--ssh-option` values when the remote host needs an explicit SSH key or custom SSH transport settings
- Windows: use the checklist in [EXTERNAL_TEST_ENV.md](/Users/max/ai-proxy-hub/docs/EXTERNAL_TEST_ENV.md); a reachable Windows VM is an acceptable release target

5. Update release notes.

- `releases/<version>/notes/RELEASE_STATUS.md`
- `releases/<version>/notes/RELEASE_CHECKLIST.md`
- `releases/<version>/notes/PUBLISH_LOG.md`

6. Publish only after the remaining blockers are closed.

Current hard blockers:

- No canonical git repository / tag baseline yet

## Notes

- The release snapshot intentionally excludes local runtime config, logs, temp files, and state files.
- Do not store real SSH passwords, RDP passwords, or API keys in this repository.
- If the local release root differs from the default, pass `--release-root` explicitly to the sync script.
