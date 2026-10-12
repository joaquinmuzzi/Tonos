# Third-party notices

The source code in this repository is released under the [MIT License](LICENSE).
It relies on third-party models and libraries that have **their own licences**. This file
summarises them so you can check them before reusing or redistributing anything.

> **This is not legal advice.** The information below comes from each project's own
> documentation and package metadata at the versions pinned in `requirements.txt`. Licences can
> change; always check the original source.

## Machine-learning models

This repository does **not** include any model weights. They are installed from their original
sources when you run `install.ps1` (or the equivalent `pip` commands): the S-KEY and
Consonance-ACE checkpoints come inside their Python packages, and the Beat This! checkpoint is
downloaded from its authors' server on first use.

| Model | Used for | Version | Code licence | Weights licence | Notes |
|---|---|---|---|---|---|
| [Beat This!](https://github.com/CPJKU/beat_this) (CPJKU, ISMIR 2024) | Beats and downbeats | `beat-this==1.1.0`, checkpoint `final0` | MIT | MIT, according to the authors | The authors note that some of the audio used for training is copyrighted. |
| [S-KEY](https://github.com/deezer/s-key) (Deezer, ICASSP 2025) | Key detection | commit `918b83d` | MIT | **Not stated** | The checkpoint (`skey/models/skey.pt`) is distributed with the package, but no licence is declared for it. |
| [Consonance-ACE](https://github.com/andreamust/consonance-ACE) (Poltronieri, Serra & Rocamora, ISMIR 2025) | Chord recognition | commit `d17633a` | MIT | **Not stated separately** | Trained on third-party chord annotation datasets (Isophonics and the McGill Billboard corpus, via ChoCo), whose terms may restrict commercial use. |

**Commercial use of the model weights is not confirmed.** Personal, local use is the intended use
of this project. If you plan to use it in a commercial product or service, review the licence and
training-data terms of each model first, and consider contacting their authors.

## Libraries

Main runtime dependencies and the licences declared in their package metadata:

| Library | Licence |
|---|---|
| PyTorch, torchaudio | BSD-3-Clause |
| librosa | ISC |
| mir_eval | MIT |
| harte-library | MIT |
| jams, pumpp | ISC |
| gin-config, lightning, torchmetrics | Apache-2.0 |
| music21 | BSD-3-Clause |
| scikit-learn, numpy, soundfile | BSD-3-Clause |
| nnAudio, einops, rotary-embedding-torch | MIT |
| soxr (python-soxr, bundles libsoxr) | LGPL-2.1-or-later |
| FastAPI | MIT |
| uvicorn | BSD-3-Clause |
| python-multipart | Apache-2.0 |

[FFmpeg](https://ffmpeg.org/legal.html) is used as an external program that you install
separately (`winget install Gyan.FFmpeg`); it is not distributed with this project. Its licence
(LGPL or GPL, depending on the build) applies to your copy.

## Citations

If you use Tonos in research, please cite the models it builds on:

- Foscarin, F., Schlüter, J., & Widmer, G. (2024). *Beat this! Accurate beat tracking without
  DBN postprocessing.* ISMIR. [arXiv:2407.21658](https://arxiv.org/abs/2407.21658)
- Kong, Y., Meseguer-Brocal, G., Lostanlen, V., Lagrange, M., & Hennequin, R. (2025).
  *S-KEY: Self-supervised learning of major and minor keys from audio.* ICASSP.
  [arXiv:2501.12907](https://arxiv.org/abs/2501.12907)
- Poltronieri, A., Serra, X., & Rocamora, M. (2025). *From discord to harmony: Decomposed
  consonance-based training for improved audio chord estimation.* ISMIR.
  [arXiv:2509.01588](https://arxiv.org/abs/2509.01588)
