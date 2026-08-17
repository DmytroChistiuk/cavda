import os

import anthropic

from cavda.dto.errors import AppError

__all__ = ["build_ai_client"]

#TODO: Serve client as a object to the method. Check on null before serve and if it is null init it.
def build_ai_client():
    """Build an Anthropic SDK client. The API key is read from the environment and never stored."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise AppError(
            "ANTHROPIC_API_KEY is not set. Export it for this shell session (detailed instructions listed in README.md)"
        )
    return anthropic.Anthropic()
