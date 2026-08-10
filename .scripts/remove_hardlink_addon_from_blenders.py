"""Remove BL Objector development links from all detected Blender installs.

Always checks BOTH the legacy addons location and the Blender 4.2+ extensions
location, regardless of detected Blender version, so stale links from either
layout get cleaned up. Cross-platform (Windows / macOS / Linux).
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import sys

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
LOG = logging.getLogger(__name__)

RESULTING_ADDON_NAME = "material_x"

# Always probe both layouts during removal.
_REMOVAL_SUBDIRS = (
    "extensions/user_default",
    "scripts/addons",
)


def _blender_versions_path() -> str:
    if sys.platform == "win32":
        base = os.path.expanduser("~/AppData/Roaming/Blender Foundation/Blender")
    elif sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support/Blender")
    else:
        xdg = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
        base = os.path.join(xdg, "blender")
        if not os.path.isdir(base):
            base = os.path.expanduser("~/.config/blender")
    return base.replace("\\", "/")


BLENDER_VERSIONS_PATH = _blender_versions_path()


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


def _candidate_paths() -> list[tuple[str, str]]:
    """Return list of (blender_version, candidate_target_path) for both layouts."""
    candidates: list[tuple[str, str]] = []
    version_re = re.compile(r"^\d+\.\d+$")
    if not os.path.isdir(BLENDER_VERSIONS_PATH):
        return candidates

    for entry in sorted(os.listdir(BLENDER_VERSIONS_PATH)):
        if not version_re.match(entry):
            continue
        for subdir in _REMOVAL_SUBDIRS:
            target = os.path.join(
                BLENDER_VERSIONS_PATH, entry, subdir, RESULTING_ADDON_NAME,
            ).replace("\\", "/")
            candidates.append((entry, target))
    return candidates


def main() -> None:
    candidates = _candidate_paths()
    if not candidates:
        LOG.warning("No Blender install directories found under: %s", BLENDER_VERSIONS_PATH)
        return

    removed_any = False
    for blender_version, target in candidates:
        if not os.path.lexists(target):
            continue
        LOG.info("Removing link for Blender %s: %s", blender_version, target)
        _remove_existing(target)
        if os.path.lexists(target):
            LOG.error("Failed to remove: %s", target)
        else:
            LOG.info("Removed MaterialX addon link for Blender %s", blender_version)
            removed_any = True

    if not removed_any:
        LOG.info("No BL Objector links found to remove.")


if __name__ == "__main__":
    main()
