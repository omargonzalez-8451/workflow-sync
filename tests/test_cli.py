"""Tests for the CLI validate command error messages."""

import pytest
import yaml
from click.testing import CliRunner

from workflow_sync.cli import cli


@pytest.fixture()
def runner():
    return CliRunner()


def _write_config(tmp_path, data: dict):
    cfg = tmp_path / "workflows.yaml"
    cfg.write_text(yaml.dump(data))
    return str(cfg)


class TestValidateCmdErrorMessages:
    def test_shows_repo_name_on_validation_error(self, runner, tmp_path):
        cfg = _write_config(
            tmp_path,
            {
                "repos": [
                    {
                        "url": "git@github.com:org/my-repo.git",
                        "language": "python",
                        "workflows": [
                            {"name": "jira-review", "options": {"mode": "bad-mode"}}
                        ],
                    }
                ]
            },
        )
        result = runner.invoke(cli, ["validate", "--config", cfg])
        assert result.exit_code != 0
        assert "my-repo" in result.output

    def test_shows_got_value_for_bad_mode(self, runner, tmp_path):
        cfg = _write_config(
            tmp_path,
            {
                "repos": [
                    {
                        "url": "git@github.com:org/my-repo.git",
                        "language": "python",
                        "workflows": [
                            {"name": "jira-review", "options": {"mode": "bad-mode"}}
                        ],
                    }
                ]
            },
        )
        result = runner.invoke(cli, ["validate", "--config", cfg])
        assert result.exit_code != 0
        assert "bad-mode" in result.output

    def test_shows_got_value_for_invalid_language(self, runner, tmp_path):
        cfg = _write_config(
            tmp_path,
            {
                "repos": [
                    {
                        "url": "git@github.com:org/my-repo.git",
                        "language": "cobol",
                        "workflows": [{"name": "jira-review"}],
                    }
                ]
            },
        )
        result = runner.invoke(cli, ["validate", "--config", cfg])
        assert result.exit_code != 0
        assert "cobol" in result.output

    def test_shows_repo_name_for_language_error(self, runner, tmp_path):
        cfg = _write_config(
            tmp_path,
            {
                "repos": [
                    {
                        "url": "git@github.com:org/my-repo.git",
                        "language": "cobol",
                        "workflows": [{"name": "jira-review"}],
                    }
                ]
            },
        )
        result = runner.invoke(cli, ["validate", "--config", cfg])
        assert result.exit_code != 0
        assert "my-repo" in result.output

    def test_valid_config_exits_zero(self, runner, tmp_path):
        cfg = _write_config(
            tmp_path,
            {
                "repos": [
                    {
                        "url": "git@github.com:org/my-repo.git",
                        "language": "python",
                        "workflows": [{"name": "jira-review"}],
                    }
                ]
            },
        )
        result = runner.invoke(cli, ["validate", "--config", cfg])
        assert result.exit_code == 0
        assert "Schema valid" in result.output

    def test_missing_config_file(self, runner, tmp_path):
        result = runner.invoke(
            cli, ["validate", "--config", str(tmp_path / "nope.yaml")]
        )
        assert result.exit_code != 0
        assert "not found" in result.output
