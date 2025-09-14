import json
import logging
from typing import Any, Dict, List

from ai.integrations import get_intent
from core.rules import rule_based_intent_and_action
from db import models
from db.crud import (
    create_ai_suggestion,
    create_message,
    create_thread,
    get_message_by_thread_and_body,
    get_or_create_thread,
    has_accepted_decision_for_message,
)
from db.session import SessionLocal, engine

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


# Create the database tables
def init_db():
    logger.info("Creating database tables...")
    from sqlalchemy import text

    try:
        # Check whether the existing table has the new 'timestamp' column
        with engine.connect() as conn:
            res = conn.execute(text("PRAGMA table_info(email_threads)"))
            cols = [row[1] for row in res]
            if cols and "timestamp" not in cols:
                logger.info(
                    "Existing 'email_threads' table missing 'timestamp' column — recreating tables for dev environment"
                )
                models.Base.metadata.drop_all(bind=engine)
                models.Base.metadata.create_all(bind=engine)
            else:
                models.Base.metadata.create_all(bind=engine)
        logger.info("Database tables created successfully.")
    except Exception:
        logger.exception("Error checking/creating database tables — recreating tables")
        models.Base.metadata.drop_all(bind=engine)
        models.Base.metadata.create_all(bind=engine)
        logger.info("Database tables recreated successfully.")


# Function to process and persist a single email thread (uses an explicit Session)
def process_email_thread(subject: str, sender: str, recipient: str, body: str, db=None) -> models.EmailThread:
    logger.info(f"Processing email thread from {sender} to {recipient} with subject '{subject}'")
    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True
    try:
        thread = create_thread(db=db, subject=subject, sender=sender, recipient=recipient, body=body)
        logger.info(f"Email thread processed and saved: {thread}")
        return thread
    finally:
        if close_db:
            db.close()


# New: Function to process uploaded JSON (Streamlit file_uploader output)
def process_email_threads(uploaded_file) -> List[Dict[str, Any]]:
    """
    Accepts a file-like object (Streamlit uploaded file), expects JSON containing either:
      - a list of thread objects, or
      - {"threads": [ ... ]}
    Each thread object should have keys: subject, sender, recipient, body (fallback to empty string).
    Returns list of saved thread summaries (dicts).
    """
    try:
        raw = uploaded_file.read()
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        data = json.loads(raw)
    except Exception:
        logger.exception("Failed to read/parse uploaded JSON file")
        return []

    # normalize to list of threads
    if isinstance(data, dict) and "threads" in data and isinstance(data["threads"], list):
        threads = data["threads"]
    elif isinstance(data, list):
        threads = data
    else:
        logger.error("Uploaded JSON not in expected format (list or {threads: [...]})")
        return []

    saved = []
    db = SessionLocal()
    try:
        for i, t in enumerate(threads):
            try:
                subject = t.get("subject", f"no-subject-{i}")
                sender = t.get("sender", "")
                recipient = t.get("recipient", "")
                body = t.get("body", "")
                messages = t.get("messages", [])

                # Use idempotent create-or-get to avoid duplicate threads on reprocess
                thread_model = get_or_create_thread(
                    db=db, subject=subject, sender=sender, recipient=recipient, body=body
                )

                # if thread contains message list, persist messages and call AI
                for m in messages:
                    try:
                        m_sender = m.get("sender", "")
                        m_recipient = m.get("recipient", "")
                        m_body = m.get("body", "")
                        # Avoid duplicate messages by checking body within the thread
                        existing_msg = get_message_by_thread_and_body(db=db, thread_id=thread_model.id, body=m_body)
                        if existing_msg:
                            msg_model = existing_msg
                        else:
                            msg_model = create_message(
                                db=db, thread_id=thread_model.id, sender=m_sender, recipient=m_recipient, body=m_body
                            )

                        # If a human already accepted a suggestion for this message, skip re-evaluation.
                        if has_accepted_decision_for_message(db=db, message_id=msg_model.id):
                            logger.info(
                                f"Skipping re-evaluation for message {msg_model.id} because a suggestion was accepted"
                            )
                            continue

                        # call AI to get intent (safe fallback to unknown)
                        ai_resp = None
                        try:
                            ai_resp = get_intent([{"role": "user", "content": m_body}])
                            intent = getattr(ai_resp, "intent", "unknown")
                            confidence = getattr(ai_resp, "confidence", 0.0)
                            # Prefer the AI-provided suggested_action when available
                            ai_suggested_action = getattr(ai_resp, "suggested_action", None)
                        except Exception:
                            logger.exception("AI intent detection failed, using fallback")
                            intent = "unknown"
                            confidence = 0.0
                            ai_suggested_action = None

                        # Extract structured required fields from AI response when present
                        required_fields_customer = None
                        required_fields_responder = None
                        follow_up_question = None
                        try:
                            if ai_resp is not None:
                                # New structured fields
                                required_fields_customer = getattr(ai_resp, "required_fields_customer", None)
                                required_fields_responder = getattr(ai_resp, "required_fields_responder", None)
                                # Legacy fallback: a flat `required_fields` (list of strings) -> customer fields
                                legacy = getattr(ai_resp, "required_fields", None)
                                if not required_fields_customer and legacy:
                                    # turn list of strings into list of dicts
                                    try:
                                        required_fields_customer = [
                                            {"name": x, "hint": None, "required": True} for x in legacy
                                        ]
                                    except Exception:
                                        required_fields_customer = None
                                follow_up_question = getattr(ai_resp, "follow_up_question", None)
                        except Exception:
                            required_fields_customer = None
                            required_fields_responder = None
                            follow_up_question = None

                        # Ensure suggested_action is always defined. Use rule-based fallback
                        # when AI is unknown or low-confidence. Otherwise map recognized
                        # intents to default actions. Log the provenance for debugging.
                        suggested_action = "no-action"
                        provenance = "ai"
                        try:
                            # If AI returned an explicit suggested_action (and it's not the default
                            # placeholder), use it. This covers cases where the model's intent
                            # name doesn't map cleanly to our internal intent-to-action table.
                            if ai_suggested_action:
                                # normalize empty/placeholder
                                if (
                                    isinstance(ai_suggested_action, str)
                                    and ai_suggested_action.strip()
                                    and ai_suggested_action != "no-action"
                                ):
                                    suggested_action = ai_suggested_action

                            # If no usable AI action, fall back to rule-based intent/action
                            if suggested_action == "no-action":
                                if intent == "unknown" or confidence < 0.6:
                                    r_intent, r_conf, r_action = rule_based_intent_and_action(m_body)
                                    if r_conf > confidence:
                                        intent = r_intent
                                        confidence = r_conf
                                        suggested_action = r_action
                                        provenance = "rule"
                                else:
                                    # map recognized intents to actions
                                    if intent == "interested":
                                        suggested_action = "send_pricing"
                                    elif intent == "not_interested":
                                        suggested_action = "close_thread"
                                    elif intent == "cancel_request" or intent == "cancel_booking_and_request_refund":
                                        suggested_action = "start_cancellation_flow"
                                    elif intent == "escalation" or intent == "request_escalation_to_manager":
                                        suggested_action = "escalate_to_manager"
                                    elif intent in ("request_group_availability_and_rates", "group_availability"):
                                        suggested_action = "send_group_rates"
                        except Exception:
                            logger.exception("Error while determining suggested_action; defaulting to 'no-action'")

                        rf_payload = {"customer": required_fields_customer, "responder": required_fields_responder}
                        # try to serialize the raw AI response for provenance/audit
                        raw_resp = None
                        try:
                            import json as _json

                            try:
                                # some ai_resp may be a pydantic model or object with dict()
                                if hasattr(ai_resp, "dict"):
                                    raw_resp = _json.dumps(ai_resp.dict(), default=str)
                                else:
                                    raw_resp = _json.dumps(ai_resp, default=str)
                            except Exception:
                                raw_resp = str(ai_resp)
                        except Exception:
                            raw_resp = None

                        logger.info(
                            "Persisting AISuggestion (provenance=%s) for message=%s intent=%s confidence=%.2f "
                            "action=%s required_fields_customer=%s required_fields_responder=%s follow_up=%s",
                            provenance,
                            msg_model.id,
                            intent,
                            confidence,
                            suggested_action,
                            required_fields_customer,
                            required_fields_responder,
                            follow_up_question,
                        )
                        create_ai_suggestion(
                            db=db,
                            message_id=msg_model.id,
                            intent=intent,
                            confidence=confidence,
                            suggested_action=suggested_action,
                            required_fields=rf_payload,
                            follow_up_question=follow_up_question,
                            raw_response=raw_resp,
                        )

                    except Exception:
                        logger.exception("Failed to persist message or AI suggestion, continuing")
                        continue

                saved.append(
                    {
                        "id": thread_model.id,
                        "subject": thread_model.subject,
                        "sender": thread_model.sender,
                        "recipient": thread_model.recipient,
                        "status": thread_model.status,
                    }
                )
            except Exception:
                logger.exception("Failed to process a thread entry, skipping")
                continue
    finally:
        db.close()

    logger.info(f"Processed {len(saved)} threads from uploaded file")
    return saved


# Initialize the database
init_db()
