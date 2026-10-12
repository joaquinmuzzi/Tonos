"""The version number is written in two places that must agree."""

import tomllib
from pathlib import Path

from tonos import __version__


def test_version_matches_pyproject():
    pyproject = Path(__file__).parents[1] / "pyproject.toml"
    assert tomllib.loads(pyproject.read_text(encoding="utf-8"))["project"]["version"] == __version__
