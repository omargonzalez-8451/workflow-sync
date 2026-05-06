"""Shared pytest fixtures."""

from pathlib import Path

import pytest
import yaml


@pytest.fixture()
def sample_config_data() -> dict:
    return {
        "repos": [
            {
                "url": "https://github.com/my-org/my-app.git",
                "language": "python",
                "workflows": [
                    {"name": "jira-review", "options": {"mode": "copilot"}},
                    {"name": "jira-review", "options": {"mode": "anthropic"}},
                ],
            }
        ]
    }


@pytest.fixture()
def config_file(tmp_path: Path, sample_config_data: dict) -> Path:
    path = tmp_path / "workflows.yaml"
    path.write_text(yaml.dump(sample_config_data))
    return path


@pytest.fixture()
def workflows_dir(tmp_path: Path) -> Path:
    """Return a workflows directory populated with a minimal jira-review template."""
    base = tmp_path / "workflows"
    d = base / "jira-review"
    d.mkdir(parents=True)
    (d / "workflow.yml.j2").write_text(
        "{% extends '_common_partials/_workflow-base.yml.j2' %}\n{% block workflow_content %}\nname: JIRA Validator\n{% endblock %}\n"
    )
    return base
