# Fork index — `deploy/mytracecat`

This file lives on the [eviltik/tracecat](https://github.com/eviltik/tracecat)
fork and is **not** present on `TracecatHQ/tracecat:main`. It indexes the
fork's feature branches.

For the rebase / rebuild / redeploy procedure when pulling a new
upstream release, see [`FORK_SYNC.md`](FORK_SYNC.md).

## Feature branches

| Branch | What it does | Fork issue | Upstream PR status |
|---|---|---|---|
| [`feat/basepath`](https://github.com/eviltik/tracecat/tree/feat/basepath) | Serve Tracecat under a sub-path (e.g. `/tracecat/`). | [#1](https://github.com/eviltik/tracecat/issues/1) | Proposed ([#2651](https://github.com/TracecatHQ/tracecat/pull/2651)), closed — fork recommended |
| [`feat/ai-action-system-prompt-overrides`](https://github.com/eviltik/tracecat/tree/feat/ai-action-system-prompt-overrides) | Per-source system prompt cascade (replace / append). | [#2](https://github.com/eviltik/tracecat/issues/2) | Proposed ([#2657](https://github.com/TracecatHQ/tracecat/pull/2657)), closed — env var suggested, insufficient |
| [`feat/ai-action-allowed-tools-control`](https://github.com/eviltik/tracecat/tree/feat/ai-action-allowed-tools-control) | Per-source Claude SDK tools allowlist. | [#3](https://github.com/eviltik/tracecat/issues/3) | Not proposed yet — could be |
| [`feat/workflow-upsert`](https://github.com/eviltik/tracecat/tree/feat/workflow-upsert) | `POST /workflows/{wf_id}/upsert` — idempotent YAML deploy, preserves webhook URL & API key. | [#4](https://github.com/eviltik/tracecat/issues/4) | Not proposed yet — good candidate |
| [`feat/external-directory`](https://github.com/eviltik/tracecat/tree/feat/external-directory) | `GET /workspaces/{ws}/directory` — service-key authenticated directory API for internal backends. | [#5](https://github.com/eviltik/tracecat/issues/5) | Not proposed — tension with Tracecat Service Accounts (paid feature) |
| `deploy/mytracecat` | **Default branch.** Merges all the above on top of `origin/main`. Docker images build from this. | — | — |

Open the corresponding issue for the goal, design, why-OSS-relevant
reasoning, smoke checklist, and conflict-prone files of each branch.
