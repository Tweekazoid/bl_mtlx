"""Link MaterialX add-on folder into all detected Blender user addon directories.

Uses platform-appropriate links to avoid copying files during development:
- Windows: NTFS directory junctions (mklink /J)
- macOS/Linux: POSIX symbolic links (os.symlink)
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import sys

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
LOG = logging.getLogger(__name__)

THIS_REPO_ADDON = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "src"),
).replace("\\", "/")


def _blender_versions_path() -> str:
    if sys.platform == "win32":
        base = os.path.expanduser("~/AppData/Roaming/Blender Foundation/Blender")
    elif sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support/Blender")
    else:
        # Linux and other Unix-likes
        xdg = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
        base = os.path.join(xdg, "blender")
        if not os.path.isdir(base):
            base = os.path.expanduser("~/.config/blender")
    return base.replace("\\", "/")


BLENDER_VERSIONS_PATH = _blender_versions_path()
RESULTING_ADDON_NAME = "material_x"

# Blender 4.2 introduced the extensions system.
# - Blender >= 4.2: install under <version>/extensions/user_default/
# - Blender <  4.2: install under <version>/scripts/addons/
EXTENSIONS_MIN_VERSION = (4, 2)


def _parse_version(version: str) -> tuple[int, int]:
    major, minor = version.split(".", 1)
    return int(major), int(minor)


def _install_subdir_for(version: str) -> str:
    return "extensions/user_default" if _parse_version(version) >= EXTENSIONS_MIN_VERSION else "scripts/addons"


def _discover_install_dirs() -> list[tuple[str, str]]:
    """Return list of (blender_version, install_dir) tuples.

    For each detected Blender version directory, picks the appropriate
    install location based on the version (extensions vs legacy addons).
    """
    found: list[tuple[str, str]] = []
    version_re = re.compile(r"^\d+\.\d+$")
    if not os.path.isdir(BLENDER_VERSIONS_PATH):
        return found

    for entry in sorted(os.listdir(BLENDER_VERSIONS_PATH)):
        if not version_re.match(entry):
            continue
        subdir = _install_subdir_for(entry)
        install_dir = os.path.join(BLENDER_VERSIONS_PATH, entry, subdir).replace("\\", "/")
        os.makedirs(install_dir, exist_ok=True)
        found.append((entry, install_dir))
    return found


def _remove_existing(path: str) -> None:
    if not os.path.lexists(path):
        return
    if os.path.islink(path):
        os.unlink(path)
        return
    if os.path.isdir(path):
        try:
            os.rmdir(path)
        except OSError:
            shutil.rmtree(path, ignore_errors=True)
        return
    os.remove(path)


def _try_junction(src: str, dst: str) -> bool:
    cmd = f'cmd /c mklink /J "{dst}" "{src}"'
    proc = subprocess.run(cmd, shell=True, capture_output=True, text=True, check=False)
    if proc.returncode == 0:
        return True
    LOG.error("Junction failed: %s", (proc.stderr or proc.stdout).strip())
    return False


def _try_symlink(src: str, dst: str) -> bool:
    try:
        os.symlink(src, dst, target_is_directory=True)
    except OSError:
        LOG.exception("Symlink failed")
        return False
    else:
        return True


def _link(src: str, dst: str) -> bool:
    if sys.platform == "win32":
        return _try_junction(src, dst)
    return _try_symlink(src, dst)


def main() -> None:
    if not os.path.isdir(THIS_REPO_ADDON):
        raise RuntimeError(f"Addon folder not found: {THIS_REPO_ADDON}")

    install_dirs = _discover_install_dirs()
    if not install_dirs:
        LOG.warning(
            "No Blender extension/addon directories found under: %s",
            BLENDER_VERSIONS_PATH,
        )
        return

    for blender_version, install_dir in install_dirs:
        target_path = os.path.join(install_dir, RESULTING_ADDON_NAME).replace("\\", "/")

        LOG.info("Linking Blender %s -> %s", blender_version, target_path)
        _remove_existing(target_path)

        if _link(THIS_REPO_ADDON, target_path):
            LOG.info("Linked MaterialX addon for Blender %s", blender_version)
        else:
            LOG.error("Failed to link MaterialX addon for Blender %s", blender_version)


if __name__ == "__main__":
    main()
