from typing import Annotated, Literal
from langchain_core.messages import ToolMessage
from langchain_core.tools import InjectedToolCallId, tool
from langgraph.prebuilt import InjectedState
from langgraph.types import Command
from pydantic import BaseModel, Field

# 1. Schema para restringir as opções do LLM e evitar alucinações de parâmetros
class TransferenciaSchema(BaseModel):
    especialidade: Literal["empresa", "profissional", "investidor", "parceria"] = Field(
        description="O perfil destino. Obrigatório para iniciar a transferência."
    )

# 2. A Tool oficial de Handoff
@tool("transferir_especialista", args_schema=TransferenciaSchema)
def transferir_especialista(
    especialidade: str,
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """Use esta ferramenta IMEDIATAMENTE após identificar a necessidade do usuário para transferi-lo ao especialista."""

    mapa_nos = {
        "empresa": "node_empresa",
        "profissional": "node_profissional",
        "investidor": "node_investidor",
        "parceria": "node_parceria",
    }

    destino_node = mapa_nos[especialidade]

    return Command(
        graph=Command.PARENT,
        goto=destino_node,
        update={
            "perfil_identificado": especialidade,
            "messages": [
                *state.get("messages", []),
                ToolMessage(
                    content=f"Transferindo para especialista: {especialidade}.",
                    tool_call_id=tool_call_id,
                )
            ],
        },
    )
