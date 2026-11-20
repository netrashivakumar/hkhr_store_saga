import time

INPUT_PRICE_PER_MTOK = 0.10   # USD per million input tokens (Haiku 5.5)
OUTPUT_PRICE_PER_MTOK = 0.50  # USD per million output tokens


class RunStats:
    """Collects the numbers for one agent run."""

    def __init__(self):
        self.started = time.time()
        self.steps = 0
        self.input_tokens = 0
        self.output_tokens = 0
        self.tool_calls = []

    def add_response(self, response):
        self.steps += 1
        usage = getattr(response, "usage", None)
        if usage:
            self.input_tokens += usage.input_tokens
            self.output_tokens += usage.output_tokens

    def add_tool_call(self, name, seconds, failed):
        self.tool_calls.append({"tool": name, "seconds": seconds, "failed": failed})

    @property
    def cost(self):
        return (self.input_tokens * INPUT_PRICE_PER_MTOK
                + self.output_tokens * OUTPUT_PRICE_PER_MTOK) / 1_000_000

    def print_summary(self):
        failed = sum(1 for call in self.tool_calls if call["failed"])
        print(
            f"[run] steps={self.steps} "
            f"input_tokens={self.input_tokens} output_tokens={self.output_tokens} "
            f"cost=${self.cost:.8f} seconds={time.time() - self.started:.1f} "
            f"tool_calls={len(self.tool_calls)} tool_errors={failed}"
        )