# AI Proxy Hub FAQ

[![Docs](https://img.shields.io/badge/Docs-FAQ-2563eb)](../README.md)
[![Homebrew](https://img.shields.io/badge/Homebrew-preview-f59e0b)](https://github.com/weicj/homebrew-tap)
![winget](https://img.shields.io/badge/winget-planned-6b7280)
![APT](https://img.shields.io/badge/APT-planned-6b7280)

## What is AI Proxy Hub?

AI Proxy Hub is a local control layer for AI clients and upstream APIs. It provides one managed entrypoint, multiple routing strategies, subscription-aware availability handling, local API key management, and both Web and CLI control surfaces.

## Which clients and protocol families does it focus on?

The current project focus is:

- Codex
- Claude Code
- Gemini CLI

It currently exposes protocol-oriented workspaces for:

- OpenAI-compatible
- Claude / Anthropic
- Gemini

## Is it only for local use?

The primary design target is local or private-network use. LAN exposure can be enabled when needed, but the project is not positioned as a hardened public multi-tenant gateway.

## Does it require root or administrator permissions?

Not for normal runtime. The intended operating model is user-level execution with user-writable configuration paths.

Installation can still use elevated privileges when the platform expects them, such as:

- `sudo apt install ./ai-proxy-hub_<version>_all.deb`
- `sudo dpkg -i ai-proxy-hub_<version>_all.deb`

So the rule is: installation may use `sudo`, but routine operation should not depend on it.

## Can one local API key be limited to only one protocol?

Yes. Local keys can be scoped to specific protocol families.

## What routing modes are available?

The project currently supports:

- manual control
- priority routing
- round-robin routing
- latency-aware routing

## What does subscription-aware upstream control mean?

Each upstream can contain one or more subscription records. These can model:

- unlimited access
- periodic reset windows
- quota-style usage

This allows the router to distinguish between normal availability, temporary exhaustion, expiry, and later recovery windows.

## Can different protocols use different routing settings?

Yes. The project is organized around protocol workspaces, so routing behavior, local entry settings, and upstream ordering can differ by protocol.

## Does the project support both Web and terminal-based administration?

Yes. The Web dashboard and the interactive CLI are both first-class control surfaces.

## Can it be packaged and distributed?

Yes. The repository includes tooling for:

- portable `.tar.gz` and `.zip` artifacts
- optional `.deb` generation
- generated metadata for Homebrew and winget-oriented workflows

## Is the project already fully ready for package-manager publication?

Not yet. The release tooling has been substantially hardened, and the Homebrew tap is already public in preview form, but the broader public package-manager publication path is still being finalized.

## Which license does the project use?

Apache License 2.0.
