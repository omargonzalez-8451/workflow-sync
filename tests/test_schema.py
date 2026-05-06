"""Tests for the Pydantic schema models."""

import pytest
from pydantic import ValidationError

from workflow_sync.base_schemas import (
    BaseWorkflowOptions,
    Config,
    Repo,
    Settings,
    WorkflowDefinition,
    WorkflowRef,
    WORKFLOW_REGISTRY,
)
from workflow_sync.enums import Language

# JiraReviewOptions lives in src/workflow_sync/workflows/jira-review/schemas.py.
# The hyphen makes it unreachable via normal imports; access it through the registry.
JiraReviewOptions = WORKFLOW_REGISTRY["jira-review"].options_class
LintOptions = WORKFLOW_REGISTRY["lint"].options_class


class TestWorkflowDefinitionVersion:
    def _make(self, version: str) -> WorkflowDefinition:
        return WorkflowDefinition(name="Test", version=version)

    @pytest.mark.parametrize("version", ["1.0.0", "2.3.4", "0.0.1", "10.20.30"])
    def test_valid_versions(self, version):
        defn = self._make(version)
        assert defn.version == version

    @pytest.mark.parametrize(
        "version",
        [
            "1.0",  # only two parts
            "1",  # only one part
            "1.0.0.0",  # four parts
            "v1.0.0",  # leading 'v'
            "1.0.a",  # non-integer part
            "1.0.0-rc1",  # pre-release suffix
            "",  # empty string
        ],
    )
    def test_invalid_versions(self, version):
        with pytest.raises(ValidationError, match="int.int.int"):
            self._make(version)


class TestWorkflowRef:
    def test_valid_unknown_workflow_uses_base_options(self):
        wf = WorkflowRef(name="custom-workflow")
        assert wf.name == "custom-workflow"
        assert isinstance(wf.options, BaseWorkflowOptions)
        assert wf.definition is None

    def test_missing_name(self):
        with pytest.raises(ValidationError):
            WorkflowRef.model_validate({})

    def test_jira_review_defaults_to_copilot_mode(self):
        wf = WorkflowRef.model_validate({"name": "jira-review"})
        assert isinstance(wf.options, JiraReviewOptions)
        assert wf.options.mode == "copilot"
        assert wf.options.runs_on == "ubuntu-latest"
        assert isinstance(wf.definition, WorkflowDefinition)
        assert wf.definition.id == "jira-review"
        assert wf.definition.version == "2.0.0"
        assert wf.definition.name == "JIRA Validator — AI Code Review"

    def test_jira_review_anthropic_mode(self):
        wf = WorkflowRef.model_validate(
            {"name": "jira-review", "options": {"mode": "anthropic"}}
        )
        assert isinstance(wf.options, JiraReviewOptions)
        assert wf.options.mode == "anthropic"
        assert wf.options.model == "claude-opus-4-5"

    def test_jira_review_agentic_mode(self):
        wf = WorkflowRef.model_validate(
            {"name": "jira-review", "options": {"mode": "anthropic-agentic"}}
        )
        assert isinstance(wf.options, JiraReviewOptions)
        assert wf.options.mode == "anthropic-agentic"

    def test_jira_review_invalid_mode_rejected(self):
        with pytest.raises(ValidationError):
            WorkflowRef.model_validate(
                {"name": "jira-review", "options": {"mode": "unknown-mode"}}
            )

    def test_runs_on_override(self):
        wf = WorkflowRef.model_validate(
            {"name": "jira-review", "options": {"runs_on": "self-hosted"}}
        )
        assert wf.options.runs_on == "self-hosted"

    def test_registry_contains_jira_review(self):
        assert "jira-review" in WORKFLOW_REGISTRY
        entry = WORKFLOW_REGISTRY["jira-review"]
        assert entry.options_class is JiraReviewOptions
        assert isinstance(entry.definition, WorkflowDefinition)
        assert entry.definition.id == "jira-review"
        assert entry.definition.version == "2.0.0"


class TestRepo:
    def test_derives_name_and_org_from_https_url(self):
        repo = Repo(
            url="https://github.com/my-org/my-app.git", language="python", workflows=[]
        )
        assert repo.name == "my-app"
        assert repo.org == "my-org"
        assert repo.workflows == []

    def test_derives_name_and_org_from_ssh_url(self):
        repo = Repo.model_validate(
            {
                "url": "git@github.com:my-org/my-app.git",
                "language": "python",
            }
        )
        assert repo.name == "my-app"
        assert repo.org == "my-org"

    def test_explicit_name_and_org_not_overridden(self):
        repo = Repo.model_validate(
            {
                "url": "https://github.com/my-org/my-app.git",
                "name": "custom-name",
                "org": "custom-org",
                "language": "python",
            }
        )
        assert repo.name == "custom-name"
        assert repo.org == "custom-org"

    def test_missing_url(self):
        with pytest.raises(ValidationError):
            Repo.model_validate({"language": "python", "workflows": []})

    def test_missing_language(self):
        with pytest.raises(ValidationError):
            Repo.model_validate({"url": "https://github.com/org/app", "workflows": []})


class TestSettings:
    def test_defaults(self):
        s = Settings()
        assert s.base_branch == "main"
        assert s.workflows_target_dir == ".github/workflows"

    def test_override(self):
        s = Settings(base_branch="develop")
        assert s.base_branch == "develop"


class TestConfig:
    def test_valid(self, sample_config_data):
        cfg = Config.model_validate(sample_config_data)
        assert len(cfg.repos) == 1
        assert cfg.repos[0].name == "my-app"
        assert cfg.repos[0].org == "my-org"
        assert len(cfg.repos[0].workflows) == 2

    def test_default_settings(self):
        cfg = Config.model_validate({"repos": []})
        assert cfg.settings.base_branch == "main"

    def test_custom_settings(self):
        data = {"settings": {"base_branch": "develop"}, "repos": []}
        cfg = Config.model_validate(data)
        assert cfg.settings.base_branch == "develop"

    def test_missing_repos_key(self):
        with pytest.raises(ValidationError):
            Config.model_validate({})

    def test_empty_repos_allowed(self):
        cfg = Config.model_validate({"repos": []})
        assert cfg.repos == []


# ---------------------------------------------------------------------------
# Language enum
# ---------------------------------------------------------------------------


class TestLanguageEnum:
    def test_values_are_plain_strings(self):
        # StrEnum — compares equal to its string value
        assert Language.PYTHON == "python"
        assert Language.JAVASCRIPT == "javascript"
        assert Language.TYPESCRIPT == "typescript"
        assert Language.GO == "go"
        assert Language.JAVA == "java"

    def test_all_required_values_present(self):
        values = {lang.value for lang in Language}
        assert {"python", "javascript", "typescript", "go", "java"}.issubset(values)

    def test_invalid_language_rejected_on_repo(self):
        with pytest.raises(ValidationError):
            Repo.model_validate({"url": "https://github.com/org/app.git", "language": "cobol"})

    @pytest.mark.parametrize(
        "lang",
        ["python", "javascript", "typescript", "go", "java", "rust", "ruby", "csharp", "cpp", "shell"],
    )
    def test_valid_language_accepted(self, lang):
        repo = Repo.model_validate({"url": "https://github.com/org/app.git", "language": lang})
        assert repo.language == lang


# ---------------------------------------------------------------------------
# WorkflowDefinition.supported_languages
# ---------------------------------------------------------------------------


class TestWorkflowDefinitionSupportedLanguages:
    def test_defaults_to_none(self):
        defn = WorkflowDefinition(name="Test", version="1.0.0")
        assert defn.supported_languages is None

    def test_accepts_language_list(self):
        defn = WorkflowDefinition(
            name="Test",
            version="1.0.0",
            supported_languages=[Language.PYTHON, Language.GO],
        )
        assert Language.PYTHON in defn.supported_languages
        assert Language.GO in defn.supported_languages


# ---------------------------------------------------------------------------
# Repo workflow language guard (_validate_workflow_languages)
# ---------------------------------------------------------------------------


class TestRepoWorkflowLanguageGuard:
    def test_accepted_when_language_matches_supported(self):
        repo = Repo.model_validate(
            {
                "url": "https://github.com/org/app.git",
                "language": "python",
                "workflows": [{"name": "lint"}],
            }
        )
        assert repo.language == Language.PYTHON

    def test_rejected_when_language_not_in_supported(self):
        with pytest.raises(ValidationError, match="only supports languages"):
            Repo.model_validate(
                {
                    "url": "https://github.com/org/app.git",
                    "language": "go",
                    "workflows": [{"name": "lint"}],
                }
            )

    def test_error_mentions_repo_name(self):
        with pytest.raises(ValidationError) as exc_info:
            Repo.model_validate(
                {
                    "url": "https://github.com/org/my-go-app.git",
                    "language": "go",
                    "workflows": [{"name": "lint"}],
                }
            )
        assert "my-go-app" in str(exc_info.value)

    def test_error_mentions_workflow_name(self):
        with pytest.raises(ValidationError) as exc_info:
            Repo.model_validate(
                {
                    "url": "https://github.com/org/my-go-app.git",
                    "language": "go",
                    "workflows": [{"name": "lint"}],
                }
            )
        assert "lint" in str(exc_info.value)

    def test_no_restriction_when_supported_languages_none(self):
        # jira-review has no supported_languages — any language is allowed
        repo = Repo.model_validate(
            {
                "url": "https://github.com/org/app.git",
                "language": "go",
                "workflows": [{"name": "jira-review"}],
            }
        )
        assert repo.language == Language.GO

    @pytest.mark.parametrize("lang", ["python", "javascript", "typescript"])
    def test_all_lint_supported_languages_accepted(self, lang):
        repo = Repo.model_validate(
            {
                "url": "https://github.com/org/app.git",
                "language": lang,
                "workflows": [{"name": "lint"}],
            }
        )
        assert repo.language == lang


# ---------------------------------------------------------------------------
# lint workflow registry + LintOptions
# ---------------------------------------------------------------------------


class TestLintWorkflowRegistry:
    def test_lint_in_registry(self):
        assert "lint" in WORKFLOW_REGISTRY

    def test_lint_definition_metadata(self):
        entry = WORKFLOW_REGISTRY["lint"]
        assert entry.definition.id == "lint"
        assert entry.definition.version == "1.0.0"
        assert entry.definition.name == "Lint"

    def test_lint_supported_languages(self):
        langs = WORKFLOW_REGISTRY["lint"].definition.supported_languages
        assert Language.PYTHON in langs
        assert Language.JAVASCRIPT in langs
        assert Language.TYPESCRIPT in langs

    def test_lint_options_class(self):
        entry = WORKFLOW_REGISTRY["lint"]
        assert entry.options_class is LintOptions

    def test_lint_options_defaults(self):
        wf = WorkflowRef.model_validate({"name": "lint"})
        assert isinstance(wf.options, LintOptions)
        assert wf.options.python_version == "3.12"
        assert wf.options.ruff_version == "0.4.4"
        assert wf.options.node_version == "20"
        assert wf.options.runs_on == "ubuntu-latest"

    def test_lint_options_override(self):
        wf = WorkflowRef.model_validate(
            {"name": "lint", "options": {"python_version": "3.11", "node_version": "18"}}
        )
        assert wf.options.python_version == "3.11"
        assert wf.options.node_version == "18"
