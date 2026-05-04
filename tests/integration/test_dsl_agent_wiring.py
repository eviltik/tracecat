from __future__ import annotations

import uuid
from collections.abc import Callable, Generator, Iterator, Sequence
from datetime import timedelta
from typing import Any

import pytest
from temporalio import activity
from temporalio.client import Client
from temporalio.worker import Worker
from tracecat_ee.agent.activities import BuildToolDefsArgs, BuildToolDefsResult
from tracecat_ee.agent.workflows.durable import DurableAgentWorkflow

from tests.shared import to_data
from tracecat import config
from tracecat.agent.executor.activity import (
    AgentExecutorInput,
    AgentExecutorResult,
)
from tracecat.agent.preset.activities import ResolveMCPIntegrationsActivityInput
from tracecat.agent.session.activities import (
    CreateSessionInput,
    CreateSessionResult,
    LoadSessionInput,
    LoadSessionResult,
)
from tracecat.agent.worker import (
    get_activities as get_agent_worker_activities,
)
from tracecat.agent.worker import (
    new_sandbox_runner as new_agent_sandbox_runner,
)
from tracecat.agent.workflow_schemas import MCPHttpServerConfigPayload
from tracecat.auth.types import Role
from tracecat.dsl.common import RETRY_POLICIES, DSLEntrypoint, DSLInput, DSLRunArgs
from tracecat.dsl.schemas import ActionStatement
from tracecat.dsl.worker import get_activities as get_dsl_worker_activities
from tracecat.dsl.workflow import DSLWorkflow
from tracecat.identifiers.workflow import WorkflowUUID, generate_exec_id
from tracecat.registry.lock.types import RegistryLock


def _activity_name(activity_def: object) -> str:
    return getattr(activity_def, "__temporal_activity_definition").name


@pytest.fixture(scope="session")
def minio_server() -> Iterator[None]:
    yield


@pytest.fixture(scope="session", autouse=True)
def workflow_bucket() -> Iterator[None]:
    yield


@pytest.fixture(autouse=True)
def disable_result_externalization(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(config, "TRACECAT__RESULT_EXTERNALIZATION_ENABLED", False)
    monkeypatch.setattr(
        config,
        "TRACECAT__RESULT_EXTERNALIZATION_THRESHOLD_BYTES",
        1024 * 1024,
    )
    yield


def _replace_activity(
    activities: Sequence[Callable[..., Any]],
    replacement: Callable[..., Any],
) -> list[Callable[..., Any]]:
    target_name = _activity_name(replacement)
    replaced = False
    updated: list[Callable[..., Any]] = []
    for existing in activities:
        if _activity_name(existing) == target_name:
            updated.append(replacement)
            replaced = True
        else:
            updated.append(existing)
    if not replaced:
        raise AssertionError(f"Activity {target_name!r} was not registered")
    return updated


def create_mock_create_session_activity(
    captured_inputs: list[CreateSessionInput] | None = None,
) -> Callable[..., Any]:
    @activity.defn(name="create_session_activity")
    async def mock_create_session_activity(
        input: CreateSessionInput,
    ) -> CreateSessionResult:
        if captured_inputs is not None:
            captured_inputs.append(input)
        return CreateSessionResult(session_id=input.session_id, success=True)

    return mock_create_session_activity


def create_mock_load_session_activity() -> Callable[..., Any]:
    @activity.defn(name="load_session_activity")
    async def mock_load_session_activity(_: LoadSessionInput) -> LoadSessionResult:
        return LoadSessionResult(
            found=False,
            sdk_session_id=None,
            sdk_session_data=None,
            is_fork=False,
        )

    return mock_load_session_activity


def create_mock_build_tool_definitions_activity(
    captured_inputs: list[BuildToolDefsArgs] | None = None,
) -> Callable[..., Any]:
    @activity.defn(name="build_tool_definitions")
    async def mock_build_tool_definitions(
        args: BuildToolDefsArgs,
    ) -> BuildToolDefsResult:
        if captured_inputs is not None:
            captured_inputs.append(args)
        return BuildToolDefsResult(
            tool_definitions={},
            registry_lock=RegistryLock(
                origins={"tracecat_registry": "test-version"},
                actions={},
            ),
            user_mcp_claims=None,
            allowed_internal_tools=None,
        )

    return mock_build_tool_definitions


def create_mock_resolve_mcp_integrations_activity(
    captured_inputs: list[ResolveMCPIntegrationsActivityInput] | None = None,
) -> Callable[..., Any]:
    @activity.defn(name="resolve_mcp_integrations_activity")
    async def mock_resolve_mcp_integrations(
        args: ResolveMCPIntegrationsActivityInput,
    ) -> list[MCPHttpServerConfigPayload]:
        if captured_inputs is not None:
            captured_inputs.append(args)
        return [
            MCPHttpServerConfigPayload(
                type="http",
                name="HTTP MCP",
                url="https://api.example.com/mcp",
            )
        ]

    return mock_resolve_mcp_integrations


def create_mock_run_agent_activity(*, output: str) -> Callable[..., Any]:
    @activity.defn(name="run_agent_activity")
    async def mock_run_agent_activity(
        input: AgentExecutorInput,
    ) -> AgentExecutorResult:
        del input
        activity.heartbeat("Mock agent running")
        return AgentExecutorResult(success=True, output=output)

    return mock_run_agent_activity


@pytest.fixture
def agent_worker_factory(
    threadpool: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[Callable[..., Worker], None, None]:
    def create_agent_worker(
        client: Client,
        *,
        task_queue: str,
        activities: Sequence[Callable[..., Any]],
    ) -> Worker:
        monkeypatch.setattr(config, "TRACECAT__AGENT_EXECUTOR_QUEUE", task_queue)
        monkeypatch.setattr(config, "TRACECAT__EXECUTOR_QUEUE", task_queue)
        return Worker(
            client=client,
            task_queue=task_queue,
            activities=activities,
            workflows=[DurableAgentWorkflow],
            workflow_runner=new_agent_sandbox_runner(),
            activity_executor=threadpool,
        )

    yield create_agent_worker


class TestDSLAgentWiring:
    @pytest.mark.anyio
    @pytest.mark.integration
    async def test_dsl_workflow_executes_ai_agent_on_agent_worker(
        self,
        test_role: Role,
        temporal_client: Client,
        test_worker_factory: Callable[..., Worker],
        agent_worker_factory: Callable[..., Worker],
    ) -> None:
        agent_activities = list(get_agent_worker_activities())
        for replacement in (
            create_mock_create_session_activity(),
            create_mock_load_session_activity(),
            create_mock_build_tool_definitions_activity(),
        ):
            agent_activities = _replace_activity(agent_activities, replacement)
        agent_activities.append(
            create_mock_run_agent_activity(output="dsl-agent-wired")
        )

        dsl = DSLInput(
            title="DSL agent wiring",
            description="Verify ai.agent spawns a child agent workflow",
            entrypoint=DSLEntrypoint(ref="agent"),
            actions=[
                ActionStatement(
                    ref="agent",
                    action="ai.agent",
                    args={
                        "user_prompt": "Investigate this alert",
                        "model_name": "gpt-4o-mini",
                        "model_provider": "openai",
                    },
                )
            ],
            returns="${{ ACTIONS.agent.result }}",
        )
        wf_id = WorkflowUUID.new_uuid4()

        async with test_worker_factory(
            temporal_client,
            activities=list(get_dsl_worker_activities()),
        ):
            async with agent_worker_factory(
                temporal_client,
                task_queue=config.TRACECAT__AGENT_QUEUE,
                activities=agent_activities,
            ):
                result = await temporal_client.execute_workflow(
                    DSLWorkflow.run,
                    DSLRunArgs(
                        dsl=dsl,
                        role=test_role,
                        wf_id=wf_id,
                    ),
                    id=generate_exec_id(wf_id),
                    task_queue=config.TEMPORAL__CLUSTER_QUEUE,
                    retry_policy=RETRY_POLICIES["workflow:fail_fast"],
                    execution_timeout=timedelta(seconds=60),
                )

        data = await to_data(result)
        assert data["output"] == "dsl-agent-wired"

    @pytest.mark.anyio
    @pytest.mark.integration
    async def test_dsl_workflow_resolves_ai_agent_mcp_integrations(
        self,
        test_role: Role,
        temporal_client: Client,
        test_worker_factory: Callable[..., Worker],
        agent_worker_factory: Callable[..., Worker],
    ) -> None:
        captured_resolver_inputs: list[ResolveMCPIntegrationsActivityInput] = []
        captured_tool_inputs: list[BuildToolDefsArgs] = []
        integration_id = "11111111-1111-1111-1111-111111111111"

        agent_activities = list(get_agent_worker_activities())
        for replacement in (
            create_mock_create_session_activity(),
            create_mock_load_session_activity(),
            create_mock_build_tool_definitions_activity(captured_tool_inputs),
        ):
            agent_activities = _replace_activity(agent_activities, replacement)
        agent_activities.append(
            create_mock_run_agent_activity(output="dsl-agent-mcp-wired")
        )

        dsl_activities = list(get_dsl_worker_activities())
        dsl_activities = _replace_activity(
            dsl_activities,
            create_mock_resolve_mcp_integrations_activity(captured_resolver_inputs),
        )

        dsl = DSLInput(
            title="DSL agent MCP wiring",
            description="Verify ai.agent resolves saved MCP integrations",
            entrypoint=DSLEntrypoint(ref="agent"),
            actions=[
                ActionStatement(
                    ref="agent",
                    action="ai.agent",
                    args={
                        "user_prompt": "Investigate this alert",
                        "model_name": "gpt-4o-mini",
                        "model_provider": "openai",
                        "mcp_integrations": [integration_id],
                    },
                )
            ],
            returns="${{ ACTIONS.agent.result }}",
        )
        wf_id = WorkflowUUID.new_uuid4()

        async with test_worker_factory(
            temporal_client,
            activities=dsl_activities,
        ):
            async with agent_worker_factory(
                temporal_client,
                task_queue=config.TRACECAT__AGENT_QUEUE,
                activities=agent_activities,
            ):
                result = await temporal_client.execute_workflow(
                    DSLWorkflow.run,
                    DSLRunArgs(
                        dsl=dsl,
                        role=test_role,
                        wf_id=wf_id,
                    ),
                    id=generate_exec_id(wf_id),
                    task_queue=config.TEMPORAL__CLUSTER_QUEUE,
                    retry_policy=RETRY_POLICIES["workflow:fail_fast"],
                    execution_timeout=timedelta(seconds=60),
                )

        data = await to_data(result)
        assert data["output"] == "dsl-agent-mcp-wired"
        assert captured_resolver_inputs[0].mcp_integrations == [integration_id]
        assert captured_tool_inputs[0].mcp_servers == [
            {
                "type": "http",
                "name": "HTTP MCP",
                "url": "https://api.example.com/mcp",
            }
        ]

    @pytest.mark.anyio
    @pytest.mark.integration
    async def test_dsl_workflow_marks_existing_agent_session_as_required(
        self,
        test_role: Role,
        temporal_client: Client,
        test_worker_factory: Callable[..., Worker],
        agent_worker_factory: Callable[..., Worker],
    ) -> None:
        session_id = uuid.uuid4()
        captured_inputs: list[CreateSessionInput] = []

        agent_activities = list(get_agent_worker_activities())
        for replacement in (
            create_mock_create_session_activity(captured_inputs),
            create_mock_load_session_activity(),
            create_mock_build_tool_definitions_activity(),
        ):
            agent_activities = _replace_activity(agent_activities, replacement)
        agent_activities.append(
            create_mock_run_agent_activity(output="dsl-agent-existing-session")
        )

        dsl = DSLInput(
            title="DSL agent existing session wiring",
            description="Verify ai.agent reuses a provided session ID",
            entrypoint=DSLEntrypoint(ref="agent"),
            actions=[
                ActionStatement(
                    ref="agent",
                    action="ai.agent",
                    args={
                        "user_prompt": "Continue this investigation",
                        "model_name": "gpt-4o-mini",
                        "model_provider": "openai",
                        "session_id": str(session_id),
                    },
                )
            ],
            returns="${{ ACTIONS.agent.result }}",
        )
        wf_id = WorkflowUUID.new_uuid4()

        async with test_worker_factory(
            temporal_client,
            activities=list(get_dsl_worker_activities()),
        ):
            async with agent_worker_factory(
                temporal_client,
                task_queue=config.TRACECAT__AGENT_QUEUE,
                activities=agent_activities,
            ):
                result = await temporal_client.execute_workflow(
                    DSLWorkflow.run,
                    DSLRunArgs(
                        dsl=dsl,
                        role=test_role,
                        wf_id=wf_id,
                    ),
                    id=generate_exec_id(wf_id),
                    task_queue=config.TEMPORAL__CLUSTER_QUEUE,
                    retry_policy=RETRY_POLICIES["workflow:fail_fast"],
                    execution_timeout=timedelta(seconds=60),
                )

        data = await to_data(result)
        assert data["output"] == "dsl-agent-existing-session"
        assert len(captured_inputs) == 1
        assert captured_inputs[0].session_id == session_id
        assert captured_inputs[0].require_existing is True
