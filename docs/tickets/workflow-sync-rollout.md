# workflow-sync Rollout

## Title

Roll out `workflow-sync` CLI to distribute standardised GitHub Actions workflows across repos

## Description

`workflow-sync` is an internal CLI tool that manages and standardises GitHub Actions workflows across multiple repositories from a single source of truth. A central `workflows.yaml` defines which repos get which workflow templates; running `workflow-sync sync` automatically creates branches with the rendered workflow files in each target repo.

This ticket covers setting up `workflow-sync` in CI, onboarding the initial set of repos, and establishing the process for ongoing workflow updates.

---

## Background

Workflow files are currently copied and maintained manually in each repo, leading to drift and inconsistency. `workflow-sync` solves this by treating workflow templates as versioned artifacts: when a template version bumps, the tool detects the delta and opens a branch in every affected repo for review and merge.

---

## Acceptance Criteria

- [ ] `workflow-sync` is installable in the team's environment (`poetry install` or published package).
- [ ] `workflows.yaml` is populated with the initial set of target repos and the `jira-copilot` workflow template.
- [ ] `workflow-sync validate` passes with no errors for all configured repos and templates.
- [ ] `workflow-sync sync --dry-run` correctly reports which repos are out of date without pushing any changes.
- [ ] `workflow-sync sync` creates branches (`chore/workflow-sync/<name>-v<version>`) and pushes rendered workflow files to each target repo.
- [ ] The tool is documented: README covers setup, `workflows.yaml` format, and the `validate` / `sync` commands.
- [ ] A repeatable process (e.g. scheduled CI job or runbook) is defined for triggering syncs when a template version is bumped.

---

## References

- Repository: `workflow-sync`
- Main docs: [`README.md`](../../README.md)
- Template docs: [`docs/jira-workflows.md`](../jira-workflows.md)
