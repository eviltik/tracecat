"""External directory API for service-to-service consumers.

Exposes a tree of folders + workflows + webhooks for a workspace, in a
single roundtrip, authenticated by `x-tracecat-service-key` (the same
inter-service key Tracecat uses internally — clients must also send
`x-tracecat-role-service-id: tracecat-cli` and
`x-tracecat-role-workspace-id: <uuid>`).

This is intended for internal backends that need to discover and trigger
Tracecat workflows programmatically without going through the user
session cookie path and without requiring an Enterprise service account.

Two endpoints:

* `GET  /workspaces/{ws}/directory`
    Returns the workspace's folder/workflow tree with webhook URL +
    api-key preview for each workflow. The URL contains a secret derived
    from `webhook.id` and is sufficient to trigger the workflow. The raw
    api-key is **not** returned (Tracecat only stores it hashed).

* `POST /workspaces/{ws}/directory/workflows/{wf_id}/webhook/regenerate-key`
    Regenerates a webhook API key. Returns the raw key once. The previous
    key (if any) is invalidated server-side.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from tracecat.auth.api_keys import generate_api_key
from tracecat.auth.dependencies import WorkspaceServiceRole
from tracecat.db.dependencies import AsyncDBSession
from tracecat.db.models import Webhook, WebhookApiKey, Workflow, WorkflowFolder
from tracecat.directory.schemas import (
    DirectoryFolderNode,
    DirectoryResponse,
    DirectoryWebhookKey,
    DirectoryWorkflowNode,
    RegeneratedWebhookKey,
)
from tracecat.identifiers.workflow import AnyWorkflowIDPath, WorkflowUUID
from tracecat.logger import logger

router = APIRouter(prefix="/directory", tags=["directory"])


def _make_api_key_preview(preview: str | None) -> DirectoryWebhookKey | None:
    if preview is None:
        return None
    return DirectoryWebhookKey(
        preview=preview,
        created_at=datetime.now(UTC),  # placeholder; overwritten by caller
    )


@router.get("", response_model=DirectoryResponse)
async def get_directory(
    role: WorkspaceServiceRole,
    session: AsyncDBSession,
) -> DirectoryResponse:
    """Return the workspace's folder/workflow tree with webhook info.

    Output is shaped for client-side tree renderers: `root` is a list of
    top-level nodes; each folder node carries its sub-tree in `children`.
    Workflows include the full webhook URL (with secret) and the API key
    preview if present.
    """
    if role.workspace_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Workspace ID is required",
        )

    workspace_id = role.workspace_id

    # 1. Fetch all folders for this workspace
    folder_stmt = select(WorkflowFolder).where(
        WorkflowFolder.workspace_id == workspace_id
    )
    folder_res = await session.execute(folder_stmt)
    folders = folder_res.scalars().all()

    # 2. Fetch all workflows for this workspace, with their webhook + api_key
    workflow_stmt = (
        select(Workflow)
        .where(Workflow.workspace_id == workspace_id)
        .options(
            selectinload(Workflow.webhook).selectinload(Webhook.api_key),
        )
    )
    workflow_res = await session.execute(workflow_stmt)
    workflows = workflow_res.scalars().all()

    # 3. Build folder nodes indexed by path
    folder_nodes_by_path: dict[str, DirectoryFolderNode] = {}
    for f in folders:
        folder_nodes_by_path[f.path] = DirectoryFolderNode(
            _id=f"folder:{f.id}",
            name=f.name,
            path=f.path,
            children=[],
        )

    # 4. Build workflow nodes and place each one under its folder (or root)
    workflow_nodes_by_folder_path: dict[str, list[DirectoryWorkflowNode]] = {}
    folder_path_by_id = {f.id: f.path for f in folders}

    for wf in workflows:
        wf_id_short = WorkflowUUID.new(wf.id).short()
        webhook_url: str | None = None
        webhook_status: str | None = None
        webhook_methods: list[str] = []
        webhook_key: DirectoryWebhookKey | None = None

        if wf.webhook is not None:
            try:
                webhook_url = wf.webhook.url
            except Exception:  # pragma: no cover — best-effort URL build
                logger.warning(
                    "Failed to compute webhook URL", workflow_id=wf_id_short
                )
            webhook_status = wf.webhook.status
            webhook_methods = list(wf.webhook.methods or [])
            if wf.webhook.api_key is not None:
                api_key = wf.webhook.api_key
                webhook_key = DirectoryWebhookKey(
                    preview=api_key.preview,
                    created_at=api_key.created_at,
                    last_used_at=api_key.last_used_at,
                    revoked_at=api_key.revoked_at,
                    is_active=api_key.revoked_at is None,
                )

        node = DirectoryWorkflowNode(
            _id=wf_id_short,
            wf_id=wf_id_short,
            alias=wf.alias,
            title=wf.title,
            description=wf.description,
            version=wf.version,
            status=wf.status,
            webhook_url=webhook_url,
            webhook_status=webhook_status,
            webhook_methods=webhook_methods,
            webhook_key=webhook_key,
        )

        path = folder_path_by_id.get(wf.folder_id, "/") if wf.folder_id else "/"
        workflow_nodes_by_folder_path.setdefault(path, []).append(node)

    # 5. Stitch the folder tree (parent-child by materialized path)
    root_folders: list[DirectoryFolderNode] = []
    for path, folder_node in folder_nodes_by_path.items():
        segments = [s for s in path.split("/") if s]
        if len(segments) <= 1:
            root_folders.append(folder_node)
        else:
            parent_path = "/" + "/".join(segments[:-1]) + "/"
            parent = folder_nodes_by_path.get(parent_path)
            if parent is None:
                # Orphan (parent missing): hoist to root rather than drop
                root_folders.append(folder_node)
            else:
                parent.children.append(folder_node)

    # 6. Attach workflow nodes to their folder.children (and collect root-level
    #    workflows separately)
    for folder_node in folder_nodes_by_path.values():
        for wf_node in workflow_nodes_by_folder_path.get(folder_node.path, []):
            folder_node.children.append(wf_node)

    root_workflows = workflow_nodes_by_folder_path.get("/", [])

    # 7. Sort: folders alphabetically first, then workflows alphabetically by
    #    alias (fallback to title)
    def _sort_key(node):
        if isinstance(node, DirectoryFolderNode):
            return (0, node.name.lower())
        return (1, (node.alias or node.title or "").lower())

    def _sort_recursive(folder: DirectoryFolderNode) -> None:
        folder.children.sort(key=_sort_key)
        for child in folder.children:
            if isinstance(child, DirectoryFolderNode):
                _sort_recursive(child)

    root_nodes: list = [*root_folders, *root_workflows]
    root_nodes.sort(key=_sort_key)
    for child in root_nodes:
        if isinstance(child, DirectoryFolderNode):
            _sort_recursive(child)

    return DirectoryResponse(synced_at=datetime.now(UTC), root=root_nodes)


@router.post(
    "/workflows/{workflow_id}/webhook/regenerate-key",
    response_model=RegeneratedWebhookKey,
    status_code=status.HTTP_201_CREATED,
)
async def regenerate_webhook_api_key(
    role: WorkspaceServiceRole,
    session: AsyncDBSession,
    workflow_id: AnyWorkflowIDPath,
) -> RegeneratedWebhookKey:
    """Regenerate the webhook API key for a workflow and return the raw key.

    The raw key is only returned here, once. After this call it is stored
    hashed in the database. Any previous key for this webhook is
    invalidated server-side.
    """
    if role.workspace_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Workspace ID is required",
        )

    # Fetch the workflow + webhook scoped to the workspace
    stmt = (
        select(Workflow)
        .where(
            Workflow.workspace_id == role.workspace_id,
            Workflow.id == workflow_id,
        )
        .options(selectinload(Workflow.webhook).selectinload(Webhook.api_key))
    )
    res = await session.execute(stmt)
    workflow = res.scalars().first()
    if workflow is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow not found",
        )
    webhook = workflow.webhook
    if webhook is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Webhook not found for this workflow",
        )

    now = datetime.now(UTC)
    generated = generate_api_key()
    preview = generated.preview()

    api_key = webhook.api_key
    if api_key is None:
        api_key = WebhookApiKey(
            workspace_id=role.workspace_id,
            webhook_id=webhook.id,
            hashed=generated.hashed,
            salt=generated.salt_b64,
            preview=preview,
            created_at=now,
            updated_at=now,
        )
    else:
        api_key.workspace_id = role.workspace_id
        api_key.hashed = generated.hashed
        api_key.salt = generated.salt_b64
        api_key.preview = preview
        api_key.last_used_at = None
        api_key.revoked_at = None
        api_key.revoked_by = None
        api_key.created_at = now
        api_key.updated_at = now
    session.add(api_key)
    await session.commit()

    return RegeneratedWebhookKey(
        wf_id=WorkflowUUID.new(workflow.id).short(),
        api_key=generated.raw,
        preview=preview,
        created_at=now,
    )
