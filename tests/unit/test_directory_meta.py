"""Tests for the directory `meta` extraction (feat/directory-meta).

`extract_workflow_meta` surfaces the declarative metadata bag of a
workflow — the `args.value` of its `meta` action — from the latest
committed definition. It is a pure function (no DB), so these tests use
a tiny stand-in for `WorkflowDefinition` with just `.version` and
`.content`.

Covers:
1. Workflow with a `meta` action -> its args.value is returned
2. Workflow with no definitions -> empty dict
3. Workflow with definitions but no `meta` action -> empty dict
4. Multiple definitions -> the highest `version` wins
5. Malformed `meta` action (no args / non-dict value) -> empty dict
"""

from dataclasses import dataclass

from tracecat.directory.schemas import extract_workflow_meta


@dataclass
class _FakeDefinition:
    """Minimal stand-in for WorkflowDefinition: only what the pure
    function reads (`version` for ordering, `content` for the DSL)."""

    version: int
    content: dict


def _def_with_meta(version: int, meta_value: dict) -> _FakeDefinition:
    return _FakeDefinition(
        version=version,
        content={
            "actions": [
                {"ref": "meta", "args": {"value": meta_value}},
                {"ref": "notify_flow_begin", "args": {}},
            ]
        },
    )


def test_extracts_meta_value_from_meta_action():
    meta_value = {
        "label": "Désactiver le compte",
        "name": "o365-disable-account",
        "version": "2.0.0",
    }
    definitions = [_def_with_meta(1, meta_value)]
    assert extract_workflow_meta(definitions) == meta_value


def test_no_definitions_returns_empty_dict():
    assert extract_workflow_meta([]) == {}


def test_no_meta_action_returns_empty_dict():
    definitions = [
        _FakeDefinition(
            version=1,
            content={"actions": [{"ref": "notify_flow_begin", "args": {}}]},
        )
    ]
    assert extract_workflow_meta(definitions) == {}


def test_latest_version_wins():
    definitions = [
        _def_with_meta(1, {"label": "old", "version": "1.0.0"}),
        _def_with_meta(3, {"label": "current", "version": "3.0.0"}),
        _def_with_meta(2, {"label": "middle", "version": "2.0.0"}),
    ]
    # version 3 is the latest, regardless of list order
    assert extract_workflow_meta(definitions) == {
        "label": "current",
        "version": "3.0.0",
    }


def test_malformed_meta_action_returns_empty_dict():
    # meta action present but args.value is not a dict (or missing)
    cases = [
        {"ref": "meta", "args": {"value": "not-a-dict"}},
        {"ref": "meta", "args": {}},
        {"ref": "meta"},
    ]
    for bad_meta in cases:
        definitions = [_FakeDefinition(version=1, content={"actions": [bad_meta]})]
        assert extract_workflow_meta(definitions) == {}


def test_empty_content_returns_empty_dict():
    definitions = [_FakeDefinition(version=1, content={})]
    assert extract_workflow_meta(definitions) == {}
    definitions = [_FakeDefinition(version=1, content=None)]
    assert extract_workflow_meta(definitions) == {}
