"""Builds the online demo in _site/: the web page, opening a song that is already analyzed.

To preview it:

    python demo/build.py
    python -m http.server --directory _site
"""

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "tonos" / "web"
DEMO = ROOT / "demo"
SITE = ROOT / "_site"
SONG = ("carefree.json", "carefree.mp3")


def build() -> None:
    shutil.rmtree(SITE, ignore_errors=True)
    # The same layout as the app's server: the page at the root, its files under static/
    shutil.copytree(WEB, SITE / "static", ignore=shutil.ignore_patterns("index.html"))
    shutil.copy(WEB / "index.html", SITE / "index.html")
    # The demo configuration replaces the app's empty one
    shutil.copy(DEMO / "demo.js", SITE / "static" / "demo.js")
    (SITE / "demo").mkdir()
    for name in SONG:
        shutil.copy(DEMO / name, SITE / "demo" / name)


if __name__ == "__main__":
    build()
    print(f"Demo built in {SITE}")
