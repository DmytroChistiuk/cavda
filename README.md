# CAVDA — CLI AI Video Downloader App

A small, deliberately thin CLI. You describe what you want in plain language;
Claude turns that into a structured search, restricted to domains **you** have
explicitly allow-listed; the app verifies every proposed URL itself; you confirm
one; `yt-dlp` downloads it.

Five linear stages, one process, no state:

```
prompt → intent_parser → source_resolver → verifier → confirm → downloader → report
           (Claude #1)     (Claude #2,       (HTTP,   (you,        (yt-dlp
                            web_search)      no AI)   blocking)   subprocess)
```

## Scope: allow-list only

CAVDA does not search "the web". It searches `allowlist.yaml` and nothing else.

* The allow-list is passed to Claude's `web_search` tool as `allowed_domains`,
  so the search is restricted **server-side** — the model cannot retrieve a page
  outside the list.
* Every URL that comes back is re-checked against the allow-list locally, and
  cross-checked against the URLs that actually appeared in search results. A URL
  the model did not receive from a search result is dropped as fabricated.
* The verifier re-checks the allow-list a third time, including after redirects,
  so a redirect cannot walk a candidate off the list.

That is defence in depth on purpose: the AI is treated as an untrusted source of
suggestions, never as an authority on what is permitted.

**What goes in the allow-list is your call and your responsibility.** Public-domain
archives, openly licensed catalogues, official rights-holder channels, platforms
you hold a licence for. CAVDA cannot judge whether you have the right to download
something — an entry in that file is your assertion, not a fact the tool checked.

## Install

Requires Python 3.10+.

```bash
git clone <your-repo> cavda
cd cavda
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\Activate.ps1
pip install -e .
```

That pulls in `anthropic`, `httpx`, `pyyaml` and `yt-dlp`, and installs the
`cavda` console script.

## API key

CAVDA reads `ANTHROPIC_API_KEY` from the environment at call time. It never
writes it anywhere, never caches it, and there is no credential file, keyring
integration, or `--api-key` flag.

```bash
export ANTHROPIC_API_KEY="sk-ant-..."            # bash/zsh
$env:ANTHROPIC_API_KEY = "sk-ant-..."            # PowerShell
```

Get a key at <https://console.anthropic.com/>. If the variable is unset, the run
ends with a clear error before any network call.

## Usage

```bash
cavda "Night of the Living Dead 1968, 1080p"
```

```
Allow-list: archive.org, your-licensed-platform.example
Looking for: Night of the Living Dead 1968 [1080p]
Verifying 2 candidate(s)...
  dropped (HTTP 404): https://archive.org/details/night-living-dead-trailer

Found 1 verified source(s) on allowed domains:

  [1] Night of the Living Dead (1968), full feature
      domain:  archive.org
      url:     https://archive.org/details/night_of_the_living_dead
      checked: HTTP 200, text/html
      why:
        From search result "Night of the Living Dead : George A. Romero :
        Free Download" — the page lists the full 96-minute feature, public
        domain, with downloadable MPEG4 files.

You are responsible for having the right to download the source you pick.

Download this source? [y/N]: y

Running: yt-dlp -f bestvideo[height<=1080]+bestaudio/best[height<=1080] -o downloads/%(title)s.%(ext)s --no-playlist -- https://archive.org/details/night_of_the_living_dead

Done. Saved to: /home/you/cavda/downloads
```

Options:

| Flag | Meaning |
|---|---|
| `--prompt TEXT` | Same as the positional argument |
| `--allowlist PATH` | Use a different allow-list file (default `./allowlist.yaml`) |
| `--output-dir DIR` | Where yt-dlp writes (default `./downloads`) |
| `--mock` | Run the whole pipeline with offline stand-ins — no API key, no network, no download. Useful for seeing the flow before wiring up a key. |

Exit codes: `0` success or user cancellation, `1` any handled failure. Unhandled
exceptions deliberately raise a full traceback.

## What this tool will never do

These are enforced in code, not just promised in documentation.

* **Never scrape outside the allow-list.** The `web_search` call is domain-restricted
  server-side, and `allowlist.is_allowed()` re-checks the parsed hostname — exact
  match or true subdomain, never a substring — after the AI proposes a URL, again
  in the verifier, and again on the post-redirect URL. `archive.org.attacker.com`
  and `evil-archive.org` both fail.
* **Never bypass DRM, paywalls, geo-blocks or authentication.** `downloader.py`
  keeps a `FORBIDDEN_ARGS` set (`--cookies`, `--cookies-from-browser`,
  `--no-check-certificate`, `--username`, `--password`, `--netrc`, `--add-header`,
  `--proxy`, `--geo-bypass*`, `--allow-unplayable-formats`, …) and asserts that
  none of them appear in the argument list on every invocation. There is no code
  path that adds one. yt-dlp's own errors — "Sign in to confirm your age", "This
  video is DRM protected" — are printed verbatim, with no interpretation that
  could imply a workaround exists.
* **Never store credentials.** There is no credential module, not even a stub. No
  cookie jar, no keyring, no token file. The API key is read from the environment
  at call time and nothing else.
* **Never keep state between runs.** No database, no history log, no cache, no
  `~/.config` writes. The only file CAVDA reads is `allowlist.yaml`, and it never
  writes to it. Two identical runs are genuinely independent.
* **Never retry.** Every Claude call, HTTP check and yt-dlp run is single-shot.
  A failed candidate is dropped, not re-probed. A failed download ends the run.
  Failures raise typed exceptions (`AppError` and its subclasses) and print a
  clear message.
* **Never fabricate a source.** A candidate with no citation, or with a URL that
  did not appear in a search result, is discarded. If that leaves nothing, the app
  says so and exits `1` — it does not fall back to unverified guesses.
* **Never download without your confirmation.** The confirmation step is blocking
  and there is no `--yes` flag to skip it.
* **Never build a shell string.** The yt-dlp command is an argument list, with a
  `--` separator before the URL.

## Layout

```
cavda/
├── pyproject.toml          # console script: cavda = cavda.cli:main
├── allowlist.yaml          # the only file the app reads; format documented inline
├── README.md
└── src/cavda/
    ├── __init__.py
    ├── cli.py              # orchestration only — the pipeline, top to bottom
    ├── models.py           # frozen dataclasses + AppError hierarchy
    ├── allowlist.py        # load_allowlist / is_allowed
    ├── intent_parser.py    # Claude #1: prompt → UserIntent (JSON schema output)
    ├── source_resolver.py  # Claude #2: web_search with allowed_domains → Candidate[]
    ├── verifier.py         # no AI: allow-list re-check + one HEAD/GET → VerifiedCandidate
    ├── confirm.py          # blocking interactive pick, nothing written to disk
    ├── downloader.py       # argument-list yt-dlp subprocess → DownloadResult
    └── mocks.py            # offline stand-ins behind --mock
```

The functions marked `# todo` in `intent_parser`, `source_resolver`, `verifier`
and `downloader` are the four impure boundaries — they are implemented, but need
a live service (the Anthropic API, real hosts, a real yt-dlp binary) to exercise.
`mocks.py` provides a deterministic substitute for each so the pipeline runs end
to end offline. The mocks honour the same constraints: they respect the
allow-list, label their output as fabricated, and never report a download as
having succeeded.
