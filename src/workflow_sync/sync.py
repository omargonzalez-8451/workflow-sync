"""Core sync logic: clone / pull repos and apply workflow templates."""

from __future__ import annotations

import contextlib
import tempfile
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import git
import yaml
from rich.console import Console

from .renderer import (
    find_template_file,
    needs_update,
    parse_deployed_meta,
    parse_template_meta,
    render_template,
)

if TYPE_CHECKING:
    from .base_schemas import BaseWorkflowOptions, Config, Repo, WorkflowDefinition

console = Console()

# Type alias for a sync action result
SyncAction = dict[str, str]


def _pr_url(
    org: str, repo: str, base_branch: str, head_branch: str, title: str, body: str
) -> str:
    """Build a GitHub compare URL that pre-fills the PR title and body."""
    params = urllib.parse.urlencode(
        {
            "expand": "1",
            "title": title,
            "body": body,
        }
    )
    return f"https://github.com/{org}/{repo}/compare/{base_branch}...{head_branch}?{params}"


def _is_version_bump_only(old_content: str, new_content: str) -> bool:
    """Return True when the only differing lines are sync header comment lines.

    Header lines start with ``# id:``, ``# title:``, ``# version:``, or
    ``# description:``.  If every changed line falls into that set the
    workflow body itself is unchanged — it's a version-bump-only update.
    """
    _HEADER_PREFIX = ("# id:", "# title:", "# version:", "# description:")

    old_lines = old_content.splitlines()
    new_lines = new_content.splitlines()

    # Pad the shorter side so zip covers all lines
    length = max(len(old_lines), len(new_lines))
    old_lines += [""] * (length - len(old_lines))
    new_lines += [""] * (length - len(new_lines))

    for old_line, new_line in zip(old_lines, new_lines):
        if old_line == new_line:
            continue
        # This line differs — it must be a header comment on both sides
        if not (
            old_line.startswith(_HEADER_PREFIX) and new_line.startswith(_HEADER_PREFIX)
        ):
            return False
    return True


_DEFAULT_BRANCH_PREFIX = "NOJIRA-WS-"


@dataclass
class SyncWorkflowContext:
    """All inputs needed to sync a single workflow template into a cloned repo."""

    repo_config: "Repo"
    git_repo: git.Repo
    clone_path: Path
    workflow_name: str
    workflow_options: "BaseWorkflowOptions"
    workflows_dir: Path
    target_dir: Path
    base_branch: str
    dry_run: bool
    branch_prefix: str = _DEFAULT_BRANCH_PREFIX
    workflow_def: "WorkflowDefinition | None" = None
    auto_push: bool = False


def _clone_or_update(url: str, clone_path: Path, *, cached: bool) -> git.Repo:
    """Return a git.Repo at *clone_path*, cloning or fetching as needed.

    When *cached* is True and *clone_path* already exists the repo is updated
    via ``git fetch`` (no full re-clone).  Otherwise a fresh clone is performed.
    """
    if cached and clone_path.exists():
        console.print(f"  [cyan]updating cache[/cyan]  {url}")
        repo = git.Repo(clone_path)
        repo.git.fetch("origin")
        return repo

    if cached:
        clone_path.parent.mkdir(parents=True, exist_ok=True)
        console.print(f"  [cyan]cloning (first run)[/cyan]  {url}")
    else:
        console.print(f"  [cyan]cloning[/cyan]  {url}")

    return git.Repo.clone_from(url, clone_path)


def _sync_workflow(ctx: SyncWorkflowContext) -> SyncAction:
    """Sync a single workflow template to the cloned repo.

    Returns a dict describing the action taken.
    """
    workflow_dir = ctx.workflows_dir / ctx.workflow_name
    template_file = find_template_file(workflow_dir)

    if template_file is None:
        console.print(
            f"    [yellow]warn[/yellow]  '{ctx.workflow_name}': no template file found, skipping"
        )
        return {
            "workflow": ctx.workflow_name,
            "status": "skipped",
            "reason": "template_not_found",
        }

    meta = parse_template_meta(template_file)
    template_version = meta.get("version", "0.0.0")
    title = meta.get("title", ctx.workflow_name)

    if ctx.workflow_def is not None:
        template_version = ctx.workflow_def.version
        title = ctx.workflow_def.name
        meta = {
            "title": ctx.workflow_def.name,
            "version": ctx.workflow_def.version,
            "description": ctx.workflow_def.description,
        }

    output_file = ctx.target_dir / f"{ctx.workflow_name}.yml"
    deployed_content: str | None = (
        output_file.read_text() if output_file.exists() else None
    )

    if not needs_update(
        template_version,
        deployed_content,
        workflow_id=ctx.workflow_def.id if ctx.workflow_def else ctx.workflow_name,
    ):
        console.print(
            f"    [green]✓[/green]  {ctx.workflow_name}  v{template_version}  (up to date)"
        )
        return {
            "workflow": ctx.workflow_name,
            "status": "up_to_date",
            "version": template_version,
        }

    deployed_version = (
        parse_deployed_meta(deployed_content).get("version")
        if deployed_content
        else None
    )
    from_label = f"v{deployed_version}" if deployed_version else "new"
    console.print(
        f"    [yellow]↑[/yellow]  {ctx.workflow_name}  "
        f"{from_label} → v{template_version}"
    )

    # Render and validate YAML syntax (runs for both dry-run and real runs)
    context = {
        "repo": ctx.repo_config,
        "meta": meta,
        "workflow": ctx.workflow_def,
        "options": ctx.workflow_options,
    }
    rendered = render_template(
        template_file, context, extra_search_paths=[ctx.workflows_dir]
    )
    try:
        yaml.safe_load(rendered)
        console.print(f"    [green]✓[/green]  {ctx.workflow_name}  YAML syntax OK")
    except yaml.YAMLError as exc:
        console.print(
            f"    [bold red]✗[/bold red]  {ctx.workflow_name}  invalid YAML: {exc}"
        )
        return {
            "workflow": ctx.workflow_name,
            "status": "error",
            "reason": "invalid_yaml",
            "detail": str(exc),
        }

    if ctx.dry_run:
        return {
            "workflow": ctx.workflow_name,
            "status": "would_update",
            "from_version": deployed_version,
            "to_version": template_version,
        }

    version_bump_only = deployed_content is not None and _is_version_bump_only(
        deployed_content, rendered
    )
    ctx.target_dir.mkdir(parents=True, exist_ok=True)
    output_file.write_text(rendered)

    commit_msg = (
        f"chore: bump {title} workflow to v{template_version}"
        if version_bump_only
        else f"chore: sync {title} workflow to v{template_version}"
    )

    if ctx.auto_push:
        # Push directly to the base branch (no feature branch, no PR)
        ctx.git_repo.git.checkout(ctx.base_branch)
        relative_path = str(output_file.relative_to(ctx.clone_path))
        ctx.git_repo.index.add([relative_path])
        ctx.git_repo.index.commit(f"{commit_msg}\n\nAutomated by workflow-sync")
        origin = ctx.git_repo.remote("origin")
        origin.push(refspec=f"{ctx.base_branch}:{ctx.base_branch}")
        console.print(
            f"    [bold green]✓[/bold green]  pushed directly to '{ctx.base_branch}'"
        )
        return {
            "workflow": ctx.workflow_name,
            "status": "pushed_to_main",
            "from_version": deployed_version,
            "to_version": template_version,
            "branch": ctx.base_branch,
        }

    branch_name = f"{ctx.branch_prefix}{ctx.workflow_name}-v{template_version}".replace(
        "/", "-"
    )

    # Always branch off the latest base branch
    ctx.git_repo.git.checkout(ctx.base_branch)
    try:
        ctx.git_repo.git.checkout("-b", branch_name)
    except git.GitCommandError:
        # Branch already exists locally – reuse it
        ctx.git_repo.git.checkout(branch_name)

    # Commit
    relative_path = str(output_file.relative_to(ctx.clone_path))
    ctx.git_repo.index.add([relative_path])
    ctx.git_repo.index.commit(f"{commit_msg}\n\nAutomated by workflow-sync")

    # Push
    origin = ctx.git_repo.remote("origin")
    try:
        origin.push(refspec=f"{branch_name}:{branch_name}")
    except git.GitCommandError as exc:
        msg = str(exc)
        if "already exists" in msg or "rejected" in msg:
            console.print(
                f"    [yellow]warn[/yellow]  branch '{branch_name}' already exists on remote"
            )
            return {
                "workflow": ctx.workflow_name,
                "status": "branch_exists",
                "branch": branch_name,
                "to_version": template_version,
                "pr_url": _pr_url(
                    ctx.repo_config.org,
                    ctx.repo_config.name,
                    ctx.base_branch,
                    branch_name,
                    title=(
                        f"chore: bump {title} to v{template_version}"
                        if version_bump_only
                        else f"chore: sync {title} to v{template_version}"
                    ),
                    body=(
                        f"Automated by [workflow-sync](https://github.com/8451/workflow-sync).\n\n"
                        f"| Field | Value |\n"
                        f"|---|---|\n"
                        f"| Workflow | `{ctx.workflow_name}` |\n"
                        f"| Version | `{deployed_version}` → `{template_version}` |\n"
                        f"| Change type | {'version bump only (no workflow changes)' if version_bump_only else 'workflow updated'} |\n"
                    ),
                ),
            }
        raise

    console.print(f"    [bold green]✓[/bold green]  pushed branch '{branch_name}'")
    return {
        "workflow": ctx.workflow_name,
        "status": "updated",
        "from_version": deployed_version,
        "to_version": template_version,
        "branch": branch_name,
        "pr_url": _pr_url(
            ctx.repo_config.org,
            ctx.repo_config.name,
            ctx.base_branch,
            branch_name,
            title=(
                f"chore: bump {title} to v{template_version}"
                if version_bump_only
                else f"chore: sync {title} to v{template_version}"
            ),
            body=(
                f"Automated by [workflow-sync](https://github.com/8451/workflow-sync).\n\n"
                f"| Field | Value |\n"
                f"|---|---|\n"
                f"| Workflow | `{ctx.workflow_name}` |\n"
                f"| Version | `{deployed_version}` → `{template_version}` |\n"
                f"| Change type | {'version bump only (no workflow changes)' if version_bump_only else 'workflow updated'} |\n"
            ),
        ),
    }


def sync_repo(
    repo_config: "Repo",
    config: "Config",
    workflows_dir: Path,
    *,
    dry_run: bool = False,
    cache_dir: Path | None = None,
    branch_prefix: str = _DEFAULT_BRANCH_PREFIX,
    auto_push: bool = False,
) -> list[SyncAction]:
    """Clone (or update from cache) *repo_config.url*, then sync every referenced workflow.

    When *cache_dir* is provided repos are kept on disk and updated with
    ``git fetch`` on subsequent runs, avoiding a full re-clone each time.

    Returns a list of action dicts, one per workflow.
    """
    actions: list[SyncAction] = []
    cached = cache_dir is not None

    if cached:
        clone_path = cache_dir / repo_config.name  # type: ignore[operator]
        dir_ctx: contextlib.AbstractContextManager = contextlib.nullcontext()
    else:
        _tmpdir = tempfile.TemporaryDirectory()
        clone_path = Path(_tmpdir.name) / repo_config.name
        dir_ctx = _tmpdir

    with dir_ctx:
        try:
            git_repo = _clone_or_update(repo_config.url, clone_path, cached=cached)
        except git.GitCommandError as exc:
            console.print(f"  [red]error[/red]  could not clone/update: {exc}")
            return [
                {"repo": repo_config.name, "status": "clone_failed", "error": str(exc)}
            ]

        base_branch = repo_config.branch or config.settings.base_branch
        try:
            git_repo.git.checkout(base_branch)
        except git.GitCommandError:
            try:
                git_repo.git.checkout("master")
                base_branch = "master"
            except git.GitCommandError as exc:
                console.print(f"  [red]error[/red]  cannot checkout base branch: {exc}")
                return [
                    {
                        "repo": repo_config.name,
                        "status": "checkout_failed",
                        "error": str(exc),
                    }
                ]

        # Reset to remote HEAD to discard any leftover local changes from a previous run
        git_repo.git.reset("--hard", f"origin/{base_branch}")
        git_repo.git.clean("-fd")

        if not repo_config.workflows:
            console.print("  [yellow]warn[/yellow]  no workflows defined, skipping")
            return [
                {
                    "repo": repo_config.name,
                    "status": "skipped",
                    "reason": "no_workflows",
                }
            ]

        for wf_ref in repo_config.workflows:
            # Per-workflow overrides take precedence over global settings
            wf_base_branch = (
                wf_ref.definition.base_branch
                if wf_ref.definition and wf_ref.definition.base_branch
                else base_branch
            )
            wf_target_dir = clone_path / (
                wf_ref.definition.workflows_target_dir
                if wf_ref.definition and wf_ref.definition.workflows_target_dir
                else config.settings.workflows_target_dir
            )
            action = _sync_workflow(
                SyncWorkflowContext(
                    repo_config=repo_config,
                    git_repo=git_repo,
                    clone_path=clone_path,
                    workflow_name=wf_ref.name,
                    workflow_options=wf_ref.options,
                    workflows_dir=workflows_dir,
                    target_dir=wf_target_dir,
                    base_branch=wf_base_branch,
                    dry_run=dry_run,
                    branch_prefix=branch_prefix,
                    workflow_def=wf_ref.definition,
                    auto_push=auto_push,
                )
            )
            actions.append(action)

    return actions


def sync_all(
    config: "Config",
    workflows_dir: Path,
    *,
    dry_run: bool = False,
    only_repo: str | None = None,
    cache_dir: Path | None = None,
    branch_prefix: str = _DEFAULT_BRANCH_PREFIX,
    auto_push: bool = False,
) -> dict[str, list[SyncAction]]:
    """Sync workflows for all (or one) repo(s) in *config*.

    Args:
        config: Validated configuration object.
        workflows_dir: Path to the local ``workflows/`` template directory.
        dry_run: If True, report what would be done without making changes.
        only_repo: When set, only sync the repo whose ``name`` matches.
        cache_dir: When set, repos are cloned here and reused across runs.
            On subsequent runs only ``git fetch + reset`` is performed.

    Returns:
        A mapping of repo name → list of sync actions.
    """
    results: dict[str, list[SyncAction]] = {}

    repos = [r for r in config.repos if only_repo is None or r.name == only_repo]

    if only_repo and not repos:
        console.print(f"[red]error[/red]  repo '{only_repo}' not found in config")
        return results

    for repo_config in repos:
        console.print(f"\n[bold]▶ {repo_config.name}[/bold]  ({repo_config.language})")
        results[repo_config.name] = sync_repo(
            repo_config,
            config,
            workflows_dir,
            dry_run=dry_run,
            cache_dir=cache_dir,
            branch_prefix=branch_prefix,
            auto_push=auto_push,
        )

    return results
