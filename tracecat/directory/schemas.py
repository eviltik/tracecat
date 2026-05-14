"""Schemas for the external directory API.

These schemas are designed to be friendly for client-side tree renderers:
the response carries a pre-built tree of folders and workflows (`root`)
rather than a flat list — so callers don't need to reconstruct the
hierarchy themselves.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class DirectoryWebhookKey(BaseModel):
    """Lightweight webhook API key info (preview only — raw key is never
    retrievable after creation; use the regenerate endpoint to rotate)."""

    preview: str
    created_at: datetime
    last_used_at: datetime | None = None
    revoked_at: datetime | None = None
    is_active: bool = True


class DirectoryTag(BaseModel):
    """A workflow tag exposed in the directory tree."""

    ref: str = Field(..., description="Slug-like identifier, stable across renames")
    name: str = Field(..., description="Human-readable label")
    color: str | None = None


class DirectoryWorkflowNode(BaseModel):
    """A workflow entry in the directory tree.

    The `id` field is the unique node identifier (= short wf_id). This name
    matches the default `getItemId` of virtual-tree-style renderers
    (`item.id || item.nodeId`).
    """

    # Tree node fields
    id: str = Field(
        ...,
        description="Unique identifier for the tree node (= short wf_id)",
    )
    type: Literal["workflow"] = "workflow"
    children: list = Field(
        default_factory=list,
        description="Always empty for workflows; present for vtree compatibility",
    )

    # Workflow fields
    wf_id: str
    alias: str | None = None
    title: str
    description: str | None = None
    version: int | None = None
    status: str
    tags: list[DirectoryTag] = Field(
        default_factory=list,
        description="Workflow tags (organization/filtering metadata)",
    )
    meta: dict = Field(
        default_factory=dict,
        description=(
            "Declarative metadata bag — the `args.value` of the workflow's "
            "`meta` action (if any). Opaque pass-through: whatever a workflow "
            "puts in its `meta` action (label, version, custom fields...) is "
            "surfaced here, so consumers can read workflow metadata without "
            "fetching the full definition. Empty dict if no `meta` action."
        ),
    )

    # Webhook fields (URL contains a secret derived from webhook.id — treat
    # as sensitive)
    webhook_url: str | None = None
    webhook_status: str | None = None
    webhook_methods: list[str] = Field(default_factory=list)
    webhook_key: DirectoryWebhookKey | None = None


class DirectoryFolderNode(BaseModel):
    """A folder entry in the directory tree.

    The `id` field is the unique node identifier (prefixed `folder:` to
    avoid colliding with workflow short ids).
    """

    id: str = Field(
        ...,
        description=(
            "Unique identifier for the tree node "
            "(prefixed `folder:` to avoid collision with wf_id)"
        ),
    )
    type: Literal["folder"] = "folder"
    name: str
    path: str
    children: list["DirectoryNode"] = Field(default_factory=list)


DirectoryNode = DirectoryFolderNode | DirectoryWorkflowNode

DirectoryFolderNode.model_rebuild()


class DirectoryResponse(BaseModel):
    """Top-level response of `GET /workspaces/{ws}/directory`."""

    synced_at: datetime
    root: list[DirectoryNode] = Field(
        default_factory=list,
        description=(
            "Top-level nodes (folders at root and workflows directly under root). "
            "Each folder node embeds its sub-tree in `children`."
        ),
    )


class RegeneratedWebhookKey(BaseModel):
    """Response of `POST /workspaces/{ws}/directory/workflows/{wf}/webhook/regenerate-key`.

    The raw key is only returned here, once. After this call returns it is
    only stored hashed in the database; the previous key (if any) is
    invalidated.
    """

    wf_id: str
    api_key: str
    preview: str
    created_at: datetime
