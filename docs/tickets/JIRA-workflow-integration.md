# JIRA Workflow Integration

## Title

Add JIRA-driven Copilot code review workflow to GitHub Actions

## Description

As part of standardising our engineering process, we need to enforce that every pull request is linked to a valid JIRA ticket and automatically receives a GitHub Copilot code review that verifies the implementation against the ticket's acceptance criteria.

This ticket covers the design and implementation of a single reusable GitHub Actions workflow (`jira-copilot`) that automates this process.

---

## Background

Today, PR reviews are inconsistent: some repos require a JIRA link, others don't; and Copilot review is not systematically triggered. This work introduces a single GitHub Actions workflow that enforces the JIRA link, enriches the PR with ticket context, and requests a GitHub Copilot review — ensuring every PR is reviewed against its requirements.

---

## Acceptance Criteria

- [ ] Workflow triggers on `pull_request` events (`opened`, `synchronize`, `reopened`).
- [ ] **Step 1 — Ticket extraction:** the branch name is parsed for a JIRA key matching `[A-Z]{2,10}-[0-9]+`. If none is found, the JIRA steps are skipped gracefully (no hard failure).
- [ ] **NOJIRA skip:** branches prefixed with `NOJIRA` (case-insensitive) bypass all JIRA steps without failing the workflow.
- [ ] **Step 2 — JIRA API fetch:** ticket summary, status, and description are retrieved via the JIRA REST API using `JIRA_BASE_URL`, `JIRA_USER`, and `JIRA_TOKEN` repo secrets.
- [ ] **Step 3 — PR enrichment:** a `## 🎫 JIRA` section is appended to the PR description (idempotent — inserted only once, guarded by an HTML comment marker). The section includes summary, status, requirements, and a Copilot review instruction block.
- [ ] **Step 4 — Copilot review:** `copilot-pull-request-reviewer` is requested as a PR reviewer via the GitHub REST API. Copilot picks up the enriched PR description (including JIRA requirements) as review context.
- [ ] Workflow file is committed to `.github/workflows/` in each target repo.

---

## Required Secrets

| Secret | Description |
|--------|-------------|
| `JIRA_BASE_URL` | Base URL of your JIRA instance (e.g. `https://your-org.atlassian.net`) |
| `JIRA_USER` | JIRA user email for API authentication |
| `JIRA_TOKEN` | JIRA API token |
| `GITHUB_TOKEN` | Provided automatically by GitHub Actions |

---

## Out of Scope

- Rollout tooling for distributing this workflow across multiple repos (separate ticket).
- JIRA project configuration or ticket field customisation.
- Other AI review strategies (Anthropic API, agentic review) — separate tickets.

---

## References

- Workflow file: `.github/workflows/jira-copilot.yml`
- Template docs: [`docs/jira-workflows.md`](../jira-workflows.md)
