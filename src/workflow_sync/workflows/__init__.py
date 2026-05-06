"""Built-in workflow templates and their option schemas.

Each workflow lives entirely in its own subfolder::

    workflows/<workflow-name>/
        schemas.py       — Pydantic options schema (JiraReviewOptions etc.)
        workflow.yml.j2  — Jinja2 template rendered into each target repo
        _partials/       — shared Jinja2 fragments included by the template

The folder name (e.g. ``jira-review``) is the value used in ``workflows.yaml``
under ``repos[].workflows[].name``.  Because hyphens are not valid Python
identifiers, options classes are loaded dynamically via ``importlib`` in
``workflow_sync.base_schemas._build_registry``.
"""
