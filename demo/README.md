# Online demo

The demo at <https://joaquinmuzzi.github.io/Tonos/> is the same web page as the app, opening a
song that is already analyzed, so anyone can try the player, the click, the speed control and the
bar grid without installing anything. It cannot analyze other songs: there is no server behind it.

| File | What it is |
|---|---|
| `carefree.mp3` | The song, re-encoded at 128 kbps from the original. |
| `carefree.json` | Its analysis, the same JSON the app produces. |
| `demo.js` | Which song to open and its credit. It replaces `tonos/web/demo.js` in the site. |
| `build.py` | Puts the site together in `_site/`. |

The [Demo workflow](../.github/workflows/pages.yml) builds and publishes the site whenever
`tonos/web/` or this folder changes on `main`.

## The song

"Carefree" by Kevin MacLeod ([incompetech.com](https://incompetech.com/music/royalty-free/index.html?isrc=USUAN1400037)),
licensed under [Creative Commons: By Attribution 3.0](https://creativecommons.org/licenses/by/3.0/).
The file was taken from [Wikimedia Commons](https://commons.wikimedia.org/wiki/File:Carefree_(ISRC_USUAN1400037).mp3)
and re-encoded at a lower bitrate; the music is unchanged. The demo page shows this credit.

Only use audio here that its licence lets anyone redistribute. Songs you analyze with the app stay
on your computer and must not be added to the repository.

## Updating it

When the analysis changes, analyze the song again (in Git Bash or `cmd`; Windows PowerShell 5.1
would save the JSON in UTF-16):

```bash
python -m tonos --json demo/carefree.mp3 > demo/carefree.json
```

To preview the site:

```bash
python demo/build.py
python -m http.server --directory _site
```
