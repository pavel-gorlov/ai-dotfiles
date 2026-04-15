"""Exception hierarchy for ai-dotfiles.

Commands catch AiDotfilesError subclasses and convert them to user-friendly
output with an exit code.
"""


class AiDotfilesError(Exception):
    """Base exception for all ai-dotfiles errors."""

    def __init__(self, message: str, exit_code: int = 1) -> None:
        super().__init__(message)
        self.exit_code = exit_code


class ConfigError(AiDotfilesError):
    """Invalid or missing configuration / manifest."""


class ElementError(AiDotfilesError):
    """Invalid element specifier or missing element in catalog."""


class LinkError(AiDotfilesError):
    """Symlink operation failed."""


class ExternalError(AiDotfilesError):
    """External process failure (git clone, etc.)."""
