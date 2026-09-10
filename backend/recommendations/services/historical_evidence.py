"""Content acceptance is independent of whether a fact is current."""

HISTORICAL_LABEL = "과거 자료·현재 미확인"
HISTORICAL_PREFIX = HISTORICAL_LABEL + ": "


def is_historical_tag(row):
    return row.source == "web_evidence" and (row.evidence or "").startswith(HISTORICAL_PREFIX)
