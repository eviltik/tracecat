# Fork maintenance — `deploy/mytracecat`

This file lives on the [eviltik/tracecat](https://github.com/eviltik/tracecat)
fork and is **not** present on `TracecatHQ/tracecat:main`. It indexes the
fork's feature branches and documents the upstream-sync procedure.

If you're reading this on the upstream repo, ignore it.

## Why this fork

Two features were proposed upstream and declined, with an explicit
recommendation from maintainers to fork rather than insist:

> *"keeping a fork + pull in new changes will be our recommendation"*
>   — Topher Lo, 2026-05-08

A few other patches were added on the same principle: small, focused
branches, each rebased independently on `origin/main`. Each is tracked
as a GitHub issue on this fork for context and history.

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

## Remote layout

```
origin    → TracecatHQ/tracecat (upstream — fetch-only)
eviltik   → eviltik/tracecat   (this fork)
```

If your clone is missing the `eviltik` remote:

```bash
git remote add eviltik git@github.com:eviltik/tracecat.git
git fetch eviltik
```

## Pulling a new upstream release

When TracecatHQ ships a new release (e.g. `1.0.0-beta.48`):

```bash
git fetch origin
```

### 1. Rebase each feature branch on the new upstream main

```bash
for branch in feat/basepath \
              feat/ai-action-system-prompt-overrides \
              feat/ai-action-allowed-tools-control \
              feat/workflow-upsert \
              feat/external-directory ; do
  git checkout "$branch"
  git rebase origin/main
  git push --force-with-lease eviltik "$branch"
done
```

`--force-with-lease` is used because rebasing rewrites history; it
refuses the push if someone else pushed to the branch in the meantime
(safer than `--force`).

If a rebase hits a conflict you don't recognise, the corresponding fork
issue lists the conflict-prone files for that branch.

### 2. Rebuild the integration branch from scratch

```bash
git checkout deploy/mytracecat
git reset --hard origin/main
for branch in feat/basepath \
              feat/ai-action-system-prompt-overrides \
              feat/ai-action-allowed-tools-control \
              feat/workflow-upsert \
              feat/external-directory ; do
  git merge --no-ff "$branch" -m "Merge $branch into deploy/mytracecat"
done
git push --force-with-lease eviltik deploy/mytracecat
```

### 3. Rebuild Docker images

```bash
# Backend (same image for every Tracecat service except the UI)
docker build -f Dockerfile -t <your-org>-tracecat-api:<tag> .

# UI — NEXT_PUBLIC_* args are baked at build time
docker build \
  --build-arg NEXT_PUBLIC_BASE_PATH=/tracecat \
  --build-arg NEXT_PUBLIC_APP_URL=https://example.com/tracecat \
  --build-arg NEXT_PUBLIC_API_URL=https://example.com/tracecat/api \
  --build-arg NEXT_SERVER_API_URL=http://api:8000 \
  -f frontend/Dockerfile.prod \
  -t <your-org>-tracecat-ui:<tag> \
  frontend/
```

The backend image is environment-agnostic; the UI image bakes its URLs
at build time, so build one per target environment.

### 4. Redeploy

Redeploy the seven Tracecat services with your usual workflow
(`docker compose up`, Helm, ECS, etc.). The migration runner inside the
API container applies any new Alembic revisions on startup, including
`c969b5f63428` from `feat/ai-action-system-prompt-overrides`.

### 5. Smoke test

Per-branch checklists are in the fork issues. The cross-cutting checks
that matter for every release:

- [ ] Login via your IdP
- [ ] UI loads under the configured sub-path (`feat/basepath`)
- [ ] At least one workflow runs end-to-end (worker + executor reachable)

## When upstream merges what we have

If a maintainer one day picks up one of these features upstream:

1. Drop the corresponding feature branch from the merge loop above.
2. Rebase `deploy/mytracecat` onto the new `origin/main` (which now
   contains the feature).
3. Close the fork issue with a link to the upstream PR for posterity.
