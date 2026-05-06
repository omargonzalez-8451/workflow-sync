# JIRA Workflow Templates

JIRA driven AI code review workflow, can be used on all or any repo.

---

## Shared steps (1–3)

All three templates share the same first three steps. On every PR created or updated.

| # | Step | What it does |
|---|------|--------------|
| 1 | **Extract JIRA ticket** | Reads the branch name (`github.head_ref`) and extracts the first JIRA key matching `[A-Z]{2,10}-[0-9]+` (e.g. `PROJ-123`). If no key is found the remaining steps are skipped and the PR is flagged. |

| 2 | **Fetch ticket from JIRA** | Calls the JIRA REST API (`GET /rest/api/3/issue/{key}`) with `JIRA_BASE_URL`, `JIRA_USER`, and `JIRA_TOKEN` secrets. Stores the ticket summary, status, and description for the next step. |

| 3 | **Enrich PR description** | Appends a `## 🎫 JIRA` section to the PR body containing the ticket summary, status, and acceptance criteria. Also adds an instruction block that tells the AI reviewer to verify the code satisfies those requirements. The section is idempotent — it is inserted only once, guarded by an HTML comment marker. |

> **Skipping JIRA:** prefix your branch with `NOJIRA` (case-insensitive, e.g. `NOJIRA-hotfix-typo`)
> to bypass all JIRA steps without failing the workflow.

---

## Step 4 — where the three templates differ

### `jira-copilot` — Agente native gitub AI review, aka GPT

### `jira-anthropic` — Anthropic non agentic review, aka Claude
- Is unable to explore the whole code base, only has PR description and diff available.

### `jira-anthropic-agent` — Anthropic agentic review, aka Claude with tools
- anthropic github action still in beta.
