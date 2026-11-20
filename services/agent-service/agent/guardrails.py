import json
import time
from pathlib import Path

# Tools that change data. They never run without a human saying yes.
WRITE_TOOLS = {"republish_order_placed"}

AUDIT_LOG = Path(__file__).resolve().parent.parent / "audit.jsonl"


def audit(event, **details):
    """Append one line to the audit log: what happened and when."""
    record = {"time": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "event": event, **details}
    with AUDIT_LOG.open("a") as file:
        file.write(json.dumps(record) + "\n")


def ask_human(tool_name, arguments):
    """Show the proposed action and wait for a yes or no from the person."""
    print(f"\n[approval needed] the agent wants to run {tool_name} {arguments}")
    answer = input("Allow this? Type yes to allow, anything else to deny: ")
    return answer.strip().lower() == "yes"