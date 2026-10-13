"""Checks on the Markdown files: mistakes no reader should see and links that lead nowhere."""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
DOCS = sorted(
    p
    for pattern in ("*.md", "docs/**/*.md", "demo/*.md", "benchmarks/*.md", ".github/**/*.md")
    for p in ROOT.glob(pattern)
)


def _prose(text: str) -> str:
    """The text a reader sees as text: without code blocks, inline code or HTML comments."""
    text = re.sub(r"^```.*?^```", "", text, flags=re.MULTILINE | re.DOTALL)
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    return re.sub(r"`[^`\n]*`", "", text)


def _anchor(heading: str) -> str:
    """GitHub's anchor for a heading: lower case, punctuation removed, spaces as hyphens."""
    heading = re.sub(r"[`*_]", "", heading.strip().lower())
    return re.sub(r"[^\w\- ]", "", heading).replace(" ", "-")


def _anchors(path: Path) -> set[str]:
    text = re.sub(r"^```.*?^```", "", path.read_text(encoding="utf-8"), flags=re.MULTILINE | re.DOTALL)
    return {_anchor(h) for h in re.findall(r"^#+ (.+)$", text, flags=re.MULTILINE)}


def _links(text: str) -> list[str]:
    targets = re.findall(r"\]\(([^)\s]+)\)", text) + re.findall(r'(?:src|href)="([^"]+)"', text)
    return [t for t in targets if not re.match(r"[a-z]+:", t)]  # http:, https:, mailto:...


@pytest.mark.parametrize("path", DOCS, ids=lambda p: str(p.relative_to(ROOT)))
def test_no_escape_sequences_in_text(path):
    # A "\n" typed by an editing tool instead of a line break shows up as text on GitHub
    found = re.findall(r".{0,30}\\[nt](?![A-Za-z]).{0,10}", _prose(path.read_text(encoding="utf-8")))
    assert not found, f"literal escape sequences: {found}"


@pytest.mark.parametrize("path", DOCS, ids=lambda p: str(p.relative_to(ROOT)))
def test_relative_links_lead_somewhere(path):
    broken = []
    for target in _links(_prose(path.read_text(encoding="utf-8"))):
        file, _, anchor = target.partition("#")
        linked = (path.parent / file).resolve() if file else path
        # (the heading is only looked for once the file is known to exist)
        if not linked.exists() or (anchor and linked.suffix == ".md" and anchor not in _anchors(linked)):
            broken.append(target)
    assert not broken, f"links to missing files or headings: {broken}"
