import re

from app.state import TriageState


def normalize_request(state: TriageState) -> TriageState:
    return {"normalized_message": re.sub(r"\s+", " ", state["raw_message"]).strip()}
