## What

<!-- What does this pull request change? -->

## Why

<!-- The problem it solves. Link the issue: "Fixes #123". -->

## Testing

<!-- How you checked it: new or updated tests, songs you tried (no copyrighted audio in the repository), screenshots for the web page. -->

## Checklist

- [ ] The title follows [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/) (`fix(rhythm): ...`), in English.
- [ ] Tests cover the change, and `python -m pytest` passes.
- [ ] `ruff check .` and `ruff format --check .` pass.
- [ ] If the report changed shape or results: `VERSION` in `tonos/analysis/pipeline.py` is bumped.
- [ ] New messages have their English text in `tonos/messages.py` and their translations in `tonos/web/i18n.js`.
- [ ] Documentation is updated (README, CONTRIBUTING), if needed.
