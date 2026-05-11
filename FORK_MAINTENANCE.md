# Fork maintenance — `deploy/mytracecat`

This file is **specific to the [eviltik/tracecat](https://github.com/eviltik/tracecat)
fork** and is not present on `TracecatHQ/tracecat:main`. It documents the
local feature branches, how to keep them rebased on upstream, and the
day-to-day rebuild / redeploy procedure.

If you are reading this on the upstream repo, you can safely ignore it.

## Why this fork exists

Two features were proposed upstream and declined by maintainers (see
[issue #2652](https://github.com/TracecatHQ/tracecat/issues/2652) and
[PR #2657](https://github.com/TracecatHQ/tracecat/pull/2657)). The
maintainers' explicit recommendation was to fork rather than insist
upstream:

> *"keeping a fork + pull in new changes will be our recommendation"*
>   — Topher Lo, 2026-05-08

The features are reasonably stable and live as small, focused branches.
Rebasing onto upstream `main` is straightforward in 95% of cases.

## Branches

| Branch | Purpose | Upstream issue |
|---|---|---|
| `feat/basepath` | Serve Tracecat under a sub-path (`https://example.com/tracecat`). | [#2652](https://github.com/TracecatHQ/tracecat/issues/2652) |
| `feat/ai-action-system-prompt-overrides` | Per-source `system_prompt_replace` / `system_prompt_append` on custom providers, with cascade resolution. | [#2654](https://github.com/TracecatHQ/tracecat/issues/2654) |
| `feat/workflow-upsert` | `POST /workflows/{wf_id}/upsert` — idempotent YAML deploy at a stable workflow_id (preserves webhook URL secret and API key across redeploys). | — |
| `feat/external-directory` | `GET /workspaces/{ws}/directory` + `POST .../regenerate-key` — service-key-authenticated directory API for internal backends (folders + workflows + webhooks in one tree response). Avoids needing Enterprise service accounts to drive Tracecat from a sister backend. | — |
| `deploy/mytracecat` | Integration branch — merges all the above on top of `origin/main`. This is what we build Docker images from. | — |

Each feature branch is rebased independently on `origin/main` so it can
be re-proposed upstream if the maintainers ever change their stance.

## Remote layout

```
origin    → TracecatHQ/tracecat (upstream — fetch-only in practice)
eviltik   → eviltik/tracecat   (our fork — push target)
```

If your clone is missing the `eviltik` remote, add it:

```bash
git remote add eviltik git@github.com:eviltik/tracecat.git
git fetch eviltik
```

## Routine: pull a new upstream release

When TracecatHQ ships a new release (for example `1.0.0-beta.48`):

```bash
cd /path/to/tracecat
git fetch origin
```

### 1. Rebase each feature branch on the new upstream main

```bash
git checkout feat/basepath
git rebase origin/main
# resolve conflicts if any (rare — touched files are peripheral)
git push --force-with-lease eviltik feat/basepath

git checkout feat/ai-action-system-prompt-overrides
git rebase origin/main
git push --force-with-lease eviltik feat/ai-action-system-prompt-overrides
```

`--force-with-lease` is required because the rebase rewrites the branch
history. It's safer than `--force` because it refuses the push if
someone else pushed to the branch in the meantime.

### 2. Rebuild the integration branch from scratch

```bash
git checkout deploy/mytracecat
# Reset deploy onto the new upstream main and re-merge each feature
git reset --hard origin/main
git merge --no-ff feat/basepath -m "Merge feat/basepath into deploy/mytracecat"
git merge --no-ff feat/ai-action-system-prompt-overrides \
    -m "Merge feat/ai-action-system-prompt-overrides into deploy/mytracecat"
git push --force-with-lease eviltik deploy/mytracecat
```

### 3. Rebuild Docker images

```bash
# Backend (used by every Tracecat service except the UI)
docker build -f Dockerfile -t <your-org>-tracecat-api:<tag> .

# UI — build args are baked in at build time (Next.js basePath)
# Adjust URLs for your environment.
docker build \
  --build-arg NEXT_PUBLIC_BASE_PATH=/tracecat \
  --build-arg NEXT_PUBLIC_APP_URL=https://example.com/tracecat \
  --build-arg NEXT_PUBLIC_API_URL=https://example.com/tracecat/api \
  --build-arg NEXT_SERVER_API_URL=http://api:8000 \
  -f frontend/Dockerfile.prod \
  -t <your-org>-tracecat-ui:<tag> \
  frontend/
```

The backend image is environment-agnostic (same image everywhere; URLs
come from your runtime env). The UI image, in contrast, bakes the
`NEXT_PUBLIC_*` URLs at build time, so you typically have one UI image
per target environment.

### 4. Redeploy

Redeploy each of the seven Tracecat services using your usual workflow
(`docker compose up`, Helm, Fargate, etc.). The migration runner inside
the API container applies any new Alembic revisions on startup,
including ours (`c969b5f63428`).

### 5. Smoke test

Before declaring the rebase done:

- [ ] Login via Keycloak.
- [ ] UI loads under the sub-path (`/tracecat/`).
- [ ] `Settings → Agent → Custom sources → Edit` shows the two extra
      textareas (`System prompt replace`, `System prompt append`).
- [ ] A workflow with `ai.action` against a custom source whose
      `system_prompt_replace` is set returns the overridden identity.
- [ ] OAuth / SAML still redirect correctly (verify devtools cookie
      `Path=/tracecat`).

## Conflict-prone files

The features touch these files. If upstream changes the same lines, the
rebase will need attention:

| File | Branch | Likelihood of conflict |
|---|---|---|
| `tracecat/agent/runtime/claude_code/runtime.py` | `feat/ai-action-system-prompt-overrides` | Medium — actively developed upstream |
| `tracecat/dsl/workflow.py` (the `AI_ACTION` case) | `feat/ai-action-system-prompt-overrides` | Medium |
| `frontend/next.config.mjs` | `feat/basepath` | Low |
| `frontend/Dockerfile.prod` | `feat/basepath` | Low |
| `tracecat/auth/users.py` (cookie path) | `feat/basepath` | Low |
| `frontend/src/components/organization/org-settings-agent.tsx` | `feat/ai-action-system-prompt-overrides` | Medium — UI evolves often |
| Alembic migrations | `feat/ai-action-system-prompt-overrides` | Low — distinct revision IDs unless upstream also touches `agent_custom_provider` |
| `tracecat/workflow/management/router.py` (route block before `restore_workflow_definition`) | `feat/workflow-upsert` | Low — additive route, no overlap with existing imports |
| `tracecat/auth/dependencies.py` (new `WorkspaceServiceRole`) | `feat/external-directory` | Low — additive symbol below `ServiceRole` |
| `tracecat/api/app.py` (`_include_workspace_scoped_router` block) | `feat/external-directory` | Low — additive `directory_router` registration |
| `tracecat/directory/*` | `feat/external-directory` | None — new module, no upstream collision |

If a conflict you don't recognise pops up:

1. Check the upstream PR that introduced the change
   (`git log --oneline <file>`).
2. Adapt our patch to keep the same intent — the cascade and the
   basePath helpers are designed to be additive and survive most
   refactors.
3. Re-run the smoke checklist.

## When upstream merges what we have

Unlikely, but if it ever happens (multiple users vote for the same need
on the issues):

1. Drop the corresponding feature branch from `deploy/mytracecat`.
2. Rebase the integration branch on the new `origin/main` that already
   contains the feature.
3. Move the relevant tests/docs from our branch into a follow-up PR if
   maintainers want to consolidate.

## API surface added by the fork

These endpoints are not present upstream. They are consumed by sister
internal backends to discover and drive Tracecat workflows without
relying on a user session cookie or an Enterprise service account.

### `POST /api/workspaces/{ws}/workflows/{wf_id}/upsert`

Branch: `feat/workflow-upsert`.

Idempotent YAML deploy at a stable `workflow_id`. If the workflow
exists, replaces its DSL while preserving:
- the workflow row id,
- the webhook row id (so the URL secret stays valid),
- the attached `WebhookApiKey` row (so the previously-issued key keeps
  working).

If absent, creates a new workflow using the URL-provided ID.

Auth: `WorkspaceActorRouteRole` (user session or Tracecat API key,
same as the rest of the workflow management API).

Body: multipart `file=` containing a YAML or JSON document that
deserialises to `RemoteWorkflowDefinition` (top-level `id`, `alias`,
`definition`, optional `webhook`, `schedules`, `tags`, `folder_path`).
The `id` in the body must match the URL `wf_id`.

Implementation: reuses `WorkflowImportService.import_workflows_atomic`,
the same code path as the Git sync feature — so the upsert benefits
from the existing validation, atomicity and tests.

Tests live in `tests/unit/test_workflow_upsert.py` and cover the
webhook-preservation guarantee that this endpoint is built around.

### `GET /api/workspaces/{ws}/directory`

Branch: `feat/external-directory`.

Returns a workspace's folder/workflow tree in a single roundtrip,
shaped for client-side tree renderers:

```json
{
  "synced_at": "…",
  "root": [
    { "_id": "folder:…", "type": "folder", "name": "O365", "path": "/O365/",
      "children": [
        { "_id": "wf_…", "type": "workflow", "alias": "…", "version": 4,
          "webhook_url": "https://…/wf_…/secret",
          "webhook_key": { "preview": "tc_sk_…XeQ8", "created_at": "…" }
        }
      ]
    }
  ]
}
```

Auth: new `WorkspaceServiceRole` dependency. The client must send
`x-tracecat-service-key: <TRACECAT__SERVICE_KEY>` and
`x-tracecat-role-service-id: tracecat-cli`. The workspace comes from
the URL path.

The raw webhook API key is **not** returned (Tracecat only stores it
hashed). Use the regenerate endpoint below to mint a fresh one.

### `POST /api/workspaces/{ws}/directory/workflows/{wf_id}/webhook/regenerate-key`

Branch: `feat/external-directory`.

Regenerates the webhook API key for a workflow. The raw key is
returned once. The previous key (if any) is invalidated server-side.

Same auth as the directory endpoint.

## Reference: original PRs (for context)

- **Sub-path support**: PR [#2651](https://github.com/TracecatHQ/tracecat/pull/2651)
  — closed by upstream maintainer with the recommendation to fork.
- **System prompt overrides**: PR [#2657](https://github.com/TracecatHQ/tracecat/pull/2657)
  — closed by upstream maintainer with the suggestion to use a global
  env var instead. We chose to keep the per-source / cascade version
  on the fork because the env var doesn't cover multi-source nor
  webhook-driven prompts.

Both PRs have full descriptions, test matrices, and end-to-end
verification logs in their bodies — useful if you ever need to
re-justify the approach to a new reviewer.
