"""Tests for config loading and validation helpers."""

import pytest
import yaml
from pathlib import Path

from workflow_sync.base_schemas import Config
from workflow_sync.validator import load_config, validate_workflows_exist


class TestLoadConfig:
    def test_loads_valid_file(self, config_file):
        cfg = load_config(config_file)
        assert isinstance(cfg, Config)
        assert cfg.repos[0].name == "my-app"

    def test_raises_on_missing_file(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_config(tmp_path / "missing.yaml")

    def test_raises_on_invalid_schema(self, tmp_path):
        bad = tmp_path / "bad.yaml"
        bad.write_text(yaml.dump({"repos": [{"name": "x"}]}))  # missing url + language
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            load_config(bad)

    def test_raises_on_invalid_yaml(self, tmp_path):
        bad = tmp_path / "bad.yaml"
        bad.write_text("repos: [\n  - name: broken")
        with pytest.raises(yaml.YAMLError):
            load_config(bad)


class TestValidateWorkflowsExist:
    def test_all_present(self, sample_config_data, workflows_dir):
        cfg = Config.model_validate(sample_config_data)
        errors = validate_workflows_exist(cfg, workflows_dir)
        assert errors == []

    def test_missing_template(self, sample_config_data, tmp_path):
        cfg = Config.model_validate(sample_config_data)
        # Pass an empty dir — no templates exist
        errors = validate_workflows_exist(cfg, tmp_path)
        assert (
            len(errors) == 1
        )  # jira-review is missing (both workflow refs share the same template)

    def test_repo_with_no_workflows(self, workflows_dir):
        cfg_data = {
            "repos": [
                {
                    "url": "https://github.com/org/no-workflows-repo.git",
                    "language": "python",
                    "workflows": [],
                }
            ]
        }
        from workflow_sync.base_schemas import Config

        cfg = Config.model_validate(cfg_data)
        errors = validate_workflows_exist(cfg, workflows_dir)
        assert len(errors) == 1
        assert "no workflows" in errors[0].lower()

    def test_partial_missing(self, sample_config_data, workflows_dir):
        cfg = Config.model_validate(sample_config_data)
        # Remove the jira-review template
        import shutil

        shutil.rmtree(workflows_dir / "jira-review")
        errors = validate_workflows_exist(cfg, workflows_dir)
        assert len(errors) == 1
        assert "jira-review" in errors[0]

    def test_missing_header_partial(self, sample_config_data, workflows_dir):
        cfg = Config.model_validate(sample_config_data)
        # Overwrite template without the required extends line
        (workflows_dir / "jira-review" / "workflow.yml.j2").write_text(
            "# title: JIRA Validator\n# version: 2.0.0\nname: JIRA Validator\n"
        )
        errors = validate_workflows_exist(cfg, workflows_dir)
        assert len(errors) == 1
        assert "jira-review" in errors[0]
        assert "_common_partials/_workflow-base.yml.j2" in errors[0]
