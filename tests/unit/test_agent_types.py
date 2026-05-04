from temporalio.converter import value_to_type

from tracecat.agent.common.types import (
    SandboxAgentConfig,
    SandboxSubagentConfig,
    sandbox_requires_internet_access,
)
from tracecat.agent.types import AgentConfig


def test_temporal_converter_decodes_agent_config_with_mcp_servers() -> None:
    config = value_to_type(
        AgentConfig,
        {
            "model_name": "claude-3-5-sonnet-20241022",
            "model_provider": "anthropic",
            "mcp_servers": [
                {
                    "name": "Jira",
                    "type": "http",
                    "url": "https://mcp.atlassian.com/v1/mcp",
                    "headers": {"Authorization": "Bearer test-token"},
                }
            ],
        },
    )

    assert config.mcp_servers == [
        {
            "name": "Jira",
            "type": "http",
            "url": "https://mcp.atlassian.com/v1/mcp",
            "headers": {"Authorization": "Bearer test-token"},
        }
    ]


def test_sandbox_network_access_follows_root_agent_only() -> None:
    root_config = SandboxAgentConfig(
        model_name="gpt-4o-mini",
        model_provider="openai",
        enable_internet_access=False,
    )
    subagent = SandboxSubagentConfig(
        alias="web",
        description="Web-enabled subagent",
        prompt="Use web tools",
        config=SandboxAgentConfig(
            model_name="gpt-4o-mini",
            model_provider="openai",
            enable_internet_access=True,
        ),
        mcp_auth_token="token",
    )

    assert sandbox_requires_internet_access(root_config, [subagent]) is False


def test_sandbox_network_access_enabled_for_root_agent() -> None:
    root_config = SandboxAgentConfig(
        model_name="gpt-4o-mini",
        model_provider="openai",
        enable_internet_access=True,
    )

    assert sandbox_requires_internet_access(root_config, []) is True
