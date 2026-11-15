"""Preparing the operator's question (Feature 026): one line, no forged context, named drones.

The question reaches the model as the last part of the user message, after `Fleet context:` and
the snapshot. To keep it from being mistaken for (or hiding) that data it is made ONE line of
plain text: every whitespace and control character, newlines included, becomes a single space, so
it cannot start a line of its own, and the words "fleet context" are refused outright (a question
that mentions them could pose as a second snapshot). The word "question" is not refused: after
this normalisation it cannot begin a line and the question is operator text by design.

Named drones: ids written as `DRN-7`, `drn 007` or `DRN-0007` are normalised to the backend's own
format `DRN-NNN` (three digits at least, see `drones.service`), at most `MAX_NAMED_DRONES` distinct
ones, in the order they were mentioned. Only that exact pattern is recognised, so there is no fuzzy
or ambiguous matching, and no database access happens here: the snapshot builder ranks the matching
rows and reports whether each named drone exists and is listed.
"""

import re
import unicodedata
from dataclasses import dataclass

from app.ai.errors import InvalidQuestionError
from app.fleet_context.schemas import MAX_NAMED_DRONES

_DELIMITER = re.compile(r"fleet[\s_\-]*context", re.IGNORECASE)
_DRONE_ID = re.compile(r"\bDRN[-\s]?([0-9]{1,6})\b", re.IGNORECASE | re.ASCII)
_BLANK_CATEGORIES = frozenset({"Cc", "Cf", "Zl", "Zp", "Zs"})


@dataclass(frozen=True)
class PreparedQuestion:
    text: str
    named_drones: tuple[str, ...]


def _one_line(question: str) -> str:
    spaced = "".join(
        " " if char.isspace() or unicodedata.category(char) in _BLANK_CATEGORIES else char
        for char in question
    )
    return " ".join(spaced.split())


def prepare_question(question: str) -> PreparedQuestion:
    """The question as one line plus the drones it names, or `InvalidQuestionError`."""
    if not isinstance(question, str):
        raise InvalidQuestionError("The question is empty.")
    text = _one_line(question)
    if not text:
        raise InvalidQuestionError("The question is empty.")
    if _DELIMITER.search(text):
        raise InvalidQuestionError("The question must not contain the words 'fleet context'.")
    named: list[str] = []
    for match in _DRONE_ID.finditer(text):
        drone_id = f"DRN-{int(match.group(1)):03d}"
        if drone_id not in named:
            named.append(drone_id)
    return PreparedQuestion(text, tuple(named[:MAX_NAMED_DRONES]))
