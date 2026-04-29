#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path


APP_NAME = "AI Proxy Hub"
APP_SLUG = "ai-proxy-hub"
DEFAULT_SIGNING_ROOT = Path.home() / "Develop" / "AI Proxy Hub" / "signing"
DEFAULT_COMMENT = f"{APP_NAME} APT Repository"
DEFAULT_EXPIRE_DATE = "2y"
DEFAULT_PUBLIC_KEY_NAME = f"{APP_SLUG}-archive-keyring"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bootstrap and export a dedicated GPG key for AI Proxy Hub APT signing")
    parser.add_argument("--signing-root", default=str(DEFAULT_SIGNING_ROOT), help="Root directory for signing metadata and helper files")
    parser.add_argument("--gpg-home", help="Override GPG home directory; defaults to <signing-root>/gpg")
    parser.add_argument("--public-key-dir", help="Directory where exported public key files should be written")
    parser.add_argument("--public-key-name", default=DEFAULT_PUBLIC_KEY_NAME, help="Base filename used for exported keyring files")
    parser.add_argument("--name-real", help="Real name for the signing UID")
    parser.add_argument("--name-email", help="Email address for the signing UID")
    parser.add_argument("--name-comment", default=DEFAULT_COMMENT, help="Comment for the signing UID")
    parser.add_argument("--expire-date", default=DEFAULT_EXPIRE_DATE, help="Key expiry, for example 2y or 365d")
    parser.add_argument("--key-id", help="Reuse an existing secret key ID if multiple keys are present")
    parser.add_argument("--gpg-binary", default="gpg", help="GPG executable")
    parser.add_argument("--passphrase", help="Optional passphrase used for non-interactive key generation")
    parser.add_argument("--no-protection", action="store_true", help="Generate the key without a passphrase")
    parser.add_argument("--skip-generate", action="store_true", help="Do not generate a key if no secret key exists in the target GPG home")
    parser.add_argument("--metadata-file", help="Optional path for a JSON summary file")
    return parser.parse_args()


def run_gpg(gpg_binary: str, *args: str, homedir: Path | None = None, input_text: str | None = None, capture_output: bool = True) -> subprocess.CompletedProcess[str]:
    command = [gpg_binary]
    if homedir is not None:
        command.extend(["--homedir", str(homedir)])
    command.extend(args)
    return subprocess.run(
        command,
        check=True,
        capture_output=capture_output,
        text=True,
        input=input_text,
    )


def detect_git_identity() -> tuple[str, str]:
    def read_config(key: str) -> str:
        try:
            result = subprocess.run(
                ["git", "config", "--global", "--get", key],
                check=True,
                capture_output=True,
                text=True,
            )
        except (FileNotFoundError, subprocess.CalledProcessError):
            return ""
        return result.stdout.strip()

    return read_config("user.name"), read_config("user.email")


def build_batch_config(
    *,
    name_real: str,
    name_email: str,
    name_comment: str,
    expire_date: str,
    no_protection: bool,
    passphrase: str = "",
) -> str:
    lines = [
        "Key-Type: RSA",
        "Key-Length: 4096",
        "Key-Usage: sign",
        f"Name-Real: {name_real}",
    ]
    if name_comment:
        lines.append(f"Name-Comment: {name_comment}")
    lines.append(f"Name-Email: {name_email}")
    lines.append(f"Expire-Date: {expire_date}")
    if no_protection:
        lines.append("%no-protection")
    elif passphrase:
        lines.append(f"Passphrase: {passphrase}")
    lines.append("%commit")
    return "\n".join(lines) + "\n"


def list_secret_keys(gpg_binary: str, homedir: Path) -> str:
    result = run_gpg(gpg_binary, "--batch", "--with-colons", "--keyid-format", "LONG", "--list-secret-keys", homedir=homedir)
    return result.stdout


def extract_primary_secret_key(colon_output: str, requested_key_id: str = "") -> dict[str, str]:
    selected: dict[str, str] = {}
    current_key_id = ""
    current_fingerprint = ""
    current_uid = ""

    def maybe_select() -> None:
        nonlocal selected
        if not current_key_id or not current_fingerprint:
            return
        if requested_key_id and current_key_id != requested_key_id and not current_fingerprint.endswith(requested_key_id):
            return
        if not selected:
            selected = {
                "key_id": current_key_id,
                "fingerprint": current_fingerprint,
                "uid": current_uid,
            }

    for raw_line in colon_output.splitlines():
        parts = raw_line.split(":")
        record_type = parts[0]
        if record_type == "sec":
            maybe_select()
            current_key_id = parts[4]
            current_fingerprint = ""
            current_uid = ""
            continue
        if record_type == "fpr" and current_key_id and not current_fingerprint:
            current_fingerprint = parts[9]
            continue
        if record_type == "uid" and current_key_id and not current_uid:
            current_uid = parts[9]
            continue
    maybe_select()
    return selected


def ensure_signing_key(
    *,
    gpg_binary: str,
    homedir: Path,
    key_id: str,
    name_real: str,
    name_email: str,
    name_comment: str,
    expire_date: str,
    no_protection: bool,
    passphrase: str,
    allow_generate: bool,
) -> dict[str, str]:
    colon_output = list_secret_keys(gpg_binary, homedir)
    existing = extract_primary_secret_key(colon_output, key_id)
    if existing:
        return existing
    if not allow_generate:
        raise SystemExit("No matching secret key found and generation is disabled.")
    if not no_protection and not passphrase:
        raise SystemExit("Provide --no-protection or --passphrase when generating a new signing key.")
    batch_config = build_batch_config(
        name_real=name_real,
        name_email=name_email,
        name_comment=name_comment,
        expire_date=expire_date,
        no_protection=no_protection,
        passphrase=passphrase,
    )
    extra_args: list[str] = ["--batch", "--pinentry-mode", "loopback", "--generate-key"]
    run_gpg(gpg_binary, *extra_args, homedir=homedir, input_text=batch_config)
    created = extract_primary_secret_key(list_secret_keys(gpg_binary, homedir), key_id)
    if not created:
        raise RuntimeError("GPG key generation finished but no secret key could be detected.")
    return created


def export_public_key_files(
    gpg_binary: str,
    key_id: str,
    output_dir: Path,
    *,
    key_name: str,
    homedir: Path | None = None,
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    ascii_path = output_dir / f"{key_name}.asc"
    binary_path = output_dir / f"{key_name}.gpg"
    ascii_export = run_gpg(gpg_binary, "--armor", "--export", key_id, homedir=homedir)
    ascii_path.write_text(ascii_export.stdout, encoding="utf-8")
    binary_export = subprocess.run(
        [gpg_binary, *(["--homedir", str(homedir)] if homedir is not None else []), "--export", key_id],
        check=True,
        capture_output=True,
    )
    dearmor = subprocess.run(
        [gpg_binary, *(["--homedir", str(homedir)] if homedir is not None else []), "--dearmor"],
        check=True,
        input=binary_export.stdout,
        capture_output=True,
    )
    binary_path.write_bytes(dearmor.stdout)
    return ascii_path, binary_path


def copy_revocation_certificate(signing_root: Path, gpg_home: Path, fingerprint: str) -> Path | None:
    source = gpg_home / "openpgp-revocs.d" / f"{fingerprint}.rev"
    if not source.exists():
        return None
    target = signing_root / f"{APP_SLUG}-apt-revocation.rev"
    shutil.copy2(source, target)
    return target


def default_metadata_path(signing_root: Path) -> Path:
    return signing_root / "apt-signing.json"


def main() -> None:
    args = parse_args()
    signing_root = Path(args.signing_root).expanduser().resolve()
    gpg_home = Path(args.gpg_home).expanduser().resolve() if args.gpg_home else (signing_root / "gpg").resolve()
    public_key_dir = (
        Path(args.public_key_dir).expanduser().resolve()
        if args.public_key_dir
        else (Path.home() / "Develop" / "AI Proxy Hub" / "apt-repo" / "public").resolve()
    )
    metadata_path = Path(args.metadata_file).expanduser().resolve() if args.metadata_file else default_metadata_path(signing_root)
    signing_root.mkdir(parents=True, exist_ok=True)
    gpg_home.mkdir(parents=True, exist_ok=True)
    gpg_home.chmod(0o700)

    git_name, git_email = detect_git_identity()
    name_real = args.name_real or git_name or "AI Proxy Hub Maintainer"
    name_email = args.name_email or git_email or ""
    if not name_email:
        raise SystemExit("Provide --name-email or configure git user.email before bootstrapping APT signing.")

    key_info = ensure_signing_key(
        gpg_binary=str(args.gpg_binary),
        homedir=gpg_home,
        key_id=str(args.key_id or ""),
        name_real=name_real,
        name_email=name_email,
        name_comment=str(args.name_comment),
        expire_date=str(args.expire_date),
        no_protection=bool(args.no_protection),
        passphrase=str(args.passphrase or ""),
        allow_generate=not args.skip_generate,
    )
    ascii_path, binary_path = export_public_key_files(
        str(args.gpg_binary),
        key_info["fingerprint"],
        public_key_dir,
        key_name=str(args.public_key_name),
        homedir=gpg_home,
    )
    revocation_path = copy_revocation_certificate(signing_root, gpg_home, key_info["fingerprint"])

    metadata = {
        "app_name": APP_NAME,
        "signing_root": str(signing_root),
        "gpg_home": str(gpg_home),
        "key_id": key_info["key_id"],
        "fingerprint": key_info["fingerprint"],
        "uid": key_info.get("uid", ""),
        "public_key_ascii": str(ascii_path),
        "public_key_binary": str(binary_path),
        "revocation_certificate": str(revocation_path) if revocation_path else "",
    }
    metadata_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(json.dumps(metadata, indent=2, ensure_ascii=True))


if __name__ == "__main__":
    main()
