import {
  buildDuplicateAgentPresetPayload,
  buildDuplicateAgentSlug,
  canSubmitAgentPresetForm,
  getSubagentPresetUnavailableCode,
  getSubagentPresetUnavailableReason,
  getUnavailableSubagentPresetSlugs,
} from "@/lib/agent-presets"

describe("canSubmitAgentPresetForm", () => {
  it("keeps save disabled for new presets until model config is present", () => {
    expect(
      canSubmitAgentPresetForm({
        mode: "create",
        isDirty: true,
        name: "QA Save Debug Agent",
        modelProvider: "",
        modelName: "",
      })
    ).toBe(false)
  })

  it("allows save for new presets once required model config is present", () => {
    expect(
      canSubmitAgentPresetForm({
        mode: "create",
        isDirty: false,
        name: "QA Save Debug Agent",
        modelProvider: "openai",
        modelName: "gpt-4o-mini",
      })
    ).toBe(true)
  })

  it("allows save for edited presets when the form is dirty and required fields are present", () => {
    expect(
      canSubmitAgentPresetForm({
        mode: "edit",
        isDirty: true,
        name: "Existing agent",
        modelProvider: "openai",
        modelName: "gpt-4o-mini",
      })
    ).toBe(true)
  })

  it("keeps save disabled for edited presets when required fields are whitespace only", () => {
    expect(
      canSubmitAgentPresetForm({
        mode: "edit",
        isDirty: true,
        name: "   ",
        modelProvider: "   ",
        modelName: "   ",
      })
    ).toBe(false)
  })

  it("builds stable duplicate agent slugs with numeric suffixes", () => {
    expect(buildDuplicateAgentSlug("triage-agent", [])).toBe(
      "copy-of-triage-agent"
    )
    expect(
      buildDuplicateAgentSlug("triage-agent", ["copy-of-triage-agent"])
    ).toBe("copy-of-triage-agent-2")
    expect(
      buildDuplicateAgentSlug("triage-agent", [
        "copy-of-triage-agent",
        "copy-of-triage-agent-2",
      ])
    ).toBe("copy-of-triage-agent-3")
  })

  it("copies agent preset payload fields while renaming the duplicate", () => {
    const duplicated = buildDuplicateAgentPresetPayload(
      {
        id: "preset-1",
        workspace_id: "ws-1",
        name: "Triage agent",
        slug: "triage-agent",
        description: "Handles inbound incidents",
        instructions: "Investigate alerts",
        model_name: "gpt-4o-mini",
        model_provider: "openai",
        base_url: null,
        output_type: null,
        actions: ["core.http_request"],
        namespaces: ["core.http_request"],
        tool_approvals: { "core.http_request": true },
        mcp_integrations: ["mcp-1"],
        retries: 2,
        enable_internet_access: true,
        created_at: "2026-03-13T12:00:00Z",
        updated_at: "2026-03-13T12:00:00Z",
      },
      ["triage-agent"]
    )

    expect(duplicated.name).toBe("Copy of Triage agent")
    expect(duplicated.slug).toBe("copy-of-triage-agent")
    expect(duplicated.instructions).toBe("Investigate alerts")
    expect(duplicated.actions).toEqual(["core.http_request"])
    expect(duplicated.enable_internet_access).toBe(true)
  })

  it("marks approval-gated presets unavailable as subagents", () => {
    const preset = {
      slug: "approval-child",
      has_tool_approvals: true,
      subagent_unavailable_code: "tool_approvals" as const,
      subagent_unavailable_reason: "Approvals are unavailable for subagents.",
    }
    const availablePreset = {
      slug: "auto-child",
      has_tool_approvals: false,
      subagent_unavailable_code: null,
      subagent_unavailable_reason: null,
    }

    expect(getSubagentPresetUnavailableReason(preset)).toBe(
      "Approvals are unavailable for subagents."
    )
    expect(getSubagentPresetUnavailableCode(preset)).toBe("tool_approvals")
    expect(getSubagentPresetUnavailableReason(availablePreset)).toBeNull()
    expect(
      getUnavailableSubagentPresetSlugs([preset, availablePreset])
    ).toEqual(new Set(["approval-child"]))
  })

  it("marks presets with agents unavailable as subagents", () => {
    const preset = {
      slug: "nested-child",
      has_tool_approvals: false,
      subagent_unavailable_code: "agents_enabled" as const,
      subagent_unavailable_reason: "Agents are unavailable for subagents.",
    }

    expect(getSubagentPresetUnavailableReason(preset)).toBe(
      "Agents are unavailable for subagents."
    )
    expect(getSubagentPresetUnavailableCode(preset)).toBe("agents_enabled")
    expect(getUnavailableSubagentPresetSlugs([preset])).toEqual(
      new Set(["nested-child"])
    )
  })
})
