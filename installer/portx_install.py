#!/usr/bin/env python3
"""
PortX Installer — Step 1
Downloads the latest FRP client binary (frpc) from the official GitHub
Releases page and installs it to ~/Downloads/portx/frp.

Supported platforms:
  macOS  ARM64  (Apple Silicon)  → frp_*_darwin_arm64.tar.gz
  macOS  AMD64  (Intel)          → frp_*_darwin_amd64.tar.gz
  Linux  ARM64                   → frp_*_linux_arm64.tar.gz
  Linux  AMD64                   → frp_*_linux_amd64.tar.gz

Zero external Python dependencies (stdlib only).
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request
from pathlib import Path


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FRP_GITHUB_API = "https://api.github.com/repos/fatedier/frp/releases/latest"
INSTALL_DIR    = Path.home() / "Downloads" / "portx"
INSTALL_PATH   = INSTALL_DIR / "frp"

# Network timeout (seconds) for GitHub API and urllib fallback downloads
NETWORK_TIMEOUT = 30

# Maps (system, machine) → FRP asset suffix
PLATFORM_MAP: dict[tuple[str, str], str] = {
    ("darwin", "arm64"):   "darwin_arm64",
    ("darwin", "aarch64"): "darwin_arm64",
    ("darwin", "x86_64"):  "darwin_amd64",
    ("darwin", "amd64"):   "darwin_amd64",
    ("linux",  "arm64"):   "linux_arm64",
    ("linux",  "aarch64"): "linux_arm64",
    ("linux",  "x86_64"):  "linux_amd64",
    ("linux",  "amd64"):   "linux_amd64",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _print_header() -> None:
    print()
    print("  ██████╗  ██████╗ ██████╗ ████████╗██╗  ██╗")
    print("  ██╔══██╗██╔═══██╗██╔══██╗╚══██╔══╝╚██╗██╔╝")
    print("  ██████╔╝██║   ██║██████╔╝   ██║    ╚███╔╝ ")
    print("  ██╔═══╝ ██║   ██║██╔══██╗   ██║    ██╔██╗ ")
    print("  ██║     ╚██████╔╝██║  ██║   ██║   ██╔╝ ██╗")
    print("  ╚═╝      ╚═════╝ ╚═╝  ╚═╝   ╚═╝   ╚═╝  ╚═╝")
    print()
    print("  PortX Installer")
    print("  ─────────────────────────────────────────")
    print()


def _step(message: str) -> None:
    print(f"  → {message}")


def _success(message: str) -> None:
    print(f"  ✓ {message}")


def _error(message: str, exit_code: int = 1) -> None:
    print(f"\n  ✗ Error: {message}", file=sys.stderr)
    sys.exit(exit_code)


# ---------------------------------------------------------------------------
# Step 1 — Detect platform
# ---------------------------------------------------------------------------

def detect_platform() -> tuple[str, str]:
    """
    Returns (display_name, frp_suffix).
    e.g. ('macOS ARM64', 'darwin_arm64')
    Exits with a clear error for unsupported platforms.
    """
    system  = platform.system().lower()
    machine = platform.machine().lower()

    frp_suffix = PLATFORM_MAP.get((system, machine))

    if frp_suffix is None:
        _error(
            f"Unsupported platform: {platform.system()} / {platform.machine()}\n"
            "  Supported: macOS ARM64, macOS AMD64, Linux ARM64, Linux AMD64"
        )

    os_label   = "macOS" if system == "darwin" else "Linux"
    arch_label = "ARM64" if "arm64" in frp_suffix else "AMD64"  # type: ignore[operator]
    display    = f"{os_label} {arch_label}"

    return display, frp_suffix  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Step 2 — Fetch latest release metadata from GitHub
# ---------------------------------------------------------------------------

def fetch_latest_release() -> tuple[str, list[dict]]:
    """
    Queries the GitHub API for the latest FRP release.
    Returns (version_tag, assets_list).
    """
    request = urllib.request.Request(
        FRP_GITHUB_API,
        headers={
            "Accept":     "application/vnd.github+json",
            "User-Agent": "PortX-Installer/1.0",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=NETWORK_TIMEOUT) as response:
            data: dict = json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        _error(f"GitHub API request failed: HTTP {exc.code} {exc.reason}")
    except urllib.error.URLError as exc:
        _error(f"Network error while contacting GitHub: {exc.reason}")
    except Exception as exc:
        _error(f"Unexpected error fetching release info: {exc}")

    tag: str = data.get("tag_name", "")
    if not tag:
        _error("Could not determine the latest FRP version from GitHub.")

    assets: list[dict] = data.get("assets", [])
    if not assets:
        _error("No release assets found for the latest FRP release.")

    return tag, assets


# ---------------------------------------------------------------------------
# Step 3 — Resolve download URL
# ---------------------------------------------------------------------------

def resolve_download_url(
    version_tag: str, assets: list[dict], frp_suffix: str
) -> str:
    """
    Finds the correct .tar.gz asset URL for the given platform suffix.
    e.g. frp_0.71.0_darwin_arm64.tar.gz
    """
    for asset in assets:
        name: str = asset.get("name", "")
        if frp_suffix in name and name.endswith(".tar.gz"):
            url: str = asset.get("browser_download_url", "")
            if url:
                return url

    _error(
        f"No matching FRP asset found for platform '{frp_suffix}'.\n"
        f"  Version: {version_tag}\n"
        "  Check https://github.com/fatedier/frp/releases for available assets."
    )
    return ""  # unreachable


# ---------------------------------------------------------------------------
# Step 3b — Already-installed version check
# ---------------------------------------------------------------------------

def get_installed_version() -> str | None:
    """
    Returns the version string of the currently installed frp binary,
    or None if not installed / version cannot be determined.
    """
    if not INSTALL_PATH.exists():
        return None
    try:
        result = subprocess.run(
            [str(INSTALL_PATH), "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        # frpc outputs something like "frpc version 0.71.0"
        output = (result.stdout + result.stderr).strip()
        for part in output.split():
            if part and part[0].isdigit():
                return part
    except Exception:
        pass
    return None


def is_already_installed(version_tag: str) -> bool:
    """
    Returns True if the installed binary already matches version_tag.
    version_tag is a git tag like 'v0.71.0'; we strip the leading 'v' to compare.
    """
    installed = get_installed_version()
    if installed is None:
        return False
    latest = version_tag.lstrip("v")
    return installed == latest


# ---------------------------------------------------------------------------
# Step 4 — Download (curl preferred, urllib fallback)
# ---------------------------------------------------------------------------

def _has_curl() -> bool:
    """Check whether the system curl binary is available."""
    return shutil.which("curl") is not None


def _download_with_curl(url: str, dest_path: Path) -> None:
    """
    Download using system curl with a real-time progress bar.
    Uses -L to follow GitHub release redirects.
    """
    cmd = [
        "curl",
        "-L",                        # follow redirects (GitHub releases redirect)
        "--progress-bar",            # compact, clean progress bar
        "--connect-timeout", "15",   # fail fast on bad connections
        "--max-time", str(NETWORK_TIMEOUT * 4),  # overall cap
        "-o", str(dest_path),
        url,
    ]
    try:
        # curl writes its progress bar to stderr; let it flow to the terminal
        result = subprocess.run(cmd, check=False)
        print()  # ensure newline after curl's progress bar
        if result.returncode != 0:
            _error(
                f"curl exited with code {result.returncode}.\n"
                f"  URL: {url}\n"
                "  Check your internet connection and try again."
            )
    except FileNotFoundError:
        _error("curl not found on PATH (should not happen after _has_curl check).")
    except Exception as exc:
        _error(f"Unexpected error running curl: {exc}")


def _download_with_urllib(url: str, dest_path: Path) -> None:
    """
    Fallback downloader using Python urllib with an ASCII progress bar.
    """

    def _progress_hook(block_count: int, block_size: int, total_size: int) -> None:
        downloaded = min(block_count * block_size, total_size if total_size > 0 else block_count * block_size)
        if total_size > 0:
            pct    = min(100, int(downloaded * 100 / total_size))
            filled = int(40 * pct / 100)
            bar    = "█" * filled + "░" * (40 - filled)
            mb_done  = downloaded / 1_048_576
            mb_total = total_size  / 1_048_576
            print(
                f"\r  [{bar}] {pct:3d}%  {mb_done:.1f} / {mb_total:.1f} MB",
                end="", flush=True,
            )
        else:
            mb_done = downloaded / 1_048_576
            print(f"\r  Downloaded {mb_done:.1f} MB", end="", flush=True)

    request = urllib.request.Request(
        url, headers={"User-Agent": "PortX-Installer/1.0"}
    )
    try:
        # urllib.request.urlretrieve doesn't honour timeout; open manually first
        # to follow redirects, then stream into the file.
        with urllib.request.urlopen(request, timeout=NETWORK_TIMEOUT) as resp:
            total = int(resp.headers.get("Content-Length", 0))
            block = 8192
            downloaded = 0
            with open(dest_path, "wb") as fh:
                while True:
                    chunk = resp.read(block)
                    if not chunk:
                        break
                    fh.write(chunk)
                    downloaded += len(chunk)
                    _progress_hook(downloaded // block, block, total)
        print()  # newline after progress bar
    except urllib.error.HTTPError as exc:
        _error(f"Download failed: HTTP {exc.code} {exc.reason}\n  URL: {url}")
    except urllib.error.URLError as exc:
        _error(f"Network error during download: {exc.reason}")
    except Exception as exc:
        _error(f"Unexpected error during download: {exc}")


def download_file(url: str, dest_path: Path) -> None:
    """
    Download `url` to `dest_path`.
    Prefers system curl (faster, real redirect handling); falls back to urllib.
    """
    if _has_curl():
        _download_with_curl(url, dest_path)
    else:
        _step("curl not found — using Python urllib fallback...")
        _download_with_urllib(url, dest_path)


# ---------------------------------------------------------------------------
# Step 5 — Validate archive
# ---------------------------------------------------------------------------

def validate_archive(archive_path: Path) -> None:
    """Verifies the downloaded file is a valid gzip tar archive."""
    if not archive_path.exists() or archive_path.stat().st_size == 0:
        _error(
            "Downloaded archive is empty or missing.\n"
            "  The download may have been interrupted."
        )
    if not tarfile.is_tarfile(archive_path):
        _error(
            "Downloaded file is not a valid tar archive.\n"
            f"  Path: {archive_path}\n"
            "  The download may be corrupt. Please try again."
        )


# ---------------------------------------------------------------------------
# Step 6 — Extract and install (frpc only; frps is excluded)
# ---------------------------------------------------------------------------

def _find_binary(root: Path, name: str) -> Path | None:
    """Recursively search for a regular file with the given name."""
    for candidate in root.rglob(name):
        if candidate.is_file():
            return candidate
    return None


def extract_and_install(archive_path: Path) -> None:
    """
    Extracts the FRP archive, copies ONLY the frpc binary to INSTALL_PATH,
    and discards everything else (including frps).
    """
    INSTALL_DIR.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="portx_frp_") as tmp_dir:
        tmp_path = Path(tmp_dir)

        try:
            with tarfile.open(archive_path, "r:gz") as tar:
                tar.extractall(tmp_path)
        except tarfile.TarError as exc:
            _error(f"Failed to extract archive: {exc}")
        except Exception as exc:
            _error(f"Unexpected error during extraction: {exc}")

        # Locate frpc (client) — ignore frps (server) entirely
        frpc_binary = _find_binary(tmp_path, "frpc")
        if frpc_binary is None:
            _error(
                "Could not find the 'frpc' binary inside the archive.\n"
                "  The archive structure may have changed in this FRP release."
            )

        # Install only frpc → renamed as 'frp'
        shutil.copy2(frpc_binary, INSTALL_PATH)
        # tmp_dir (and all extracted files including frps) are deleted automatically

    # Ensure the binary is executable
    current_mode = INSTALL_PATH.stat().st_mode
    INSTALL_PATH.chmod(current_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    _print_header()

    # ── 1. Detect platform ────────────────────────────────────────────────
    _step("Detecting system...")
    display_name, frp_suffix = detect_platform()
    _success(f"Detected: {display_name}")
    print()

    # ── 2. Fetch latest release ───────────────────────────────────────────
    _step("Finding latest FRP release...")
    version_tag, assets = fetch_latest_release()
    _success(f"Latest version: {version_tag}")
    print()

    # ── 3. Skip if already up-to-date ─────────────────────────────────────
    if is_already_installed(version_tag):
        _success(f"FRP {version_tag} is already installed.")
        print()
        print(f"  Location: {INSTALL_PATH}")
        print()
        return

    # ── 4. Resolve download URL ───────────────────────────────────────────
    download_url = resolve_download_url(version_tag, assets, frp_suffix)
    archive_name = download_url.split("/")[-1]

    # ── 5. Download ───────────────────────────────────────────────────────
    _step("Downloading FRP from GitHub...")
    print(f"  URL: {download_url}")
    print()

    with tempfile.TemporaryDirectory(prefix="portx_dl_") as dl_dir:
        archive_path = Path(dl_dir) / archive_name
        download_file(download_url, archive_path)

        # ── 6. Validate ───────────────────────────────────────────────────
        print()
        _step("Validating archive...")
        validate_archive(archive_path)
        _success("Archive is valid.")
        print()

        # ── 7. Extract & install (frpc only) ──────────────────────────────
        _step("Extracting FRP...")
        _step("Installing frpc binary (frps excluded)...")
        extract_and_install(archive_path)

    # ── Done ──────────────────────────────────────────────────────────────
    print()
    print("  ─────────────────────────────────────────")
    _success(f"FRP {version_tag} installed successfully.")
    print()
    print(f"  Location: {INSTALL_PATH}")
    print()


if __name__ == "__main__":
    main()
