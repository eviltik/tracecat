# Fork sync — pulling new upstream releases

Procedure used by this fork's maintainers to rebase the feature branches
onto a new upstream release and rebuild `deploy/mytracecat`.

If you only want to read what the fork adds, see
[`FORK_MAINTENANCE.md`](FORK_MAINTENANCE.md) — it indexes the feature
branches and their fork issues. This file is purely operational.

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
