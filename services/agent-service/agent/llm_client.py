import anthropic

MODEL = "claude-haiku-5-5"


class ClaudeClient:
    """Sends messages to Claude. Tests can swap in a fake with the same method."""

    def __init__(self):
        self.client = anthropic.Anthropic()

    def send(self, system, messages, tools):
        return self.client.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=system,
            messages=messages,
            tools=tools,
        )