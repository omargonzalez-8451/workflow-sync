# workflow-sync

A CLI tool to sync and standardize GitHub Actions workflows across multiple repositories from a single source of truth.

## Concept

Define your repos and which workflow templates they should use in `workflows.yaml`. Store your canonical workflow templates in the `src/workflow_sync/workflows/` directory. Run `workflow-sync sync` to automatically create branches in each repo with the latest workflow versions.

## Setup

```bash
poetry install
```

## Usage

### Validate configuration

```bash
workflow-sync validate
```

Checks `workflows.yaml` against the schema and verifies every referenced workflow template exists.

### Sync workflows

```bash
# Dry-run (no pushes)
workflow-sync sync --dry-run

# Sync all repos
workflow-sync sync

# Sync a single repo
workflow-sync sync --repo my-python-app
```

## Configuration — `workflows.yaml`

```yaml
settings:
  base_branch: main
  workflows_target_dir: .github/workflows

repos:
  - name: my-python-app
    url: git@github.com:your-org/my-python-app.git
    language: python
    workflows:
      - name: python-ci
      - name: release
```

## Workflow templates — `workflows/`

Each workflow lives in its own folder (`workflows/<name>/workflow.yml.j2`). The file must start with comment headers:

```yaml
# title: Python CI
# version: 1.2.0
# description: Standard CI for Python projects

on:
  push:
    branches: [main]
...
```

When `sync` detects that the deployed version in a repo is older than the template version, it creates a branch `chore/workflow-sync/<name>-v<version>`, renders the template with Jinja2, commits, and pushes.

### Template variables

| Variable  | Description |
|-----------|-------------|
| `repo`    | The `Repo` config object (`repo.name`, `repo.url`, `repo.language`, `repo.org`) |
| `workflow` | Workflow definition — `workflow.name`, `workflow.version`, `workflow.description` |
| `options` | Per-workflow options dict defined in `workflows.yaml` |

### Partial templates

Shared YAML fragments can live alongside a workflow's template in a `_partials/` subfolder and are included via Jinja2's `{% include %}`:

```yaml
steps:
{% include '_partials/_my-shared-steps.yml.j2' %}
  - name: My extra step
    ...
```

See [docs/jira-workflows.md](docs/jira-workflows.md) for documentation on the built-in JIRA review templates.

---

## Adding a new workflow

All workflow code — Jinja2 template, partials, and the Pydantic options schema — lives together in the same folder inside the package:

```
src/workflow_sync/workflows/
  my-workflow/
    schemas.py       ← Pydantic options schema (optional)
    workflow.yml.j2  ← Jinja2 template (required)
    _partials/       ← shared Jinja2 fragments (optional)
      _my-steps.yml.j2
```

### 1. Create the workflow folder

```bash
mkdir -p src/workflow_sync/workflows/my-workflow/_partials
```

### 2. Write the template

Extend the base template and put your workflow YAML inside `workflow_content`:

```yaml
{% extends '_common_partials/_workflow-base.yml.j2' %}

{% block workflow_content %}
on:
  pull_request:
    types: [opened, synchronize]

jobs:
  my-job:
    runs-on: {{ options.runs_on }}
    steps:
      - uses: actions/checkout@v4
      # your steps here...
{% endblock %}
```

The `{% extends '_common_partials/_workflow-base.yml.j2' %}` line is **required** on line 1 — `workflow-sync validate` will error if it is missing. The base template provides three blocks:

| Block | Default content |
|---|---|
| `sync_header` | `# id / # title / # version / # description` comment lines |
| `workflow_header` | `name: {{ workflow.name }}` |
| `workflow_content` | *(empty — put your `on:` / `jobs:` here)* |

Override `sync_header` or `workflow_header` only if a specific workflow needs non-standard header content.

Jinja2 variables available in every template by default:

| Variable  | Description |
|-----------|-------------|
| `repo`    | `Repo` config object — `repo.name`, `repo.url`, `repo.org`, `repo.language` |
| `workflow` | Workflow definition — `workflow.name`, `workflow.version`, `workflow.description` |
| `options` | Typed options from `workflows.yaml` (see step 3) |

The workflow header comment block and `name:` field are rendered automatically by the base template `src/workflow_sync/workflows/_common_partials/_workflow-base.yml.j2`. Use `{% extends %}` at the top of your template and place your content in `{% block workflow_content %}`:

```yaml
{% extends '_common_partials/_workflow-base.yml.j2' %}

{% block workflow_content %}
on:
  pull_request: ...
...
{% endblock %}
```

Use `${{ ... }}` for GitHub Actions expressions — they pass through Jinja2 unchanged.

### 3. Define an options schema (optional)

Create `src/workflow_sync/workflows/my-workflow/schemas.py` to add typed, validated options:

```python
from pydantic import Field
from workflow_sync.base_schemas import BaseWorkflowOptions

class MyWorkflowOptions(BaseWorkflowOptions):
    python_version: str = Field(default="3.12")
    cache: bool = Field(default=True)
```

Then register it in `src/workflow_sync/base_schemas.py` inside `_build_registry()`:

```python
return {
    "jira-review": _load("jira-review", "JiraReviewOptions"),
    "my-workflow": _load("my-workflow", "MyWorkflowOptions"),  # ← add this
}
```

Without a `schemas.py`, `options` falls back to `BaseWorkflowOptions` (only `runs_on` is typed).

### 4. Reference it in `workflows.yaml`

```yaml
repos:
  - url: git@github.com:your-org/my-repo.git
    language: python
    workflows:
      - name: my-workflow
        options:
          python_version: "3.11"
```

### 5. Validate and sync

```bash
workflow-sync validate          # check config + template existence
workflow-sync sync --dry-run    # preview what would be pushed
workflow-sync sync              # create branches and push
```

## Editing an existing workflow

Use this process when you need to modify a workflow template (e.g. updating steps, adding inputs, or changing job configuration).

### 1. Edit the workflow template

Make your changes in the workflow's Jinja2 template and any relevant partials:

```
src/workflow_sync/workflows/<name>/workflow.yml.j2
src/workflow_sync/workflows/<name>/_partials/
```

### 2. Bump the version in the workflow schema

Increment the `# version:` header in the template. This is what `workflow-sync` compares against the deployed version to decide whether to open a PR:

```yaml
{% extends '_common_partials/_workflow-base.yml.j2' %}
{# version is declared in the sync_header block of the base template #}
```

Update the version in `src/workflow_sync/workflows/<name>/schemas.py` if the options schema changed as well.

### 3. Open a PR and get a code review for the workflow changes

Commit your template edits on a feature branch, open a PR, and get it reviewed and merged before running the sync.

### 4. Before running, make sure you are on `main` and up to date

```bash
git checkout main
git pull
```

### 5. Dry-run the sync and verify

Preview what branches and commits would be created without pushing anything:

```bash
workflow-sync sync --dry-run
```

Review the output and confirm the correct repos and workflow versions are listed.

### 6. Run the sync

```bash
workflow-sync sync
```

This creates a branch `chore/workflow-sync/<name>-v<version>` in each affected repo, renders the template, commits, and pushes.

### 7. Open PRs for all new changes

For each repo that received a new branch, open a pull request targeting that repo's default branch so the updated workflow can be reviewed and merged.

---

## Editor setup

### VS Code

Install the **Better Jinja** extension for syntax highlighting in `.yml.j2` template files:

```bash
code --install-extension samuelcolvin.jinjahtml
```

Or search for `samuelcolvin.jinjahtml` in the Extensions panel. The workspace `.vscode/settings.json` already associates `*.yml.j2` files with the `jinja-yaml` language mode — no manual configuration needed after installing the extension.

### PyCharm

PyCharm Professional includes Jinja2 support out of the box. To enable it for `.yml.j2` files:

1. Open **Settings** → **Editor** → **File Types**
2. Select **Jinja2 template** from the list
3. Add `*.yml.j2` (and optionally `*.yaml.j2`) under **File name patterns**

PyCharm Community does not include Jinja2 support. The [IntelliJ Jinja2 Support](https://plugins.jetbrains.com/plugin/19896) plugin adds it — search for `Jinja2 Support` in **Settings** → **Plugins** → **Marketplace**.

## Running tests

```bash
poetry run pytest
poetry run pytest --cov
```
