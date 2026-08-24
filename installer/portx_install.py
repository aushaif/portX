#!/usr/bin/env python3
"""
PortX Installer
Downloads the PortX CLI and the FRP client binary, installing to:
- ~/.local/bin/portx (CLI executable)
- ~/.portx/bin/frpc (FRP client binary)
- ~/.portx/ (runtime data: tunnels.toml, tunnels/, logs/)

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
PORTX_GITHUB_TAR = "https://github.com/aushaif/portX/archive/refs/heads/main.tar.gz"

PORTX_DIR      = Path.home() / ".portx"
BIN_DIR        = PORTX_DIR / "bin"
FRP_PATH       = BIN_DIR / "frpc"
LOCAL_BIN_DIR  = Path.home() / ".local" / "bin"
PORTX_EXECUTABLE = LOCAL_BIN_DIR / "portx"

NETWORK_TIMEOUT = 30

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
    system  = platform.system().lower()
    machine = platform.machine().lower()

    frp_suffix = PLATFORM_MAP.get((system, machine))
    if frp_suffix is None:
        _error(
            f"Unsupported platform: {platform.system()} / {platform.machine()}\n"
            "  Supported: macOS ARM64, macOS AMD64, Linux ARM64, Linux AMD64"
        )

    os_label   = "macOS" if system == "darwin" else "Linux"
    arch_label = "ARM64" if "arm64" in frp_suffix else "AMD64"
    return f"{os_label} {arch_label}", frp_suffix


# ---------------------------------------------------------------------------
# Network Utilities
# ---------------------------------------------------------------------------

def _has_curl() -> bool:
    return shutil.which("curl") is not None


def _download_with_curl(url: str, dest_path: Path, silent: bool = False) -> None:
    cmd = [
        "curl", "-L",
        "--connect-timeout", "15",
        "--max-time", str(NETWORK_TIMEOUT * 4),
        "-o", str(dest_path),
        url,
    ]
    if silent:
        cmd.append("-s")
    else:
        cmd.append("--progress-bar")
        
    try:
        result = subprocess.run(cmd, check=False)
        if not silent: print()
        if result.returncode != 0:
            _error(f"curl exited with code {result.returncode}.\n  URL: {url}")
    except Exception as exc:
        _error(f"Unexpected error running curl: {exc}")


def _download_with_urllib(url: str, dest_path: Path, silent: bool = False) -> None:
    def _progress_hook(block_count: int, block_size: int, total_size: int) -> None:
        if silent: return
        downloaded = min(block_count * block_size, total_size if total_size > 0 else block_count * block_size)
        if total_size > 0:
            pct    = min(100, int(downloaded * 100 / total_size))
            filled = int(40 * pct / 100)
            bar    = "█" * filled + "░" * (40 - filled)
            print(f"\r  [{bar}] {pct:3d}%", end="", flush=True)
        else:
            print(f"\r  Downloaded {downloaded / 1048576:.1f} MB", end="", flush=True)

    request = urllib.request.Request(url, headers={"User-Agent": "PortX-Installer/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=NETWORK_TIMEOUT) as resp:
            total = int(resp.headers.get("Content-Length", 0))
            block = 8192
            downloaded = 0
            with open(dest_path, "wb") as fh:
                while True:
                    chunk = resp.read(block)
                    if not chunk: break
                    fh.write(chunk)
                    downloaded += len(chunk)
                    _progress_hook(downloaded // block, block, total)
        if not silent: print()
    except Exception as exc:
        _error(f"Download failed: {exc}\n  URL: {url}")


def download_file(url: str, dest_path: Path, silent: bool = False) -> None:
    if _has_curl():
        _download_with_curl(url, dest_path, silent)
    else:
        _download_with_urllib(url, dest_path, silent)


# ---------------------------------------------------------------------------
# Install PortX CLI
# ---------------------------------------------------------------------------

def install_portx_cli() -> None:
    _step("Downloading PortX CLI...")
    
    with tempfile.TemporaryDirectory(prefix="portx_src_") as tmp_dir:
        tar_path = Path(tmp_dir) / "portx.tar.gz"
        download_file(PORTX_GITHUB_TAR, tar_path, silent=True)
        
        try:
            with tarfile.open(tar_path, "r:gz") as tar:
                tar.extractall(tmp_dir)
        except Exception as exc:
            _error(f"Failed to extract PortX source: {exc}")
            
        extracted_dir = None
        for item in Path(tmp_dir).iterdir():
            if item.is_dir() and item.name.startswith("portX-"):
                extracted_dir = item
                break
                
        if not extracted_dir:
            _error("Failed to find PortX source directory inside tarball.")
        
        cli_dir = extracted_dir / "cli"
        if not cli_dir.exists():
            _error("CLI directory not found in repository.")
        
        # Install CLI modules to ~/.local/lib/portx/
        lib_dir = LOCAL_BIN_DIR.parent / "lib" / "portx"
        if lib_dir.exists():
            shutil.rmtree(lib_dir)
        lib_dir.mkdir(parents=True, exist_ok=True)
        
        # Copy all CLI modules
        for py_file in cli_dir.glob("*.py"):
            shutil.copy2(py_file, lib_dir / py_file.name)
        
        # Create the executable wrapper (this will also create LOCAL_BIN_DIR)
        create_executable_wrapper(PORTX_EXECUTABLE, lib_dir)
        
    _success("PortX CLI installed to ~/.local/bin/portx")


def create_executable_wrapper(output_path: Path, lib_dir: Path) -> None:
    """Create an executable wrapper script that imports from lib directory."""
    
    # Remove old installation if it exists (could be symlink or file)
    if output_path.exists() or output_path.is_symlink():
        output_path.unlink()
    
    # Ensure parent directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    wrapper = f'''#!/usr/bin/env python3
"""
PortX CLI - Installed to ~/.local/bin/portx
"""
from __future__ import annotations

import sys
from pathlib import Path

# Add library directory to path
LIB_DIR = Path("{lib_dir}")
if str(LIB_DIR) not in sys.path:
    sys.path.insert(0, str(LIB_DIR))

# Import and run the main CLI
if __name__ == "__main__":
    import portx as _portx_main
    _portx_main.main()
'''
    
    output_path.write_text(wrapper, "utf-8")
    output_path.chmod(output_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


# ---------------------------------------------------------------------------
# Install FRP
# ---------------------------------------------------------------------------

def fetch_latest_release() -> tuple[str, list[dict]]:
    request = urllib.request.Request(
        FRP_GITHUB_API,
        headers={"Accept": "application/vnd.github+json", "User-Agent": "PortX-Installer/1.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=NETWORK_TIMEOUT) as response:
            data: dict = json.loads(response.read().decode())
    except Exception as exc:
        _error(f"Unexpected error fetching FRP release info: {exc}")

    tag: str = data.get("tag_name", "")
    assets: list[dict] = data.get("assets", [])
    if not tag or not assets:
        _error("Could not determine the latest FRP version or assets.")
    return tag, assets


def resolve_download_url(version_tag: str, assets: list[dict], frp_suffix: str) -> str:
    for asset in assets:
        name: str = asset.get("name", "")
        if frp_suffix in name and name.endswith(".tar.gz"):
            url: str = asset.get("browser_download_url", "")
            if url: return url
    _error(f"No matching FRP asset found for platform '{frp_suffix}'.")
    return ""


def get_installed_version() -> str | None:
    if not FRP_PATH.exists(): return None
    try:
        result = subprocess.run([str(FRP_PATH), "--version"], capture_output=True, text=True, timeout=5)
        output = (result.stdout + result.stderr).strip()
        for part in output.split():
            if part and part[0].isdigit(): return part
    except Exception:
        pass
    return None


def extract_and_install_frpc(archive_path: Path) -> None:
    BIN_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="portx_frp_") as tmp_dir:
        tmp_path = Path(tmp_dir)
        try:
            with tarfile.open(archive_path, "r:gz") as tar:
                tar.extractall(tmp_path)
        except Exception as exc:
            _error(f"Failed to extract FRP archive: {exc}")

        frpc_binary = None
        for candidate in tmp_path.rglob("frpc"):
            if candidate.is_file():
                frpc_binary = candidate
                break
                
        if frpc_binary is None:
            _error("Could not find the 'frpc' binary inside the archive.")

        shutil.copy2(frpc_binary, FRP_PATH)

    FRP_PATH.chmod(FRP_PATH.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


# ---------------------------------------------------------------------------
# Ensure runtime directories exist
# ---------------------------------------------------------------------------

def create_runtime_dirs() -> None:
    """Create runtime directories in ~/.portx for tunnels, logs, etc."""
    (PORTX_DIR / "tunnels").mkdir(parents=True, exist_ok=True)
    (PORTX_DIR / "logs").mkdir(parents=True, exist_ok=True)


def check_path() -> None:
    path_env = os.environ.get("PATH", "")
    if str(LOCAL_BIN_DIR) not in path_env:
        print()
        print(f"  ⚠️  WARNING: {LOCAL_BIN_DIR} is not in your PATH.")
        print(f"  To use the 'portx' command globally, add this line to your ~/.zshrc or ~/.bashrc:")
        print(f"    export PATH=\"{LOCAL_BIN_DIR}:$PATH\"")
        print(f"  Then restart your terminal or run: source ~/.zshrc")
        print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    _print_header()

    _step("Detecting system...")
    display_name, frp_suffix = detect_platform()
    _success(f"Detected: {display_name}")
    print()
    
    # 1. Install CLI
    install_portx_cli()
    print()

    # 2. Fetch latest FRP
    _step("Checking FRP requirements...")
    version_tag, assets = fetch_latest_release()
    
    installed = get_installed_version()
    latest = version_tag.lstrip("v")
    
    if installed == latest:
        _success(f"FRP {version_tag} is already installed.")
    else:
        download_url = resolve_download_url(version_tag, assets, frp_suffix)
        archive_name = download_url.split("/")[-1]
        print(f"  Downloading FRP {version_tag}...")
        
        with tempfile.TemporaryDirectory(prefix="portx_dl_") as dl_dir:
            archive_path = Path(dl_dir) / archive_name
            download_file(download_url, archive_path)
            extract_and_install_frpc(archive_path)
            _success("FRP installed successfully.")
    
    print()

    # 3. Create runtime directories
    _step("Setting up runtime directories...")
    create_runtime_dirs()
    _success("Runtime directories created.")
    
    print()
    print("  ─────────────────────────────────────────")
    _success("PortX installed successfully!")
    print(f"  Executable: {PORTX_EXECUTABLE}")
    print(f"  Runtime:    {PORTX_DIR}")
    print(f"  FRP:        {FRP_PATH}")
    check_path()


if __name__ == "__main__":
    main()
