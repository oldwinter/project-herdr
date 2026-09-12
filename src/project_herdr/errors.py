class ProjectHerdrError(Exception):
    """User-facing control-plane error."""

    exit_code = 2


class ConfigError(ProjectHerdrError):
    """Registry, overlay, or contract failed validation."""


class NotFoundError(ProjectHerdrError):
    """Requested workspace, dispatch, or receipt does not exist."""


class GitError(ProjectHerdrError):
    """Read-only git sensor failed."""


class AdapterError(ProjectHerdrError):
    """Optional Herdr dispatch was requested but could not run."""

    exit_code = 3
