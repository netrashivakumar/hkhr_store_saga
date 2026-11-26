import sys

from agent.llm_client import ClaudeClient
from agent.loop import run_agent

question = " ".join(sys.argv[1:])
print(run_agent(question, ClaudeClient()))