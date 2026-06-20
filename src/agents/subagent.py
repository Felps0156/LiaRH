from langchain.agents import create_agent
from langchain_google_genai import ChatGoogleGenerativeAI

from src.core.config import MODEL
from src.core.prompts import system_prompt_profissional, system_prompt_parceria, system_prompt_investidor, system_prompt_empresa

model = ChatGoogleGenerativeAI(model=MODEL)

agent_profissional = create_agent(
    model=model,
    system_prompt=system_prompt_profissional
)

agent_parceria = create_agent(
    model=model,
    system_prompt=system_prompt_parceria
)

agent_investidor = create_agent(
    model=model,
    system_prompt=system_prompt_investidor
)

agent_empresa = create_agent(
    model=model,
    system_prompt=system_prompt_empresa,
)

