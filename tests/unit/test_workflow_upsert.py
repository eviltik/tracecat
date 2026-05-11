"""Tests for the workflow upsert behavior used by the new
`POST /workflows/{workflow_id}/upsert` endpoint.

These tests focus on the guarantees the endpoint relies on:

* Re-importing a workflow at the same `workflow_id` does NOT change the
  webhook row identity. This is what keeps the webhook URL secret stable
  across redeploys (the URL secret is derived from `webhook.id`).
* The webhook API key (if any) survives the upsert.
* DSL content (actions, expects, returns, config) is fully replaced.
* Version counter is incremented on each upsert.
* Omitting the top-level `webhook` field in the remote definition leaves
  the existing webhook configuration untouched (status, methods, api key).
"""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tracecat.auth.types import Role
from tracecat.db.models import Webhook, WebhookApiKey, Workflow, WorkflowDefinition
from tracecat.dsl.common import DSLEntrypoint, DSLInput
from tracecat.dsl.schemas import ActionStatement, DSLConfig
from tracecat.identifiers.workflow import WorkflowUUID
from tracecat.workflow.store.import_service import WorkflowImportService
from tracecat.workflow.store.schemas import (
    RemoteWebhook,
    RemoteWorkflowDefinition,
)

pytestmark = [
    pytest.mark.usefixtures("db"),
    pytest.mark.usefixtures("registry_version_with_manifest"),
]


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #


@pytest.fixture
async def import_service(
    session: AsyncSession, svc_role: Role
) -> WorkflowImportService:
    return WorkflowImportService(session=session, role=svc_role)


def _dsl(title: str, action_value: str) -> DSLInput:
    """Build a minimal DSL with a single reshape action."""
    return DSLInput(
        title=title,
        description=f"Description for {title}",
        entrypoint=DSLEntrypoint(ref="reshape"),
        actions=[
            ActionStatement(
                ref="reshape",
                action="core.transform.transform",
                args={"value": action_value, "format": "json"},
                description="Reshape",
            ),
        ],
        config=DSLConfig(timeout=300),
    )


def _remote(
    *,
    wf_id_short: str = "wf_upserttest00000000001",
    alias: str = "upsert-test",
    title: str = "Upsert Test v1",
    action_value: str = "v1",
    webhook: RemoteWebhook | None = RemoteWebhook(methods=["POST"], status="online"),
) -> RemoteWorkflowDefinition:
    return RemoteWorkflowDefinition(
        id=wf_id_short,
        alias=alias,
        webhook=webhook,
        definition=_dsl(title, action_value),
    )


async def _get_workflow_with_webhook(
    session: AsyncSession, wf_id: WorkflowUUID
) -> Workflow:
    stmt = select(Workflow).where(Workflow.id == wf_id)
    res = await session.execute(stmt)
    wf = res.scalars().first()
    assert wf is not None
    return wf


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #


class TestWorkflowUpsertBehavior:
    """Behavior the `/upsert` endpoint inherits via `import_workflows_atomic`."""

    @pytest.mark.anyio
    async def test_first_upsert_creates_workflow(
        self,
        import_service: WorkflowImportService,
        session: AsyncSession,
    ):
        """First upsert of an unknown wf_id creates the workflow."""
        remote = _remote()
        result = await import_service.import_workflows_atomic(
            remote_workflows=[remote], commit_sha="upsert-first"
        )
        assert result.success is True

        wf_id = WorkflowUUID.new(remote.id)
        wf = await _get_workflow_with_webhook(session, wf_id)
        assert wf.title == "Upsert Test v1"
        assert wf.alias == "upsert-test"
        assert wf.webhook is not None
        assert wf.version == 1

    @pytest.mark.anyio
    async def test_upsert_preserves_webhook_id_and_api_key(
        self,
        import_service: WorkflowImportService,
        session: AsyncSession,
    ):
        """The critical guarantee: re-importing at the same wf_id keeps the
        webhook row identity, which keeps the URL secret stable. Any attached
        webhook API key also survives."""
        # 1. First import
        first = _remote(
            title="Upsert Test v1",
            action_value="v1",
            webhook=RemoteWebhook(methods=["POST"], status="online"),
        )
        await import_service.import_workflows_atomic(
            remote_workflows=[first], commit_sha="upsert-1"
        )

        wf_id = WorkflowUUID.new(first.id)
        wf = await _get_workflow_with_webhook(session, wf_id)
        webhook_id_before = wf.webhook.id
        webhook_secret_before = wf.webhook.secret  # derived from webhook.id

        # Attach an API key to the webhook to verify it survives the upsert.
        from datetime import UTC, datetime

        api_key = WebhookApiKey(
            workspace_id=wf.workspace_id,
            webhook_id=webhook_id_before,
            hashed="dummy-hashed",
            salt="ZHVtbXktc2FsdA==",  # base64('dummy-salt')
            preview="tc_sk_dummy_preview",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        session.add(api_key)
        await session.commit()

        # 2. Re-import with a new DSL at the same wf_id
        second = _remote(
            title="Upsert Test v2",
            action_value="v2_changed",
            webhook=None,  # omit webhook in the remote → preserve existing
        )
        await import_service.import_workflows_atomic(
            remote_workflows=[second], commit_sha="upsert-2"
        )

        # 3. Verify the workflow content was updated...
        wf = await _get_workflow_with_webhook(session, wf_id)
        assert wf.title == "Upsert Test v2"
        assert wf.version == 2

        # ...but the webhook row identity is unchanged (URL secret stable)
        assert wf.webhook is not None
        assert wf.webhook.id == webhook_id_before
        assert wf.webhook.secret == webhook_secret_before

        # ...and the API key is still attached and unchanged
        stmt = select(WebhookApiKey).where(
            WebhookApiKey.webhook_id == webhook_id_before
        )
        res = await session.execute(stmt)
        keys = res.scalars().all()
        assert len(keys) == 1
        assert keys[0].preview == "tc_sk_dummy_preview"

    @pytest.mark.anyio
    async def test_upsert_replaces_actions(
        self,
        import_service: WorkflowImportService,
        session: AsyncSession,
    ):
        """Upsert replaces the action list — old actions are deleted, new ones
        from the DSL are created."""
        first = _remote(action_value="initial")
        await import_service.import_workflows_atomic(
            remote_workflows=[first], commit_sha="upsert-a-1"
        )

        wf_id = WorkflowUUID.new(first.id)
        wf = await _get_workflow_with_webhook(session, wf_id)
        # Single action initially
        assert len(wf.actions) == 1
        original_action_ids = {a.id for a in wf.actions}

        # Re-import with the SAME action `ref` but a different value → action
        # is recreated (delete + create), so its id changes.
        second = _remote(action_value="updated_value")
        await import_service.import_workflows_atomic(
            remote_workflows=[second], commit_sha="upsert-a-2"
        )

        wf = await _get_workflow_with_webhook(session, wf_id)
        assert len(wf.actions) == 1
        new_action_ids = {a.id for a in wf.actions}
        assert new_action_ids.isdisjoint(original_action_ids), (
            "Expected actions to be recreated (not the same row)"
        )

    @pytest.mark.anyio
    async def test_upsert_bumps_definition_version(
        self,
        import_service: WorkflowImportService,
        session: AsyncSession,
    ):
        """Each upsert appends a new WorkflowDefinition row with version N+1."""
        remote = _remote()
        await import_service.import_workflows_atomic(
            remote_workflows=[remote], commit_sha="v1"
        )
        await import_service.import_workflows_atomic(
            remote_workflows=[remote], commit_sha="v2"
        )
        await import_service.import_workflows_atomic(
            remote_workflows=[remote], commit_sha="v3"
        )

        wf_id = WorkflowUUID.new(remote.id)
        stmt = (
            select(WorkflowDefinition)
            .where(WorkflowDefinition.workflow_id == wf_id)
            .order_by(WorkflowDefinition.version.asc())
        )
        res = await session.execute(stmt)
        versions = [d.version for d in res.scalars().all()]
        assert versions == [1, 2, 3]

        wf = await _get_workflow_with_webhook(session, wf_id)
        assert wf.version == 3

    @pytest.mark.anyio
    async def test_upsert_with_explicit_webhook_overrides_status_methods(
        self,
        import_service: WorkflowImportService,
        session: AsyncSession,
    ):
        """When the remote definition includes a webhook block, status and
        methods are updated, but the webhook row identity stays stable."""
        first = _remote(webhook=RemoteWebhook(methods=["POST"], status="online"))
        await import_service.import_workflows_atomic(
            remote_workflows=[first], commit_sha="wh-1"
        )

        wf_id = WorkflowUUID.new(first.id)
        wf = await _get_workflow_with_webhook(session, wf_id)
        webhook_id_before = wf.webhook.id

        second = _remote(
            webhook=RemoteWebhook(methods=["POST", "GET"], status="offline"),
        )
        await import_service.import_workflows_atomic(
            remote_workflows=[second], commit_sha="wh-2"
        )

        wf = await _get_workflow_with_webhook(session, wf_id)
        assert wf.webhook.id == webhook_id_before  # identity stable
        assert wf.webhook.methods == ["POST", "GET"]  # methods updated
        assert wf.webhook.status == "offline"  # status updated
