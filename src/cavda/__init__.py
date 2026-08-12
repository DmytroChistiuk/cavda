"""CAVDA — CLI AI Video Downloader App.

A deliberately thin, stateless pipeline:

    intent_parser -> source_resolver -> verifier -> confirm -> downloader

Nothing is persisted between runs: no database, no config writes, no history
log, no credential store, no cache. The only file the app ever reads is the
static ``allowlist.yaml``.
"""

__all__ = ["__version__"]

__version__ = "0.1.0"
