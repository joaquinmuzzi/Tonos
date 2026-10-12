# Security policy

## Supported versions

Tonos is a small project: only the latest release (and `main`) receives fixes.

## How Tonos is exposed

Tonos is meant to run on your own computer. The web server only listens on `127.0.0.1`, so other
devices on your network cannot reach it, and analyses never leave your machine. It does process
files you give it, with ffmpeg and with machine-learning models downloaded from their original
sources.

Examples of problems we want to hear about:

- the server becoming reachable from other machines, or a web page on another site being able
  to use it;
- a crafted file name or upload that writes or reads files outside Tonos's folders;
- a crafted media file that makes Tonos run code or crash in a way that affects your system;
- a vulnerable dependency that Tonos actually uses in a vulnerable way.

## Reporting a vulnerability

Please **do not open a public issue**. Report it privately through GitHub instead:
[Report a vulnerability](https://github.com/joaquinmuzzi/tonos/security/advisories/new)
(the *Security* tab of the repository, then *Report a vulnerability*).

Include what you found, how to reproduce it, and what an attacker could do with it. You will get
an answer within 7 days. Once a fix is ready, it is released and the advisory is published,
crediting you unless you prefer otherwise.
