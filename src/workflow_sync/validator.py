"""Load and validate the workflows.yaml configuration file."""

from pathlib import Path

import yaml
from pydantic import ValidationError

from .base_schemas import Config


def load_config(config_path: Path) -> Config:
    """Load workflows.yaml and validate it against the schema.

    Raises:
        FileNotFoundError: if the config file does not exist.
        yaml.YAMLError: if the file is not valid YAML.
        pydantic.ValidationError: if the structure does not match the schema.
    """
    with open(config_path) as fh:
        data = yaml.safe_load(fh)

    return Config.model_validate(data)


def validate_workflows_exist(config: Config, workflows_dir: Path) -> list[str]:
    """Check that every workflow name referenced in the config has a matching
    template folder under *workflows_dir*.

    Also warns when a repo has no workflows defined.
    Each unique template name is checked only once.
    Returns a list of error messages (empty means all good).
    """
    _HEADER_EXTENDS = "{% extends '_common_partials/_workflow-base.yml.j2' %}"

    errors: list[str] = []
    seen: set[str] = set()
    for repo in config.repos:
        if not repo.workflows:
            errors.append(f"Repo '{repo.name}' has no workflows defined")
            continue
        for wf in repo.workflows:
            if wf.name in seen:
                continue
            seen.add(wf.name)
            template_dir = workflows_dir / wf.name
            if not template_dir.is_dir():
                errors.append(
                    f"Workflow template '{wf.name}' not found: "
                    f"expected directory '{template_dir}'"
                )
                continue
            # Find the main template file and verify it uses the header partial
            template_file = next(template_dir.glob("*.j2"), None)
            if template_file is not None:
                first_line = (
                    template_file.read_text().splitlines()[0]
                    if template_file.stat().st_size
                    else ""
                )
                if first_line.strip() != _HEADER_EXTENDS:
                    errors.append(
                        f"Workflow template '{wf.name}' must start with "
                        f"`{_HEADER_EXTENDS}` (first line of {template_file.name})"
                    )
    return errors
