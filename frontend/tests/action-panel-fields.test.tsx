import { fireEvent, render, screen } from "@testing-library/react"
import type { ControllerRenderProps, FieldValues } from "react-hook-form"
import { MCPIntegrationField } from "@/components/builder/panel/action-panel-fields"
import { useListMcpIntegrations } from "@/lib/hooks"

jest.mock("@/providers/workspace-id", () => ({
  useWorkspaceId: () => "workspace-1",
}))

jest.mock("@/lib/hooks", () => ({
  useBuilderRegistryActions: () => ({ registryActions: [] }),
  useListMcpIntegrations: jest.fn(),
  useWorkspaceAgentModels: () => ({ models: [], providers: [] }),
}))

describe("MCPIntegrationField", () => {
  beforeAll(() => {
    global.ResizeObserver = class ResizeObserver {
      observe() {}
      unobserve() {}
      disconnect() {}
    }
  })

  it("renders saved MCP integrations and stores selected IDs", () => {
    const handleChange = jest.fn()
    jest.mocked(useListMcpIntegrations).mockReturnValue({
      mcpIntegrations: [
        {
          id: "mcp-1",
          workspace_id: "workspace-1",
          name: "Linear MCP",
          description: "Linear tools",
          slug: "linear",
          server_type: "http",
          server_uri: "https://mcp.linear.app",
          auth_type: "NONE",
          oauth_integration_id: null,
          stdio_command: null,
          stdio_args: null,
          has_stdio_env: false,
          timeout: 30,
          created_at: "2026-05-04T00:00:00Z",
          updated_at: "2026-05-04T00:00:00Z",
        },
      ],
      mcpIntegrationsIsLoading: false,
      mcpIntegrationsError: null,
    })

    render(
      <MCPIntegrationField
        field={
          {
            name: "inputs.mcp_integrations",
            value: [],
            onChange: handleChange,
          } as unknown as ControllerRenderProps<FieldValues>
        }
      />
    )

    const input = screen.getByPlaceholderText("Select MCP integrations")
    fireEvent.focus(input)
    fireEvent.mouseDown(screen.getByText("Linear MCP"))
    fireEvent.click(screen.getByText("Linear MCP"))

    expect(handleChange).toHaveBeenCalledWith(["mcp-1"])
  })
})
