# Contributing to Tonos

Thanks for your interest in Tonos! This guide explains how to report problems, set up a
development environment and send changes. By taking part you agree to follow the
[Code of Conduct](CODE_OF_CONDUCT.md).

## Ways to contribute

- **Report a wrong result.** This is the most useful feedback: automatic music analysis fails
  in ways that are hard to predict. Open a
  [Wrong analysis result](https://github.com/joaquinmuzzi/tonos/issues/new?template=wrong_result.yml)
  issue with what Tonos said, what the right answer is, and where in the song it goes wrong.
  Attach the JSON from the *Download data (JSON)* button if you can. **Do not attach copyrighted
  audio**; a link to a public recording is enough.
- **Report a bug** (the app crashes, a file does not load, the page looks broken) with the
  [Bug report](https://github.com/joaquinmuzzi/tonos/issues/new?template=bug_report.yml) form.
- **Suggest a feature** with the
  [Feature request](https://github.com/joaquinmuzzi/tonos/issues/new?template=feature_request.yml) form.
- **Send a pull request.** For anything bigger than a small fix, open an issue first so we can
  agree on the approach before you spend time on it.
- **Translate the interface** into another language (see [Translations](#translations)).

Security problems should not be reported in public issues: see [SECURITY.md](SECURITY.md).

## Development environment

You need Python 3.12, ffmpeg and git.

**Windows:** run `.\install.ps1`. It creates the environment in `%LOCALAPPDATA%\tonos\venv`; use
that Python for everything below:

```powershell
$py = "$env:LOCALAPPDATA\tonos\venv\Scripts\python.exe"
& $py -m pip install --group dev
```

**macOS and Linux:** run `./install.sh`. It creates the environment in
`~/.local/share/tonos/venv`; use that Python for everything below:

```bash
py=~/.local/share/tonos/venv/bin/python
"$py" -m pip install --group dev
```

`--group dev` (pip 25.1 or later) installs the development tools listed in `pyproject.toml`:
pytest and Ruff.

Run the app from the repository with `python -m tonos` (web app) or `python -m tonos song.mp4`
(command line).

## Tests

```bash
python -m pytest -m "not slow"   # fast tests, a few seconds
python -m pytest                 # everything, about 1-2 minutes
```

The tests marked `slow` run the real models on synthetic songs (a pop song in G at 120 BPM, a
waltz in D at 150 BPM, odd meters...) and separate a short one into stems. The first run
downloads the beat model (77 MB) and the Demucs model (80 MB); Demucs is installed by the
installers.

Most analysis code can be tested without the models: build beats, downbeats or chord segments
by hand, as the tests in `tests/test_rhythm.py` do. When you fix a wrong result, add a test that
reproduces it with synthetic data (never with copyrighted audio).

## Code style

[Ruff](https://docs.astral.sh/ruff/) lints and formats the code; the configuration is in
`pyproject.toml`.

```bash
ruff check .        # lint (add --fix to fix what can be fixed automatically)
ruff format .       # format
```

Everything is written in English: identifiers, comments, docstrings, commit messages and
documentation. Comments explain *why* the code does something, especially the musical reasoning
behind a threshold or a rule.

## Project layout

```
tonos/
  __main__.py        command line (python -m tonos)
  server.py          local web server (FastAPI)
  messages.py        message codes and their English texts
  analysis/
    pipeline.py      runs every step and builds the report
    audio.py         audio extraction with ffmpeg
    rhythm.py        beats, tempo, meter and the bar grid
    periodicity.py   meter from how often the harmony repeats
    tonality.py      key and tuning
    chords.py        chord recognition
    notation.py      note, key and chord names
  web/               the page: index.html, app.js, i18n.js, styles.css
tests/               pytest tests and the synthetic song generator
```

## The report and its messages

The JSON report is a public interface: people download it and may parse it.

- If you change its structure, or change results enough that old cached analyses would be
  wrong, bump `VERSION` in `tonos/analysis/pipeline.py`. Cached analyses with another version
  are recomputed.
- The analysis never returns finished sentences. A warning or an error is a message code with
  parameters, for example `{"code": "too_long", "params": {"minutes": 20}}`. To add one, add its
  English text to `tonos/messages.py` and its translations to `tonos/web/i18n.js`. The tests
  check that every code is translated, with the same `{placeholders}`.

## Translations

The texts of the web page are in `tonos/web/i18n.js`, one block per language. To add a language,
copy the `en` block, translate every value (keep the keys and the `{placeholders}`) and add a
button with its `data-language` to the header of `tonos/web/index.html`. Then add the language
to the test in `tests/test_messages.py`.

## Commits

Commits follow [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/):

```
<type>(<optional scope>): <description>

<optional body: what changed and why>

<optional footers, e.g. BREAKING CHANGE: ...>
```

- **Types:** `feat` (new feature), `fix` (bug fix), `docs`, `style` (formatting only),
  `refactor`, `perf`, `test`, `build` (dependencies, packaging), `ci`, `chore`, `revert`.
- **Scopes** are optional and short, usually the area of the code: `meter`, `rhythm`, `notation`,
  `chords`, `web`, `cli`, `deps`.
- Write the description in the imperative mood ("add", not "added"), in lowercase, without a
  final period.
- Mark breaking changes with `!` after the type and a `BREAKING CHANGE:` footer that explains
  what users need to change.
- Keep commits **atomic**: one logical change per commit, with its tests.

Examples from this repository:

```
feat(meter): detect 5/4 and 7/4 from harmonic periodicity
fix(notation): spell out-of-key white-key roots without accidentals
build(deps): bump librosa from 0.11.0 to 1.0.0
```

## AI-assisted contributions

You can use AI tools (Claude Code, Codex, Copilot, Cursor…), but say so, as the
[Linux kernel](https://docs.kernel.org/process/coding-assistants.html) and
[asbplayer](https://github.com/asbplayer/asbplayer/blob/main/CONTRIBUTING.md) ask:

- **Every commit made with an AI assistant ends with a trailer** naming the tool and the model:

  ```
  Assisted-by: AGENT_NAME:MODEL_VERSION
  ```

  For example `Assisted-by: Claude Code:claude-opus-5-5` or `Assisted-by: GitHub Copilot:gpt-5`.
  Write one line per assistant if you used more than one. Editors, linters and formatters do not
  count.
- **The pull request description ends with the same line**, or with `Assisted-by: none` if no AI
  tool was used. Pull requests are squash-merged and their description becomes the commit message
  on `main`, so this is where the line stays in the history. CI checks that it is there.
- **You are responsible for the change**, whoever wrote it: read and understand every line, run
  `ruff check .`, `ruff format --check .` and the tests yourself, and say in the description what
  you ran.

Pull requests that were not run, or that are sent in bulk to many projects at once, are closed.

## Pull requests

1. Fork the repository and create a branch from `main` (for example `fix/meter-in-waltzes`).
2. Make your change with its tests, and run `ruff check .`, `ruff format .` and the tests.
3. Open a pull request. Its **title must follow Conventional Commits**: CI checks it, and the
   pull request is squash-merged, so the title becomes the commit message on `main`.
4. In the description, explain what changes, why, and how you tested it, and end it with the
   `Assisted-by:` line (see [AI-assisted contributions](#ai-assisted-contributions)). The
   template has the sections.
5. CI runs the linter and every test (including the end-to-end ones) on Linux. A maintainer
   reviews the change once it is green.

Keep pull requests small and focused: a bug fix, a feature or a refactor, not all three. If a
change needs a refactor first, send the refactor as its own pull request.

## Licensing

By contributing, you agree that your contributions are released under the
[MIT License](LICENSE), like the rest of the code. Never commit audio files or model weights:
the `.gitignore` excludes them, and they usually have their own copyright or licence.
