"""Building and measuring the one request the gateway sends.

The gateway never sends more than `max_input_bytes` of text in total: the fixed system instructions,
the fleet context and the question together. The size is measured on the exact strings that are
sent, so nothing is hidden outside the count.

HOW THE RESERVED INPUT TOKENS ARE BOUNDED, AND WHAT THAT ASSUMES. The reservation uses
`reserved_input_tokens = utf-8 bytes of everything sent + REQUEST_OVERHEAD_TOKENS`. That is a bound
only under these assumptions, none of which the provider guarantees in writing:

 A1. A token covers at least one byte of the text, so the text cannot cost more tokens than bytes.
 A2. The provider's own framing of one system text and one user message (role markers, wrappers)
     adds fewer than `REQUEST_OVERHEAD_TOKENS` tokens. No tools, images or documents are sent.
 A3. The prompt stays far below 100,000 tokens, so the base price tier applies.

Because they are assumptions, they are checked on every call: the provider reports the prompt
tokens it actually counted, and if that ever exceeds the reservation the gateway charges the real
cost and halts itself (see `gateway.py`), so a wrong assumption stops spending after one request
instead of silently continuing.
"""

from dataclasses import dataclass

from app.ai.errors import InvalidQuestionError, PromptTooLargeError

# Fixed instructions. They count toward the input size like everything else.
SYSTEM_PROMPT = (
    "You are the read-only operations assistant of SkyFleet, a simulated urban drone-delivery "
    "platform. Answer only from the fleet context you are given; if it does not contain the "
    "answer, say so. You cannot take actions, change anything or call tools. Keep answers short."
)

# Allowance for the provider's own message framing (assumption A2).
REQUEST_OVERHEAD_TOKENS = 1024


@dataclass(frozen=True)
class PreparedRequest:
    system: str
    user_content: str
    input_bytes: int
    reserved_input_tokens: int


def build_user_content(question: str, context: str) -> str:
    """The single user message: the context (data, not instructions) and then the question."""
    if context:
        return f"Fleet context:\n{context}\n\nQuestion:\n{question}"
    return f"Question:\n{question}"


def prepare_request(
    question: str, context: str, *, max_question_chars: int, max_input_bytes: int
) -> PreparedRequest:
    """Validate and measure a request; raises before anything is reserved or sent."""
    if not isinstance(question, str) or not question.strip():
        raise InvalidQuestionError("The question is empty.")
    if len(question) > max_question_chars:
        raise InvalidQuestionError(f"The question is longer than {max_question_chars} characters.")
    user_content = build_user_content(question, context)
    input_bytes = len(SYSTEM_PROMPT.encode("utf-8")) + len(user_content.encode("utf-8"))
    if input_bytes > max_input_bytes:
        raise PromptTooLargeError(
            f"The request is {input_bytes} bytes; the limit is {max_input_bytes} bytes "
            "(instructions and context included)."
        )
    return PreparedRequest(
        system=SYSTEM_PROMPT,
        user_content=user_content,
        input_bytes=input_bytes,
        reserved_input_tokens=input_bytes + REQUEST_OVERHEAD_TOKENS,
    )
