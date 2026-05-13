"""Pydantic schemas for workflows.yaml config validation."""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from .enums import Language

# Matches the org/repo path segment in both SSH and HTTPS Git URLs:
#   git@github.com:org/repo.git  →  group(1)=org  group(2)=repo
#   https://github.com/org/repo.git  →  group(1)=org  group(2)=repo
_URL_RE = re.compile(r"[:/]([^/]+)/([^/]+?)(?:\.git)?$")


# ---------------------------------------------------------------------------
# Workflow definition — static metadata declared by each workflow
# ---------------------------------------------------------------------------


class WorkflowDefinition(BaseModel):
    """Static metadata for a workflow, declared in its schemas.py.

    Passed to the Jinja2 context as ``workflow`` so templates can reference
    ``{{ workflow.name }}``, ``{{ workflow.version }}``, etc.

    ``id`` is the workflow folder name (e.g. ``jira-review``) and is set
    automatically by the registry — do not set it manually in schemas.py.
    """

    id: str = Field(
        default="", description="Workflow folder name (set by registry, not schemas.py)"
    )
    name: str = Field(..., description="Human-readable workflow title")
    description: str = Field(
        default="", description="Short description of what the workflow does"
    )
    version: str = Field(..., description="Semantic version string (e.g. '2.0.0')")
    supported_languages: list[Language] | None = Field(
        default=None,
        description="If set, repos using this workflow must have their language in this list",
    )

    @field_validator("version")
    @classmethod
    def _validate_version(cls, v: str) -> str:
        if not re.fullmatch(r"\d+\.\d+\.\d+", v):
            raise ValueError(f"version must be in int.int.int format, got '{v}'")
        return v

    base_branch: str | None = Field(
        default=None,
        description="Override the global base_branch for this workflow (falls back to settings.base_branch)",
    )
    workflows_target_dir: str | None = Field(
        default=None,
        description="Override the global workflows_target_dir for this workflow (falls back to settings.workflows_target_dir)",
    )


# ---------------------------------------------------------------------------
# Workflow options — base class (per-workflow subclasses live alongside their
# template in src/workflow_sync/workflows/<name>.py)
# ---------------------------------------------------------------------------


class BaseWorkflowOptions(BaseModel):
    """Base options applicable to any workflow template."""

    runs_on: str = Field(
        default="ubuntu-latest", description="GitHub Actions runner label"
    )


@dataclass
class WorkflowEntry:
    """Registry entry binding a workflow's definition to its options class."""

    definition: WorkflowDefinition
    options_class: type[BaseWorkflowOptions]


# ---------------------------------------------------------------------------
# Registry: maps workflow template name → WorkflowEntry.
# Unknown workflow names fall back to BaseWorkflowOptions with no definition.
# ---------------------------------------------------------------------------


def _build_registry() -> dict[str, WorkflowEntry]:
    """Load options classes from each workflow folder's schemas.py.

    Uses importlib to support workflow folder names with hyphens (not valid
    Python identifiers), keeping all workflow code co-located with its template.
    """
    import importlib.util  # noqa: PLC0415

    _workflows_dir = Path(__file__).parent / "workflows"

    def _load(
        workflow_name: str, options_class_name: str, def_name: str = "WORKFLOW_DEF"
    ) -> WorkflowEntry:
        options_file = _workflows_dir / workflow_name / "schemas.py"
        spec = importlib.util.spec_from_file_location(
            f"_wf_options_{workflow_name.replace('-', '_')}",
            options_file,
        )
        mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        defn = getattr(mod, def_name)
        # Stamp the folder name as the stable id
        defn = defn.model_copy(update={"id": workflow_name})
        return WorkflowEntry(
            definition=defn,
            options_class=getattr(mod, options_class_name),
        )

    return {
        "jira-review": _load("jira-review", "JiraReviewOptions"),
        "lint": _load("lint", "LintOptions"),
    }


WORKFLOW_REGISTRY: dict[str, WorkflowEntry] = _build_registry()


class WorkflowRef(BaseModel):
    """Reference to a workflow template to apply to a repository."""

    name: str = Field(
        ..., description="Workflow template name (must match a folder under workflows/)"
    )
    options: BaseWorkflowOptions = Field(
        default_factory=BaseWorkflowOptions,
        description="Typed options validated against the workflow's schema in WORKFLOW_REGISTRY",
    )
    definition: WorkflowDefinition | None = Field(
        default=None,
        description="Workflow definition (name, description, version) from WORKFLOW_REGISTRY",
    )

    @model_validator(mode="before")
    @classmethod
    def _parse_options(cls, data: dict) -> dict:
        name = data.get("name", "")
        raw = data.get("options") or {}
        if isinstance(raw, BaseWorkflowOptions):
            return data  # already a typed instance — nothing to do
        entry = WORKFLOW_REGISTRY.get(name)
        if entry is not None:
            data["options"] = entry.options_class.model_validate(raw)
            data["definition"] = entry.definition
        else:
            data["options"] = BaseWorkflowOptions.model_validate(raw)
        return data


class Repo(BaseModel):
    """A repository managed by workflow-sync."""

    url: str = Field(..., description="Git clone URL (SSH or HTTPS)")
    org: str = Field("", description="Organisation name, derived from URL")
    name: str = Field("", description="Repository name, derived from URL")
    language: Language = Field(
        ..., description="Primary programming language (e.g. python, javascript)"
    )
    branch: str | None = Field(
        default=None,
        description="Override the base branch for this repo (falls back to settings.base_branch)",
    )
    workflows: list[WorkflowRef] = Field(
        default_factory=list,
        description="Workflow templates to apply to this repository",
    )

    @model_validator(mode="before")
    @classmethod
    def _derive_from_url(cls, data: dict) -> dict:
        url = data.get("url", "")
        match = _URL_RE.search(url)
        if match:
            if not data.get("org"):
                data["org"] = match.group(1)
            if not data.get("name"):
                data["name"] = match.group(2)
        return data

    @model_validator(mode="after")
    def _validate_workflow_languages(self) -> "Repo":
        for wf in self.workflows:
            if wf.definition and wf.definition.supported_languages:
                if self.language not in wf.definition.supported_languages:
                    allowed = ", ".join(
                        f"'{l}'" for l in wf.definition.supported_languages
                    )
                    raise ValueError(
                        f"workflow '{wf.name}' only supports languages [{allowed}], "
                        f"but repo '{self.name}' has language '{self.language}'"
                    )
        return self


class Settings(BaseModel):
    """Global settings applied to all sync operations."""

    base_branch: str = Field(default="main", description="Branch to base sync PRs from")
    workflows_target_dir: str = Field(
        default=".github/workflows",
        description="Target directory inside each repo where workflows are written",
    )


class Config(BaseModel):
    """Root config schema matching the top-level workflows.yaml structure."""

    settings: Settings = Field(default_factory=Settings)
    repos: list[Repo] = Field(..., description="Repositories to manage")
