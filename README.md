# CAVDA — CLI AI Video Downloader App

A small, deliberately thin CLI. You describe what you want in plain language;
Claude turns that into a structured search, restricted to domains **you** have
explicitly allow-listed; the app verifies every proposed URL itself; you confirm
one; `yt-dlp` downloads it.

Five linear stages, one process, no state:

```
prompt → intent_parser → source_resolver → confirm → downloader
           (Claude #1)     (Claude #2,       (HTTP,   (you,    
                            web_search)      no AI)   blocking)
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

Options:

| Flag | Meaning |
|---|---|
| `--prompt TEXT` | Content that user searching for
| `--allowlist PATH` | Use a different allow-list file (default `./allowlist.yaml`) |
| `--output-dir DIR` | Where yt-dlp writes (default `./downloads`) |

Exit codes: `0` success or user cancellation, `1` any handled failure. Unhandled
exceptions deliberately raise a full traceback.
