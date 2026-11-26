import json
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.llm_client import ClaudeClient  # noqa: E402
from agent.loop import run_agent  # noqa: E402

SCENARIOS = Path(__file__).with_name("scenarios.json")


def check(answer, scenario):
    """Return a list of problems. An empty list means the answer passes."""
    text = answer.lower()
    problems = []
    for word in scenario["expected_all"]:
        if word.lower() not in text:
            problems.append(f"missing: {word}")
    any_words = scenario["expected_any"]
    if any_words and not any(w.lower() in text for w in any_words):
        problems.append(f"none of these appear: {any_words}")
    for word in scenario["forbidden"]:
        if word.lower() in text:
            problems.append(f"forbidden phrase: {word}")
    return problems


def fake_tools(scenario):
    results = {
        "get_order_status": scenario["status_result"],
        "get_order_events": scenario["events_result"],
    }
    return lambda name, arguments: results[name]


def main():
    scenarios = json.loads(SCENARIOS.read_text())
    client = ClaudeClient()
    failed = 0
    for scenario in scenarios:
        with patch("agent.loop.run_tool", fake_tools(scenario)):
            answer = run_agent(scenario["question"], client)
        problems = check(answer, scenario)
        print(f"{'PASS' if not problems else 'FAIL'}  {scenario['name']}")
        if problems:
            failed += 1
            print("   problems:", "; ".join(problems))
            print("   answer:", answer)
    print(f"\n{len(scenarios) - failed} of {len(scenarios)} passed")
    sys.exit(1 if failed else 0)


main()