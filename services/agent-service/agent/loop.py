import json
import time

from agent.observability import RunStats
from tools.registry import TOOLS, run_tool

SYSTEM_PROMPT = (
    "You are an operations assistant for an online store. "
    "Use the tools to look up facts, then answer clearly and briefly. "
    "You can only read data. Never guess: if a tool returns an error, say so. "
    "How the store works: an order moves through the events OrderPlaced, "
    "StockReserved, PaymentConfirmed or PaymentFailed, then OrderCompleted "
    "or OrderFailed. When a payment fails, inventory-service releases the "
    "reserved stock, but it does not publish an event for that release, so "
    "the events cannot prove it. Say what the evidence shows and what it "
    "cannot show, and do not claim the stock is still reserved unless a "
    "tool shows it."
)

MAX_STEPS = 5


def run_agent(question, client):
    stats = RunStats()
    messages = [{"role": "user", "content": question}]
    for step in range(MAX_STEPS):
        response = client.send(SYSTEM_PROMPT, messages, TOOLS)
        stats.add_response(response)
        print(f"[step {step + 1}] stop_reason={response.stop_reason}")
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason != "tool_use":
            stats.print_summary()
            return "".join(b.text for b in response.content if b.type == "text")

        results = []
        for block in response.content:
            if block.type == "tool_use":
                print(f"[tool] {block.name} {block.input}")
                started = time.time()
                output = run_tool(block.name, block.input)
                failed = isinstance(output, dict) and "error" in output
                stats.add_tool_call(block.name, time.time() - started, failed)
                results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(output),
                })
        messages.append({"role": "user", "content": results})
    stats.print_summary()
    return "Stopped: too many steps."