#!/usr/bin/env python3
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import os
import shutil
import subprocess
import tarfile
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_REPO_ROOT = Path.home() / "Develop" / "AI Proxy Hub" / "apt-repo"
DEFAULT_DISTRIBUTION = "stable"
DEFAULT_COMPONENT = "main"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync a .deb artifact into a simple APT repository tree")
    parser.add_argument("--deb", required=True, help="Path to the built .deb artifact")
    parser.add_argument("--repo-root", default=str(DEFAULT_REPO_ROOT), help="APT repository root")
    parser.add_argument("--distribution", default=DEFAULT_DISTRIBUTION, help="APT distribution, for example stable")
    parser.add_argument("--component", default=DEFAULT_COMPONENT, help="APT component, for example main")
    parser.add_argument("--gpg-key-id", help="Optional GPG key ID used to sign Release into Release.gpg and InRelease")
    parser.add_argument("--gpg-homedir", help="Optional GPG home directory used when signing")
    parser.add_argument("--gpg-binary", default="gpg", help="GPG executable used when signing")
    parser.add_argument("--gpg-passphrase-env", help="Optional environment variable that contains the GPG passphrase")
    parser.add_argument("--gpg-passphrase-file", help="Optional file containing the GPG passphrase")
    parser.add_argument("--export-public-key", action="store_true", help="Export the signing public key into the repository tree when signing is enabled")
    parser.add_argument("--public-key-dir", help="Directory for exported public key files; defaults to <repo-root>/public")
    parser.add_argument("--public-key-name", default="ai-proxy-hub-archive-keyring", help="Base filename used when exporting the public key")
    return parser.parse_args()


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def md5_of(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_deb_control_fields(deb_path: Path) -> dict[str, str]:
    if shutil.which("dpkg-deb") is None:
        return read_deb_control_fields_pure_python(deb_path)
    result = subprocess.run(
        ["dpkg-deb", "-f", str(deb_path)],
        check=True,
        capture_output=True,
        text=True,
    )
    fields: dict[str, str] = {}
    current_key: str | None = None
    for raw_line in result.stdout.splitlines():
        if raw_line.startswith(" ") and current_key:
            fields[current_key] = fields[current_key] + "\n" + raw_line[1:]
            continue
        if ":" not in raw_line:
            continue
        key, value = raw_line.split(":", 1)
        current_key = key.strip()
        fields[current_key] = value.strip()
    return fields


def _iter_ar_members(archive_bytes: bytes) -> list[tuple[str, bytes]]:
    if not archive_bytes.startswith(b"!<arch>\n"):
        raise RuntimeError("Unsupported .deb archive: missing ar magic")
    offset = 8
    members: list[tuple[str, bytes]] = []
    while offset + 60 <= len(archive_bytes):
        header = archive_bytes[offset : offset + 60]
        offset += 60
        name = header[:16].decode("utf-8", errors="replace").strip().rstrip("/")
        size_text = header[48:58].decode("ascii", errors="replace").strip()
        file_size = int(size_text or "0")
        data = archive_bytes[offset : offset + file_size]
        members.append((name, data))
        offset += file_size
        if offset % 2 == 1:
            offset += 1
    return members


def read_deb_control_fields_pure_python(deb_path: Path) -> dict[str, str]:
    members = _iter_ar_members(deb_path.read_bytes())
    control_member = next(
        (data for name, data in members if name.startswith("control.tar")),
        None,
    )
    if control_member is None:
        raise RuntimeError(f"Could not locate control.tar.* inside {deb_path}")
    with tarfile.open(fileobj=io.BytesIO(control_member), mode="r:*") as archive:
        control_file = next(
            (
                member
                for member in archive.getmembers()
                if member.name in {"control", "./control"}
            ),
            None,
        )
        if control_file is None:
            raise RuntimeError(f"Could not locate control file inside {deb_path}")
        extracted = archive.extractfile(control_file)
        if extracted is None:
            raise RuntimeError(f"Could not read control file inside {deb_path}")
        control_text = extracted.read().decode("utf-8", errors="replace")

    fields: dict[str, str] = {}
    current_key: str | None = None
    for raw_line in control_text.splitlines():
        if raw_line.startswith(" ") and current_key:
            fields[current_key] = fields[current_key] + "\n" + raw_line[1:]
            continue
        if ":" not in raw_line:
            continue
        key, value = raw_line.split(":", 1)
        current_key = key.strip()
        fields[current_key] = value.strip()
    return fields


def pool_target_path(repo_root: Path, deb_path: Path, package_name: str, component: str) -> Path:
    first_letter = (package_name[:1] or "a").lower()
    return repo_root / "pool" / component / first_letter / package_name / deb_path.name


def package_entry(relative_deb_path: Path, deb_path: Path, control_fields: dict[str, str]) -> str:
    lines = []
    preferred_keys = [
        "Package",
        "Version",
        "Section",
        "Priority",
        "Architecture",
        "Maintainer",
        "Depends",
        "Description",
    ]
    for key in preferred_keys:
        value = control_fields.get(key)
        if value:
            formatted_value = value.replace("\n", "\n ")
            lines.append(f"{key}: {formatted_value}")
    lines.append(f"Filename: {relative_deb_path.as_posix()}")
    lines.append(f"Size: {deb_path.stat().st_size}")
    lines.append(f"MD5sum: {md5_of(deb_path)}")
    lines.append(f"SHA256: {sha256_of(deb_path)}")
    return "\n".join(lines) + "\n"


def release_text(
    distribution: str,
    component: str,
    repo_root: Path,
    packages_path: Path,
    packages_gz_path: Path,
) -> str:
    paths = [packages_path, packages_gz_path]
    md5_lines = []
    sha256_lines = []
    for path in paths:
        relative = path.as_posix()
        file_path = repo_root / path
        md5_lines.append(f" {md5_of(file_path)} {file_path.stat().st_size:>16} {relative}")
        sha256_lines.append(f" {sha256_of(file_path)} {file_path.stat().st_size:>16} {relative}")
    return "\n".join(
        [
            "Origin: AI Proxy Hub",
            "Label: AI Proxy Hub",
            f"Suite: {distribution}",
            f"Codename: {distribution}",
            f"Date: {datetime.now(timezone.utc).strftime('%a, %d %b %Y %H:%M:%S %Z')}",
            "Architectures: all",
            f"Components: {component}",
            "Description: AI Proxy Hub APT repository",
            "MD5Sum:",
            *md5_lines,
            "SHA256:",
            *sha256_lines,
            "",
        ]
    )


def apt_readme(distribution: str, component: str) -> str:
    return "\n".join(
        [
            "# APT Staging for AI Proxy Hub",
            "",
            "This is an APT repository staging tree intended for release preparation and local testing.",
            "",
            "For local testing on Debian/Ubuntu you can point `sources.list.d` at it with a trusted local source, for example:",
            "",
            "```bash",
            f"deb [trusted=yes] file:/absolute/path/to/apt-repo {distribution} {component}",
            "sudo apt update",
            "sudo apt install ai-proxy-hub",
            "```",
            "",
            "If you sign the repository and export a keyring into `public/`, you can also test it without `trusted=yes`:",
            "",
            "```bash",
            "sudo install -Dm644 /absolute/path/to/apt-repo/public/ai-proxy-hub-archive-keyring.gpg /usr/share/keyrings/ai-proxy-hub-archive-keyring.gpg",
            f"echo 'deb [signed-by=/usr/share/keyrings/ai-proxy-hub-archive-keyring.gpg] file:/absolute/path/to/apt-repo {distribution} {component}' | sudo tee /etc/apt/sources.list.d/ai-proxy-hub.list",
            "sudo apt update",
            "sudo apt install ai-proxy-hub",
            "```",
            "",
            "For public distribution you should also generate `Release.gpg` and `InRelease` with a trusted signing key.",
            "",
            "Do not advertise a public `apt install` command until this repository is hosted and signed.",
            "",
        ]
    )


def build_gpg_command(
    gpg_binary: str,
    key_id: str,
    output_path: Path,
    input_path: Path,
    *,
    clearsign: bool = False,
    homedir: str | None = None,
    passphrase: str | None = None,
) -> list[str]:
    command = [gpg_binary]
    if homedir:
        command.extend(["--homedir", homedir])
    if passphrase:
        command.extend(["--pinentry-mode", "loopback", "--passphrase-fd", "0"])
    command.extend(["--batch", "--yes", "--local-user", key_id, "--output", str(output_path)])
    command.append("--clearsign" if clearsign else "--detach-sign")
    command.append(str(input_path))
    return command


def gpg_run_kwargs(passphrase: str | None) -> dict[str, object]:
    if not passphrase:
        return {}
    return {
        "input": passphrase + "\n",
        "text": True,
    }


def sign_release_files(
    repo_root: Path,
    distribution: str,
    key_id: str,
    *,
    gpg_binary: str = "gpg",
    homedir: str | None = None,
    passphrase: str | None = None,
) -> tuple[Path, Path]:
    release_path = repo_root / "dists" / distribution / "Release"
    release_gpg_path = release_path.with_name("Release.gpg")
    inrelease_path = release_path.with_name("InRelease")
    subprocess.run(
        build_gpg_command(gpg_binary, key_id, release_gpg_path, release_path, homedir=homedir, passphrase=passphrase),
        check=True,
        **gpg_run_kwargs(passphrase),
    )
    subprocess.run(
        build_gpg_command(
            gpg_binary,
            key_id,
            inrelease_path,
            release_path,
            clearsign=True,
            homedir=homedir,
            passphrase=passphrase,
        ),
        check=True,
        **gpg_run_kwargs(passphrase),
    )
    return release_gpg_path, inrelease_path


def export_public_key_files(
    key_id: str,
    output_dir: Path,
    *,
    key_name: str,
    gpg_binary: str = "gpg",
    homedir: str | None = None,
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    ascii_path = output_dir / f"{key_name}.asc"
    binary_path = output_dir / f"{key_name}.gpg"
    export_command = [gpg_binary]
    if homedir:
        export_command.extend(["--homedir", homedir])

    armored = subprocess.run(
        [*export_command, "--armor", "--export", key_id],
        check=True,
        capture_output=True,
    )
    ascii_path.write_bytes(armored.stdout)

    binary_export = subprocess.run(
        [*export_command, "--export", key_id],
        check=True,
        capture_output=True,
    )
    dearmored = subprocess.run(
        [*export_command, "--dearmor"],
        check=True,
        input=binary_export.stdout,
        capture_output=True,
    )
    binary_path.write_bytes(dearmored.stdout)
    return ascii_path, binary_path


def resolve_gpg_passphrase(*, env_name: str | None = None, file_path: str | None = None) -> str | None:
    if env_name:
        value = os.environ.get(env_name)
        if value is None:
            raise RuntimeError(f"GPG passphrase environment variable is not set: {env_name}")
        return value
    if file_path:
        return Path(file_path).read_text(encoding="utf-8").rstrip("\r\n")
    return None


def sync_apt_repo(
    deb_path: Path,
    repo_root: Path,
    distribution: str,
    component: str,
    *,
    gpg_key_id: str | None = None,
    gpg_homedir: str | None = None,
    gpg_binary: str = "gpg",
    gpg_passphrase: str | None = None,
    export_public_key: bool = False,
    public_key_dir: Path | None = None,
    public_key_name: str = "ai-proxy-hub-archive-keyring",
) -> Path:
    deb_path = deb_path.resolve()
    repo_root = repo_root.resolve()
    if not deb_path.exists():
        raise FileNotFoundError(f"Missing .deb artifact: {deb_path}")
    control_fields = read_deb_control_fields(deb_path)
    package_name = control_fields.get("Package")
    if not package_name:
        raise RuntimeError("dpkg-deb -f output did not include Package")

    target_deb_path = pool_target_path(repo_root, deb_path, package_name, component)
    target_deb_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(deb_path, target_deb_path)

    packages_dir = repo_root / "dists" / distribution / component / "binary-all"
    packages_dir.mkdir(parents=True, exist_ok=True)
    relative_deb_path = target_deb_path.relative_to(repo_root)
    packages_path = packages_dir / "Packages"
    packages_content = package_entry(relative_deb_path, target_deb_path, control_fields)
    packages_path.write_text(packages_content, encoding="utf-8")
    packages_gz_path = packages_dir / "Packages.gz"
    with gzip.open(packages_gz_path, "wt", encoding="utf-8") as handle:
        handle.write(packages_content)

    release_path = repo_root / "dists" / distribution / "Release"
    release_path.parent.mkdir(parents=True, exist_ok=True)
    release_path.write_text(
        release_text(
            distribution,
            component,
            repo_root,
            packages_path.relative_to(repo_root),
            packages_gz_path.relative_to(repo_root),
        ),
        encoding="utf-8",
    )
    if gpg_key_id:
        sign_release_files(
            repo_root,
            distribution,
            gpg_key_id,
            gpg_binary=gpg_binary,
            homedir=gpg_homedir,
            passphrase=gpg_passphrase,
        )
        if export_public_key:
            export_public_key_files(
                gpg_key_id,
                (public_key_dir or (repo_root / "public")).resolve(),
                key_name=public_key_name,
                gpg_binary=gpg_binary,
                homedir=gpg_homedir,
            )

    readme_path = repo_root / "README.md"
    readme_path.write_text(apt_readme(distribution, component), encoding="utf-8")
    gitignore_path = repo_root / ".gitignore"
    if not gitignore_path.exists():
        gitignore_path.write_text(".DS_Store\n", encoding="utf-8")
    return repo_root


def main() -> None:
    args = parse_args()
    gpg_passphrase = resolve_gpg_passphrase(
        env_name=str(args.gpg_passphrase_env) if args.gpg_passphrase_env else None,
        file_path=str(args.gpg_passphrase_file) if args.gpg_passphrase_file else None,
    )
    repo_root = sync_apt_repo(
        Path(args.deb),
        Path(args.repo_root),
        str(args.distribution),
        str(args.component),
        gpg_key_id=str(args.gpg_key_id) if args.gpg_key_id else None,
        gpg_homedir=str(args.gpg_homedir) if args.gpg_homedir else None,
        gpg_binary=str(args.gpg_binary),
        gpg_passphrase=gpg_passphrase,
        export_public_key=bool(args.export_public_key),
        public_key_dir=Path(args.public_key_dir) if args.public_key_dir else None,
        public_key_name=str(args.public_key_name),
    )
    print(repo_root)


if __name__ == "__main__":
    main()
