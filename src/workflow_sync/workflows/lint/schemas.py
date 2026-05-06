"""Options schema for the lint workflow template."""

from pydantic import Field

from workflow_sync.base_schemas import BaseWorkflowOptions, WorkflowDefinition
from workflow_sync.enums import Language

WORKFLOW_DEF = WorkflowDefinition(
    name="Lint",
    description=(
        "Runs linting and format checks. Supports 'python' (ruff) and 'node' (eslint/prettier). "
        "Validated at config time — repo.language must be 'python' or 'node'."
    ),
    version="1.0.0",
    supported_languages=[Language.PYTHON, Language.JAVASCRIPT, Language.TYPESCRIPT],
)


class LintOptions(BaseWorkflowOptions):
    """Options for the lint workflow template."""

    python_version: str = Field(
        default="3.12",
        description="Python version to set up (python repos only)",
    )
    ruff_version: str = Field(
        default="0.4.4",
        description="Pinned ruff version to install (python repos only)",
    )
    node_version: str = Field(
        default="20",
        description="Node.js version to set up (node repos only)",
    )
