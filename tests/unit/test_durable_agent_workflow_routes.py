from tracecat_ee.agent.workflows.durable import _subagent_litellm_route_model


def test_subagent_litellm_route_model_is_scope_specific() -> None:
    route_model = "openai/gpt-4o-mini"

    analyst_route = _subagent_litellm_route_model("analyst", route_model)
    writer_route = _subagent_litellm_route_model("writer", route_model)

    assert analyst_route == "openai/gpt-4o-mini::tracecat-subagent::analyst"
    assert writer_route == "openai/gpt-4o-mini::tracecat-subagent::writer"
    assert analyst_route != writer_route
