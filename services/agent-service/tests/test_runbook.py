from tools.runbook import search_runbook

SAMPLE = """# Runbook

## Payment failed over the limit
Orders above the limit fail on purpose.

## Order stuck after stock reserved
Check that payment-service is running, then retry.
"""


def test_finds_the_matching_section(tmp_path):
    path = tmp_path / "runbook.md"
    path.write_text(SAMPLE)
    result = search_runbook("order stuck waiting for payment", path=path)
    assert result["sections"][0]["title"] == "Order stuck after stock reserved"


def test_no_match_returns_nothing(tmp_path):
    path = tmp_path / "runbook.md"
    path.write_text(SAMPLE)
    assert search_runbook("banana", path=path)["sections"] == []


def test_missing_file_returns_an_error(tmp_path):
    assert "error" in search_runbook("anything", path=tmp_path / "missing.md")