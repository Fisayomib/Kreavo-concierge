import os
import time
import logging
import anthropic

RETRYABLE_ERRORS = (
    anthropic.APIConnectionError,  
    anthropic.RateLimitError,       
    anthropic.InternalServerError,  
    anthropic.OverloadedError,      
)

logger = logging.getLogger("kreavo-concierge")

CALL_TIMEOUT_SECONDS = 60.0
MAX_ATTEMPTS = 3
RETRY_WAITS = (2, 4)
MAX_REPLY_TOKENS = 500

SYSTEM_PROMPT = (
    "You are the WhatsApp assistant for a small business. "
    "Answer the customer's question directly and warmly, in plain language. "
    "Keep replies under 60 words, because they are read on a phone. "
    "If you do not know something about this business, say so and offer to pass the question on. "
    "Never invent prices, opening hours, stock or policies."
)


def get_client():
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    # max_retries=0: we run our own retry loop, so the worst-case time for one
    # call stays a number we can compute (the reaper threshold depends on it).
    return anthropic.Anthropic(api_key=api_key, timeout=CALL_TIMEOUT_SECONDS, max_retries=0)


def ask_claude(client, messages, model=None):
    model = model or os.environ.get("CLAUDE_MODEL", "").strip() or "claude-haiku-4-5-20251001"
    last_error = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = client.messages.create(
                model=model,
                max_tokens=MAX_REPLY_TOKENS,
                system=SYSTEM_PROMPT,
                messages=messages,
            )
            text = "".join(block.text for block in response.content if block.type == "text").strip()
            return text, response.usage.input_tokens, response.usage.output_tokens
        except RETRYABLE_ERRORS as e:
            last_error = e
            logger.warning("event=claude_call_failed attempt=%s retryable=true error=%s", attempt, e)
            if attempt < MAX_ATTEMPTS:
                time.sleep(RETRY_WAITS[attempt - 1])
        except Exception as e:
            logger.error("event=claude_call_failed attempt=%s retryable=false error=%s", attempt, e)
            raise
    raise last_error