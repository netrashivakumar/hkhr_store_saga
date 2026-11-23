import re
from pathlib import Path

RUNBOOK = Path(__file__).resolve().parent.parent / "runbook" / "runbook.md"

STOP_WORDS = {"the", "a", "an", "is", "of", "to", "and", "in", "it", "why", "did",
              "was", "what", "how", "for", "order", "this", "my", "after", "on"}


def _sections(text):
    """Split the runbook into (title, body) pairs at '## ' headings."""
    parts = re.split(r"^## ", text, flags=re.MULTILINE)
    sections = []
    for part in parts[1:]:
        title, _, body = part.partition("\n")
        sections.append((title.strip(), body.strip()))
    return sections


def _words(text):
    return set(re.findall(r"[a-z0-9_]+", text.lower()))


def search_runbook(query, path=RUNBOOK, top=2):
    """Read-only: return the runbook sections that best match the query."""
    try:
        sections = _sections(Path(path).read_text())
    except OSError as error:
        return {"error": f"could not read runbook: {error}"}
    wanted = _words(query) - STOP_WORDS
    scored = []
    for title, body in sections:
        score = len(wanted & _words(body)) + 2 * len(wanted & _words(title))
        if score:
            scored.append((score, title, body))
    scored.sort(key=lambda item: -item[0])
    return {
        "query": query,
        "sections": [{"title": t, "text": b} for _, t, b in scored[:top]],
    }