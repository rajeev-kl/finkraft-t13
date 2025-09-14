from typing import List, Optional
from sqlalchemy.orm import Session
from .models import EmailThread, EmailMessage, AISuggestion, UserDecision

def create_thread(db: Session, subject: str, sender: str, recipient: str, body: str) -> EmailThread:
    thread = EmailThread(subject=subject, sender=sender, recipient=recipient, body=body)
    db.add(thread)
    db.commit()
    db.refresh(thread)
    return thread


def get_thread_by_keys(db: Session, subject: str, sender: str, recipient: str) -> Optional[EmailThread]:
    return db.query(EmailThread).filter(
        EmailThread.subject == subject,
        EmailThread.sender == sender,
        EmailThread.recipient == recipient
    ).order_by(EmailThread.timestamp.desc()).first()


def get_or_create_thread(db: Session, subject: str, sender: str, recipient: str, body: str) -> EmailThread:
    existing = get_thread_by_keys(db, subject, sender, recipient)
    if existing:
        return existing
    return create_thread(db=db, subject=subject, sender=sender, recipient=recipient, body=body)


def get_thread(db: Session, thread_id: int) -> Optional[EmailThread]:
    return db.query(EmailThread).filter(EmailThread.id == thread_id).first()


def list_threads(db: Session, limit: int = 100) -> List[EmailThread]:
    return db.query(EmailThread).order_by(EmailThread.timestamp.desc()).limit(limit).all()


def create_message(db: Session, thread_id: int, sender: str, recipient: str, body: str) -> EmailMessage:
    msg = EmailMessage(thread_id=thread_id, sender=sender, recipient=recipient, body=body)
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return msg


def get_message_by_thread_and_body(db: Session, thread_id: int, body: str) -> Optional[EmailMessage]:
    return db.query(EmailMessage).filter(
        EmailMessage.thread_id == thread_id,
        EmailMessage.body == body
    ).order_by(EmailMessage.timestamp.desc()).first()


def create_ai_suggestion(db: Session, message_id: int, intent: str, confidence: float, suggested_action: str, required_fields: object | None = None, follow_up_question: str | None = None, raw_response: str | None = None) -> AISuggestion:
    import json as _json
    rf = None
    if required_fields is not None:
        try:
            rf = _json.dumps(required_fields)
        except Exception:
            # fallback: try to coerce to string
            try:
                rf = str(required_fields)
            except Exception:
                rf = None
    sug = AISuggestion(message_id=message_id, intent=intent, confidence=confidence, suggested_action=suggested_action, required_fields=rf, follow_up_question=follow_up_question, raw_response=raw_response)
    db.add(sug)
    db.commit()
    db.refresh(sug)
    return sug


def record_user_decision(db: Session, suggestion_id: int, user: str, decision: str, note: str | None = None) -> UserDecision:
    dec = UserDecision(suggestion_id=suggestion_id, user=user, decision=decision, note=note)
    db.add(dec)
    db.commit()
    db.refresh(dec)
    return dec


def list_messages_for_thread(db: Session, thread_id: int):
    return db.query(EmailMessage).filter(EmailMessage.thread_id == thread_id).order_by(EmailMessage.timestamp.asc()).all()


def list_suggestions_for_message(db: Session, message_id: int):
    return db.query(AISuggestion).filter(AISuggestion.message_id == message_id).order_by(AISuggestion.created_at.desc()).all()


def get_latest_suggestion_for_message(db: Session, message_id: int) -> AISuggestion | None:
    return db.query(AISuggestion).filter(AISuggestion.message_id == message_id).order_by(AISuggestion.created_at.desc()).first()


def create_email_thread(db: Session, email_thread: EmailThread) -> EmailThread:
    db.add(email_thread)
    db.commit()
    db.refresh(email_thread)
    return email_thread

def get_email_thread(db: Session, thread_id: int) -> Optional[EmailThread]:
    return db.query(EmailThread).filter(EmailThread.id == thread_id).first()

def get_email_threads(db: Session, skip: int = 0, limit: int = 10) -> List[EmailThread]:
    return db.query(EmailThread).offset(skip).limit(limit).all()


def has_accepted_decision_for_message(db: Session, message_id: int) -> bool:
    # Check whether any UserDecision exists for the latest suggestion on this message
    latest_sug = db.query(AISuggestion).filter(AISuggestion.message_id == message_id).order_by(AISuggestion.created_at.desc()).first()
    if not latest_sug:
        return False
    dec = db.query(UserDecision).filter(UserDecision.suggestion_id == latest_sug.id, UserDecision.decision == 'accept').first()
    return dec is not None


def has_accepted_decision_for_suggestion(db: Session, suggestion_id: int) -> bool:
    dec = db.query(UserDecision).filter(UserDecision.suggestion_id == suggestion_id, UserDecision.decision == 'accept').first()
    return dec is not None

def update_email_thread(db: Session, thread_id: int, updated_thread: EmailThread) -> Optional[EmailThread]:
    db_thread = get_email_thread(db, thread_id)
    if db_thread:
        for key, value in updated_thread.dict().items():
            setattr(db_thread, key, value)
        db.commit()
        db.refresh(db_thread)
    return db_thread

def delete_email_thread(db: Session, thread_id: int) -> Optional[EmailThread]:
    db_thread = get_email_thread(db, thread_id)
    if db_thread:
        db.delete(db_thread)
        db.commit()
    return db_thread


def create_email_draft(db: Session, thread_id: int, body: str, message_id: int | None = None, suggestion_id: int | None = None, customer_provided: dict | None = None, responder_provided: dict | None = None, status: str = 'draft'):
    from .models import EmailDraft
    import json as _json
    cp = None
    rp = None
    try:
        if customer_provided:
            cp = _json.dumps(customer_provided)
    except Exception:
        cp = None
    try:
        if responder_provided:
            rp = _json.dumps(responder_provided)
    except Exception:
        rp = None
    draft = EmailDraft(thread_id=thread_id, message_id=message_id, suggestion_id=suggestion_id, body=body, customer_provided=cp, responder_provided=rp)
    try:
        draft.status = status
    except Exception:
        pass
    db.add(draft)
    db.commit()
    db.refresh(draft)
    return draft


def mark_draft_sent(db: Session, draft_id: int):
    from .models import EmailDraft
    d = db.query(EmailDraft).filter(EmailDraft.id == draft_id).first()
    if not d:
        return None
    import datetime
    d.status = 'sent'
    d.sent_at = datetime.datetime.utcnow()
    db.commit()
    db.refresh(d)
    return d


def get_drafts_for_thread(db: Session, thread_id: int):
    from .models import EmailDraft
    return db.query(EmailDraft).filter(EmailDraft.thread_id == thread_id).order_by(EmailDraft.created_at.desc()).all()


def get_latest_draft_for_message(db: Session, message_id: int):
    from .models import EmailDraft
    return db.query(EmailDraft).filter(EmailDraft.message_id == message_id, EmailDraft.status == 'draft').order_by(EmailDraft.created_at.desc()).first()


def has_sent_draft_for_message(db: Session, message_id: int) -> bool:
    from .models import EmailDraft
    d = db.query(EmailDraft).filter(EmailDraft.message_id == message_id, EmailDraft.status == 'sent').order_by(EmailDraft.sent_at.desc()).first()
    return d is not None


def list_draft(db: Session):
    from .models import EmailDraft
    return db.query(EmailDraft).filter(EmailDraft.status == 'draft').order_by(EmailDraft.created_at.desc()).all()


def list_sent(db: Session):
    from .models import EmailDraft
    return db.query(EmailDraft).filter(EmailDraft.status == 'sent').order_by(EmailDraft.sent_at.desc()).all()


def delete_email_draft(db: Session, draft_id: int):
    from .models import EmailDraft
    d = db.query(EmailDraft).filter(EmailDraft.id == draft_id).first()
    if not d:
        return None
    db.delete(d)
    db.commit()
    return d