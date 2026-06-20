from langchain.agents import create_agent
from langchain_core.messages import AnyMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import END, START, StateGraph, add_messages
from typing_extensions import Annotated, TypedDict

from src.agents.subagent import (
    agent_empresa,
    agent_investidor,
    agent_parceria,
    agent_profissional,
)
from src.core.config import MODEL
from src.core.prompts import system_prompt_lia
from src.tools.tools_lia import transferir_especialista


class LiaState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    perfil_identificado: str | None

model = ChatGoogleGenerativeAI(model=MODEL)

tools = [
    transferir_especialista,
]

_main_agent = create_agent(
    model=model,
    system_prompt=system_prompt_lia,
    tools=tools
)

_graph = StateGraph(LiaState)
_graph.add_node("lia", _main_agent)
_graph.add_node("node_empresa", agent_empresa)
_graph.add_node("node_profissional", agent_profissional)
_graph.add_node("node_investidor", agent_investidor)
_graph.add_node("node_parceria", agent_parceria)
_graph.add_edge(START, "lia")
_graph.add_edge("node_empresa", END)
_graph.add_edge("node_profissional", END)
_graph.add_edge("node_investidor", END)
_graph.add_edge("node_parceria", END)

agent_lia = _graph.compile()
