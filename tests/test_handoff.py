import unittest

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, ToolMessage
from langgraph.graph import END, START, StateGraph, add_messages
from langgraph.prebuilt import ToolNode
from typing_extensions import Annotated, TypedDict

from src.agents.lia import agent_lia
from src.tools.tools_lia import transferir_especialista


class HandoffState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    perfil_identificado: str | None
    visited_specialist: bool | None


def invoke_parent_handoff():
    tool_call = {
        "name": "transferir_especialista",
        "args": {"especialidade": "empresa"},
        "id": "call-empresa",
        "type": "tool_call",
    }

    child = StateGraph(HandoffState)
    child.add_node(
        "model",
        lambda _state: {"messages": [AIMessage(content="", tool_calls=[tool_call])]},
    )
    child.add_node("tools", ToolNode([transferir_especialista]))
    child.add_edge(START, "model")
    child.add_edge("model", "tools")

    parent = StateGraph(HandoffState)
    parent.add_node("lia", child.compile())
    parent.add_node("node_empresa", lambda _state: {"visited_specialist": True})
    parent.add_edge(START, "lia")
    parent.add_edge("node_empresa", END)

    app = parent.compile()
    return app.invoke(
        {"messages": [HumanMessage(content="empresa")], "perfil_identificado": None}
    )


class HandoffTests(unittest.TestCase):
    def test_transfer_tool_routes_parent_graph_to_specialist(self):
        result = invoke_parent_handoff()

        tool_messages = [
            message for message in result["messages"] if isinstance(message, ToolMessage)
        ]

        self.assertEqual(result["perfil_identificado"], "empresa")
        self.assertTrue(result["visited_specialist"])
        self.assertEqual(len(tool_messages), 1)
        self.assertEqual(tool_messages[0].tool_call_id, "call-empresa")

    def test_parent_handoff_preserves_main_agent_tool_call_message(self):
        result = invoke_parent_handoff()

        self.assertEqual(
            [type(message).__name__ for message in result["messages"]],
            ["HumanMessage", "AIMessage", "ToolMessage"],
        )

    def test_exported_graph_contains_specialist_nodes(self):
        node_names = set(agent_lia.get_graph().nodes)

        self.assertTrue(
            {
                "lia",
                "node_empresa",
                "node_profissional",
                "node_investidor",
                "node_parceria",
            }.issubset(node_names)
        )


if __name__ == "__main__":
    unittest.main()
