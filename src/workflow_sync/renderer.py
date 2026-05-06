"""Template metadata parsing and Jinja2 rendering utilities."""

import re
from pathlib import Path

from jinja2 import Environment, FileSystemLoader
from packaging.version import Version, InvalidVersion

# Matches comment lines of the form:  # key: value
_META_RE = re.compile(r"^#\s+([\w-]+):\s+(.+)$")

# Placeholder used to protect GitHub Actions expressions (${{ ... }}) from
# being interpreted by Jinja2 during rendering.
_GH_PLACEHOLDER = "\x00GH\x00"


class _GitHubActionsLoader(FileSystemLoader):
    """FileSystemLoader that escapes ``${{`` before Jinja2 processes the source
    so that GitHub Actions expressions pass through untouched."""

    def get_source(self, environment, template):  # type: ignore[override]
        source, filename, uptodate = super().get_source(environment, template)
        source = source.replace("${{", _GH_PLACEHOLDER)
        return source, filename, uptodate


def parse_template_meta(template_file: Path) -> dict[str, str]:
    """Parse ``# key: value`` comment headers from the top of a template file.

    Stops at the first non-comment line.
    """
    meta: dict[str, str] = {}
    with open(template_file) as fh:
        for line in fh:
            stripped = line.rstrip()
            if not stripped.startswith("#"):
                break
            match = _META_RE.match(stripped)
            if match:
                meta[match.group(1)] = match.group(2).strip()
    return meta


def parse_deployed_meta(content: str) -> dict[str, str]:
    """Parse ``# key: value`` comment headers from the content string of a
    deployed workflow file.
    """
    meta: dict[str, str] = {}
    for line in content.splitlines():
        stripped = line.rstrip()
        if not stripped.startswith("#"):
            break
        match = _META_RE.match(stripped)
        if match:
            meta[match.group(1)] = match.group(2).strip()
    return meta


def needs_update(
    template_version: str,
    deployed_content: str | None,
    *,
    workflow_id: str | None = None,
) -> bool:
    """Return True if the deployed workflow needs to be updated.

    Args:
        template_version: Version string from the template metadata.
        deployed_content: Raw content of the existing workflow file in the
            repo, or ``None`` if the file does not exist yet.
        workflow_id: Folder-name id of the workflow (e.g. ``jira-review``).
            When provided, the deployed file's ``# id:`` header is checked
            first; a mismatch forces an update so the correct workflow
            overwrites a stale or renamed file.
    """
    if deployed_content is None:
        return True

    deployed_meta = parse_deployed_meta(deployed_content)

    if workflow_id is not None:
        deployed_id = deployed_meta.get("id")
        if deployed_id and deployed_id != workflow_id:
            # Different workflow — treat as missing so it gets overwritten
            return True

    deployed_version = deployed_meta.get("version")

    if not deployed_version:
        return True

    try:
        return Version(template_version) > Version(deployed_version)
    except InvalidVersion:
        # Fall back to string comparison if versions are non-PEP-440
        return template_version != deployed_version


def find_template_file(workflow_dir: Path) -> Path | None:
    """Return the first template file found inside *workflow_dir*.

    Preference order: ``.j2`` files, then ``.yml``, then ``.yaml``.
    """
    for pattern in ("*.j2", "*.yml", "*.yaml"):
        matches = sorted(workflow_dir.glob(pattern))
        if matches:
            return matches[0]
    return None


def render_template(
    template_file: Path, context: dict, extra_search_paths: list[Path] | None = None
) -> str:
    """Render *template_file* with Jinja2 using the provided *context* dict.

    GitHub Actions expressions (``${{ ... }}``) are preserved as-is and are
    never evaluated by Jinja2.

    *extra_search_paths* are appended to the loader's search path so that
    ``{% include %}`` directives can resolve shared partial templates (e.g.
    from a ``_partials/`` directory at the workflows root).
    """
    search_paths: list[str] = [str(template_file.parent)]
    if extra_search_paths:
        search_paths += [str(p) for p in extra_search_paths]

    env = Environment(
        loader=_GitHubActionsLoader(search_paths),
        keep_trailing_newline=True,
        autoescape=False,
    )
    template = env.get_template(template_file.name)
    rendered = template.render(**context)
    return rendered.replace(_GH_PLACEHOLDER, "${{")
