# AI Proxy Hub Release Workflow

[![Release Doc](https://img.shields.io/badge/Workflow-release-2563eb)](../README.md)
[![Homebrew](https://img.shields.io/badge/Homebrew-available-16a34a)](https://github.com/weicj/homebrew-aiproxyhub)
![winget](https://img.shields.io/badge/winget-planned-6b7280)
![APT](https://img.shields.io/badge/APT-planned-6b7280)

This project uses two parallel directory trees on the maintainer machine:

- `/Users/max/ai-proxy-hub`
  Development workspace. All coding, debugging, and local verification happen here.
- `~/Develop/AI Proxy Hub/releases/<version>`
  Local release workspace. This is the staging area for source snapshots, release artifacts, and publish notes.

## Recommended flow

1. Verify the development workspace.

```bash
python3 scripts/release_preflight.py --version 0.3.2
```

2. Sync the current source into the local release workspace.

```bash
python3 scripts/sync_release_snapshot.py --version 0.3.2
```

3. Copy or rebuild artifacts into the release workspace.

Suggested layout:

- `releases/v0.3.2/source-snapshot`
- `releases/v0.3.2/artifacts/github-release`
- `releases/v0.3.2/artifacts/homebrew`
- `releases/v0.3.2/artifacts/winget`
- `releases/v0.3.2/artifacts/linux`

4. Sync the generated Homebrew formula into the tap checkout.

```bash
python3 scripts/build_release.py \
  --version 0.3.2 \
  --output-dir dist-release \
  --download-base-url https://github.com/weicj/ai-proxy-hub/releases/download/v0.3.2 \
  --homepage https://github.com/weicj/ai-proxy-hub

python3 scripts/sync_homebrew_tap.py \
  --formula dist-release/release-metadata/ai-proxy-hub.rb \
  --tap-root ~/Develop/AI\ Proxy\ Hub/homebrew-aiproxyhub \
  --tap-repo weicj/homebrew-aiproxyhub \
  --version 0.3.2
```

5. Stage the generated winget manifests into a local `winget-pkgs` checkout or staging tree.

```bash
python3 scripts/sync_winget_manifest.py \
  --source-dir dist-release/release-metadata \
  --repo-root ~/Develop/AI\ Proxy\ Hub/winget-staging \
  --package-id AIProxyHub.AIProxyHub \
  --version 0.3.2
```

6. If a `.deb` artifact exists, sync it into a local APT repository tree.

```bash
python3 scripts/sync_apt_repo.py \
  --deb dist-release/ai-proxy-hub_0.3.2_all.deb \
  --repo-root ~/Develop/AI\ Proxy\ Hub/apt-repo \
  --distribution stable \
  --component main
```

If you are on macOS or another non-Debian host, you can build the `.deb` in a Linux container first:

```bash
python3 scripts/build_deb_in_container.py \
  --version 0.3.2 \
  --output-dir dist-container \
  --download-base-url https://github.com/weicj/ai-proxy-hub/releases/download/v0.3.2 \
  --homepage https://github.com/weicj/ai-proxy-hub
```

This requires a running Docker daemon on the local machine.
The helper defaults to a Python-based Debian image, so the host does not need `dpkg-deb`.

If you are preparing a public APT repository, bootstrap a dedicated signing key first:

```bash
python3 scripts/bootstrap_apt_signing.py \
  --no-protection
```

`--no-protection` is appropriate for local staging. For a long-lived public signing key, prefer `--passphrase`.

Then sign the staged repository and export the public key files:

```bash
python3 scripts/sync_apt_repo.py \
  --deb dist-container/ai-proxy-hub_0.3.2_all.deb \
  --repo-root ~/Develop/AI\ Proxy\ Hub/apt-repo \
  --distribution stable \
  --component main \
  --gpg-key-id YOUR_KEY_ID \
  --gpg-homedir ~/Develop/AI\ Proxy\ Hub/signing/gpg \
  --export-public-key
```

This produces:

- `apt-repo/dists/stable/Release.gpg`
- `apt-repo/dists/stable/InRelease`
- `apt-repo/public/ai-proxy-hub-archive-keyring.asc`
- `apt-repo/public/ai-proxy-hub-archive-keyring.gpg`

To publish the staged repository on GitHub Pages, configure:

- repository variable: `APT_GPG_KEY_ID`
- repository secret: `APT_GPG_PRIVATE_KEY`
- optional repository secret: `APT_GPG_PASSPHRASE`

You can export the private key for GitHub Secrets from the local signing keyring with:

```bash
/opt/homebrew/bin/gpg \
  --homedir ~/Develop/AI\ Proxy\ Hub/signing/gpg \
  --armor \
  --export-secret-keys YOUR_KEY_ID
```

Then enable GitHub Pages with `GitHub Actions` as the source and run the `Publish APT Repository` workflow. The resulting repository URL will follow the project Pages URL, for example:

```text
https://weicj.github.io/ai-proxy-hub
```

7. Run external smoke tests.

- Linux: use [run_remote_linux_smoke.py](/Users/max/ai-proxy-hub/scripts/run_remote_linux_smoke.py) with `--identity-file` and optional repeated `--ssh-option` values when the remote host needs an explicit SSH key or custom SSH transport settings
- Windows: use the checklist in [EXTERNAL_TEST_ENV.md](/Users/max/ai-proxy-hub/docs/EXTERNAL_TEST_ENV.md); a reachable Windows VM is an acceptable release target

8. Update release notes.

- `releases/<version>/notes/RELEASE_STATUS.md`
- `releases/<version>/notes/RELEASE_CHECKLIST.md`
- `releases/<version>/notes/PUBLISH_LOG.md`

9. Publish only after the remaining blockers are closed.

## Notes

- The release snapshot intentionally excludes local runtime config, logs, temp files, and state files.
- Do not store real SSH passwords, RDP passwords, or API keys in this repository.
- If the local release root differs from the default, pass `--release-root` explicitly to the sync script.
- Homebrew self-hosted taps do not require official review, but the tap repository must exist publicly before `brew install weicj/aiproxyhub/ai-proxy-hub` will work.
- winget becomes publicly installable only after the manifest is accepted into `microsoft/winget-pkgs`.
- APT becomes publicly installable only after the repository is hosted and signed; the local `apt-repo` tree is staging output, not a public feed by itself.
