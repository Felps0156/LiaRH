from langchain.agents import create_agent
from langchain_google_genai import ChatGoogleGenerativeAI

from src.core.config import MODEL
from src.core.prompts import system_prompt_lia
from src.tools.tools_lia import transferir_especialista
from src.agents.subagent import agent_empresa, agent_investidor, agent_parceria, agent_profissional

model = ChatGoogleGenerativeAI(model=MODEL)

tools = [
    transferir_especialista,
    agent_empresa,
    agent_investidor,
    agent_parceria,
    agent_profissional,
]

agent_lia = create_agent(
    model=model,
    system_prompt=system_prompt_lia,
    tools=tools
)