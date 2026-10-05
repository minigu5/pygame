"""Builds the client for the browser and puts it where the server serves it.

    python tools/build_web.py

pygbag packs one folder into a page that runs the same pygame code in
WebAssembly. The client and the shared data are gathered into one folder
first, since the page can read nothing outside what it was packed with. The
result lands in server/public/, which the worker serves at its own address
(see "assets" in server/wrangler.jsonc): open the server in a browser and the
game is there.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = "chameleon"    # the staging folder's name becomes the package's
PUBLIC = ROOT / "server" / "public"
TITLE = "Meccha Chameleon 2D"


def main() -> int:
    # Staged in the system's temporary folder: a synced one (OneDrive) holds on
    # to files it is uploading, and the next build could not clear them away.
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as scratch:
        return build(Path(scratch) / PACKAGE)


def build(stage: Path) -> int:
    stage.mkdir()
    for source in (ROOT / "client").glob("*.py"):
        shutil.copy2(source, stage / source.name)
    shutil.copytree(ROOT / "client" / "assets", stage / "assets")
    shutil.copytree(ROOT / "shared", stage / "shared")

    built = subprocess.run(
        [sys.executable, "-m", "pygbag", "--build", "--title", TITLE, "--app_name", TITLE, str(stage)]
    )
    if built.returncode != 0:
        return built.returncode

    shutil.copytree(stage / "build" / "web", PUBLIC, dirs_exist_ok=True)
    for path in sorted(PUBLIC.rglob("*")):
        if path.is_file():
            print(f"{path.stat().st_size:>10,}  {path.relative_to(ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
