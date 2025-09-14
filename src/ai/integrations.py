from openai import AzureOpenAI
from config.settings import (
    AZURE_OPENAI_CHAT_API_KEY,
    AZURE_OPENAI_CHAT_API_VERSION,
    AZURE_OPENAI_CHAT_DEPLOYMENT,
    AZURE_OPENAI_CHAT_ENDPOINT,
)

from core.logger import logger
from typing import List, Dict, Optional
from pydantic import BaseModel
import json

client = AzureOpenAI(
    api_key=AZURE_OPENAI_CHAT_API_KEY,
    api_version=AZURE_OPENAI_CHAT_API_VERSION,
    azure_endpoint=AZURE_OPENAI_CHAT_ENDPOINT,
)

class FieldSpec(BaseModel):
    name: str
    hint: Optional[str] = None
    required: Optional[bool] = True


class IntentResponse(BaseModel):
    intent: str
    confidence: float
    suggested_action: str = "no-action"
    required_fields_customer: Optional[List[FieldSpec]] = None
    required_fields_responder: Optional[List[FieldSpec]] = None
    follow_up_question: Optional[str] = None

def get_intent(messages: List[Dict[str, str]], system_prompt: Optional[str] = None) -> IntentResponse:
    """
    Sends messages to the chat model and requests a compact JSON describing:
      - intent (string)
      - confidence (0.0-1.0)
      - suggested_action (small set of canonical actions)
      - required_fields (list of follow-up fields to request from user)
      - follow_up_question (optional single question to ask)

    A `system_prompt` may be provided; otherwise a default system instruction is used.
    """
    if system_prompt is None:
        system_prompt = (
            "You are an email assistant that MUST output a single JSON object (no extra text) describing the user's intent. "
            "Return the keys: intent (string), confidence (0-1 float), suggested_action (one of: send_pricing, ask_for_details, close_thread, escalate_to_ops, no-action), "
            "required_fields_customer (array of objects with keys: name (short id), hint (short human hint), required (boolean)), "
            "required_fields_responder (array of objects with keys: name, hint, required) — these are fields the responder/agent should fill (internal notes). "
            "follow_up_question (string) — a concise question to ask if more info is needed from the customer. "
            "Be conservative with confidence. Only include required fields that are actually missing and relevant. Return valid JSON only."
        )

    # ensure the system message is first
    wrapped_messages = []
    wrapped_messages.append({"role": "system", "content": system_prompt})
    wrapped_messages.extend(messages)

    try:
        # Ask the SDK to parse the response directly into the Pydantic model when possible.
        response = client.chat.completions.parse(
            model=AZURE_OPENAI_CHAT_DEPLOYMENT,
            messages=wrapped_messages,
            response_format=IntentResponse,
        )

        # The SDK may return the parsed Pydantic object directly, or a nested structure.
        # Try several shapes here for robustness.
        if getattr(response, "value", None) is not None:
            # Some SDK shapes place the parsed value on `response.value`
            val = response.value
            if isinstance(val, dict):
                # adapt older shapes where required_fields may be a list of strings
                try:
                    return IntentResponse(**val)
                except Exception:
                    # try to normalize legacy `required_fields` into customer list
                    if isinstance(val.get("required_fields"), list):
                        cust = []
                        for it in val.get("required_fields", []):
                            if isinstance(it, str):
                                cust.append({"name": it, "hint": None, "required": True})
                        val["required_fields_customer"] = cust
                        return IntentResponse(**val)
            if isinstance(val, IntentResponse):
                return val

        if getattr(response, "choices", None):
            choice = response.choices[0]
            # choice.message.content may be the parsed object
            content = None
            if hasattr(choice, "message") and hasattr(choice.message, "content"):
                content = choice.message.content
            elif hasattr(choice, "content"):
                content = choice.content
            elif hasattr(choice, "text"):
                content = choice.text

            if isinstance(content, IntentResponse):
                return content
            if isinstance(content, dict):
                try:
                    return IntentResponse(**content)
                except Exception:
                    # try to normalize legacy `required_fields` list
                    if isinstance(content.get("required_fields"), list):
                        cust = []
                        for it in content.get("required_fields", []):
                            if isinstance(it, str):
                                cust.append({"name": it, "hint": None, "required": True})
                        content["required_fields_customer"] = cust
                        return IntentResponse(**content)
                    raise
            if isinstance(content, str):
                # Try to parse the string into JSON and load the model
                try:
                    intent_data = json.loads(content)
                    try:
                        return IntentResponse(**intent_data)
                    except Exception:
                        # normalize legacy required_fields
                        if isinstance(intent_data.get("required_fields"), list):
                            cust = []
                            for it in intent_data.get("required_fields", []):
                                if isinstance(it, str):
                                    cust.append({"name": it, "hint": None, "required": True})
                            intent_data["required_fields_customer"] = cust
                            return IntentResponse(**intent_data)
                        raise
                except Exception:
                    # fallback to searching for a JSON substring
                    import re
                    m = re.search(r"\{.*\}", content, flags=re.S)
                    if m:
                        intent_data = json.loads(m.group(0))
                        try:
                            return IntentResponse(**intent_data)
                        except Exception:
                            if isinstance(intent_data.get("required_fields"), list):
                                cust = []
                                for it in intent_data.get("required_fields", []):
                                    if isinstance(it, str):
                                        cust.append({"name": it, "hint": None, "required": True})
                                intent_data["required_fields_customer"] = cust
                                return IntentResponse(**intent_data)
                            raise

    except Exception as e:
        logger.error(f"Error in AI integration while parsing to Pydantic model: {e}")
        # fall through to a safe return below
    except Exception as e:
        logger.error(f"Error in AI integration: {e}")
        return IntentResponse(intent="unknown", confidence=0.0)

    return IntentResponse(intent="unknown", confidence=0.0)


def generate_reply_draft(suggestion: str, original_message: str, tone: str = "professional") -> str:
    """Generate a reply draft based on the suggested action and the original message body."""
    prompt = (
        f"You are an assistant that writes a concise, clear email reply. The suggested action is: '{suggestion}'.\n"
        f"The original user message is:\n'''{original_message}'''\n"
        f"Write a reply in a {tone} tone that accomplishes the suggested action. Return only the email body text.")
    try:
        resp = client.chat.completions.create(
            model=AZURE_OPENAI_CHAT_DEPLOYMENT,
            messages=[{"role": "system", "content": "You are a helpful assistant."}, {"role": "user", "content": prompt}],
        )
        # Try several common shapes
        if getattr(resp, 'choices', None):
            c = resp.choices[0]
            if hasattr(c, 'message') and hasattr(c.message, 'content'):
                return c.message.content
            if hasattr(c, 'text'):
                return c.text
        # fallback to the raw string
        return str(resp)
    except Exception as e:
        logger.error(f"Error generating reply draft: {e}")
        return ""