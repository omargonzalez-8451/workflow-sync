"""Options schema for the jira-review workflow template."""

from typing import Literal

from pydantic import Field, computed_field

from workflow_sync.base_schemas import BaseWorkflowOptions, WorkflowDefinition

WORKFLOW_DEF = WorkflowDefinition(
    name="JIRA Validator — AI Code Review",
    description=(
        "Validates PR branch against JIRA ticket requirements and runs an AI code review. "
        "Set options.mode to 'copilot' (default), 'anthropic', or 'anthropic-agentic'."
    ),
    version="2.0.8",
)

# Maps each Anthropic mode to the default model ID.
_MODE_MODELS: dict[str, str] = {
    "anthropic": "claude-opus-4-5",
    "anthropic-agentic": "claude-opus-4-5",
}


class JiraReviewOptions(BaseWorkflowOptions):
    """Options for the unified jira-review workflow template.

    Set ``mode`` to choose the AI review strategy:
    - ``copilot``           — requests GitHub Copilot as a PR reviewer (default, no extra secrets)
    - ``anthropic``         — calls the Anthropic Messages API and posts a review comment
    - ``anthropic-agentic`` — uses anthropics/claude-code-action@beta for a full agentic review
    """

    mode: Literal["copilot", "anthropic", "anthropic-agentic"] = Field(
        default="copilot",
        description="Review strategy: 'copilot' | 'anthropic' | 'anthropic-agentic'",
    )

    environment: str | None = Field(
        default="all",
        description="GitHub Environment name where JIRA secrets are stored (required if secrets were added to an environment rather than the repository directly)",
    )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def model(self) -> str:
        """Anthropic model ID derived from ``mode``. Empty string for 'copilot'."""
        return _MODE_MODELS.get(self.mode, "")
