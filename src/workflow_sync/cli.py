"""CLI entry point for workflow-sync."""

from __future__ import annotations

import re
from pathlib import Path

import click
import yaml
from pydantic import ValidationError
from rich.console import Console
from rich.table import Table

from .validator import load_config, validate_workflows_exist
from .sync import sync_all

console = Console()

_DEFAULT_CONFIG = "workflows.yaml"
# Built-in workflow templates live alongside their schemas.py inside the package.
_DEFAULT_WORKFLOWS_DIR = str(Path(__file__).parent / "workflows")
_URL_RE = re.compile(r"[:/]([^/]+)/([^/]+?)(?:\.git)?$")


@click.group()
@click.version_option(package_name="workflow-sync")
def cli() -> None:
    """workflow-sync — keep GitHub Actions workflows in sync across many repos."""


# ---------------------------------------------------------------------------
# validate
# ---------------------------------------------------------------------------


@cli.command("validate")
@click.option(
    "--config",
    "-c",
    default=_DEFAULT_CONFIG,
    show_default=True,
    help="Path to the workflows.yaml config file.",
)
@click.option(
    "--workflows-dir",
    "-w",
    default=_DEFAULT_WORKFLOWS_DIR,
    show_default=True,
    help="Path to the directory containing workflow templates.",
)
def validate_cmd(config: str, workflows_dir: str) -> None:
    """Validate workflows.yaml against the schema and check templates exist."""
    config_path = Path(config)
    workflows_path = Path(workflows_dir)

    if not config_path.exists():
        console.print(f"[red]✗[/red]  Config file not found: {config_path}")
        raise SystemExit(1)

    # Load raw data first so we can enrich validation errors with repo names.
    with open(config_path) as fh:
        raw_data = yaml.safe_load(fh)
    raw_repos: list[dict] = raw_data.get("repos", []) if isinstance(raw_data, dict) else []

    try:
        cfg = load_config(config_path)
        console.print(f"[green]✓[/green]  Schema valid")
    except ValidationError as exc:
        for error in exc.errors():
            loc = error.get("loc", ())
            # Enrich error location with repo name when available.
            # loc is e.g. ('repos', 1, 'workflows', 0, 'mode')
            repo_hint = ""
            if len(loc) >= 2 and loc[0] == "repos" and isinstance(loc[1], int):
                repo_index = loc[1]
                repo_entry = raw_repos[repo_index] if repo_index < len(raw_repos) else {}
                url = repo_entry.get("url", "")
                match = _URL_RE.search(url)
                repo_name = match.group(2) if match else repo_entry.get("name") or f"index {repo_index}"
                repo_hint = f" [dim](repo: {repo_name})[/dim]"
            loc_str = ".".join(str(part) for part in loc)
            input_val = error.get("input")
            value_hint = f" [dim](got: {input_val!r})[/dim]" if input_val is not None else ""
            console.print(f"[red]✗  Validation error:[/red] {loc_str}{repo_hint}{value_hint}\n   {error['msg']}")
        raise SystemExit(1) from exc
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]✗  Schema validation failed:[/red] {exc}")
        raise SystemExit(1) from exc

    errors = validate_workflows_exist(cfg, workflows_path)
    if errors:
        for err in errors:
            console.print(f"[red]✗[/red]  {err}")
        raise SystemExit(1)

    console.print(f"[green]✓[/green]  All workflow templates found")

    table = Table(title="Configuration summary", show_lines=True)
    table.add_column("Repository", style="cyan", no_wrap=True)
    table.add_column("Language", style="magenta")
    table.add_column("Workflows")
    table.add_column("Base branch")

    for repo in cfg.repos:
        table.add_row(
            repo.name,
            repo.language,
            ", ".join(wf.name for wf in repo.workflows) or "—",
            cfg.settings.base_branch,
        )

    console.print(table)


# ---------------------------------------------------------------------------
# sync
# ---------------------------------------------------------------------------


@cli.command("sync")
@click.option(
    "--config",
    "-c",
    default=_DEFAULT_CONFIG,
    show_default=True,
    help="Path to the workflows.yaml config file.",
)
@click.option(
    "--workflows-dir",
    "-w",
    default=_DEFAULT_WORKFLOWS_DIR,
    show_default=True,
    help="Path to the directory containing workflow templates.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Show what would be synced without pushing any changes.",
)
@click.option(
    "--repo",
    "-r",
    default=None,
    help="Limit sync to a single repository name.",
)
@click.option(
    "--cache-dir",
    default=".repos",
    show_default=True,
    help="Directory for persistent repo clones. Pass an empty string to disable caching.",
)
def sync_cmd(
    config: str, workflows_dir: str, dry_run: bool, repo: str | None, cache_dir: str
) -> None:
    """Fetch/pull repos and push workflow updates as new branches."""
    config_path = Path(config)
    workflows_path = Path(workflows_dir)

    if not config_path.exists():
        console.print(f"[red]✗[/red]  Config file not found: {config_path}")
        raise SystemExit(1)

    try:
        cfg = load_config(config_path)
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]✗  Config error:[/red] {exc}")
        raise SystemExit(1) from exc

    if dry_run:
        console.print(
            "[bold yellow]dry-run mode — no changes will be pushed[/bold yellow]"
        )

    cache_path: Path | None = Path(cache_dir) if cache_dir else None
    if cache_path is not None:
        cache_path.mkdir(parents=True, exist_ok=True)
        console.print(f"[dim]repo cache:[/dim]  {cache_path.resolve()}")

    results = sync_all(
        cfg, workflows_path, dry_run=dry_run, only_repo=repo, cache_dir=cache_path
    )

    # Summary table
    console.print()
    table = Table(title="Sync summary", show_lines=True)
    table.add_column("Repository", style="cyan", no_wrap=True)
    table.add_column("Workflow", style="magenta")
    table.add_column("Status")
    table.add_column("Details")

    status_styles = {
        "updated": "[green]updated[/green]",
        "would_update": "[yellow]would update[/yellow]",
        "up_to_date": "[dim]up to date[/dim]",
        "skipped": "[yellow]skipped[/yellow]",
        "branch_exists": "[yellow]branch exists[/yellow]",
        "clone_failed": "[red]clone failed[/red]",
        "checkout_failed": "[red]checkout failed[/red]",
    }

    for repo_name, actions in results.items():
        for action in actions:
            status_key = action.get("status", "unknown")
            styled_status = status_styles.get(status_key, status_key)
            if "from_version" in action and "to_version" in action:
                from_v = action["from_version"]
                to_v = action["to_version"]
                from_str = from_v if from_v == "none" else f"v{from_v}"
                to_str = to_v if to_v == "none" else f"v{to_v}"
                details = f"{from_str} → {to_str}"
            else:
                details = action.get(
                    "branch", action.get("error", action.get("reason", ""))
                )
            table.add_row(
                repo_name, action.get("workflow", "—"), styled_status, details or ""
            )

    console.print(table)

    # Print PR links for any branches that were pushed or already exist
    pr_links = [
        (repo_name, action["workflow"], action["pr_url"])
        for repo_name, actions in results.items()
        for action in actions
        if action.get("pr_url")
    ]
    if pr_links and not dry_run:
        console.print()
        console.print("[bold]Open pull requests:[/bold]")
        for repo_name, workflow, url in pr_links:
            console.print(f"  [cyan]{repo_name}[/cyan] / [magenta]{workflow}[/magenta]")
            console.print(f"  [link={url}]{url}[/link]")
