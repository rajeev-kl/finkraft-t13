from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
import datetime

Base = declarative_base()


class EmailThread(Base):
    __tablename__ = 'email_threads'

    id = Column(Integer, primary_key=True, index=True)
    subject = Column(String, index=True)
    sender = Column(String)
    recipient = Column(String)
    body = Column(Text)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    status = Column(String, default="pending")

    messages = relationship("EmailMessage", back_populates="thread", cascade="all, delete-orphan")
    actions = relationship("Action", back_populates="thread", cascade="all, delete-orphan")


class EmailMessage(Base):
    __tablename__ = 'email_messages'

    id = Column(Integer, primary_key=True, index=True)
    thread_id = Column(Integer, ForeignKey('email_threads.id'))
    sender = Column(String)
    recipient = Column(String)
    body = Column(Text)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)

    thread = relationship("EmailThread", back_populates="messages")
    ai_suggestions = relationship("AISuggestion", back_populates="message", cascade="all, delete-orphan")


class AISuggestion(Base):
    __tablename__ = 'ai_suggestions'

    id = Column(Integer, primary_key=True, index=True)
    message_id = Column(Integer, ForeignKey('email_messages.id'))
    intent = Column(String)
    confidence = Column(Float)
    suggested_action = Column(String)
    required_fields = Column(Text, nullable=True)
    follow_up_question = Column(Text, nullable=True)
    raw_response = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    message = relationship("EmailMessage", back_populates="ai_suggestions")


class UserDecision(Base):
    __tablename__ = 'user_decisions'

    id = Column(Integer, primary_key=True, index=True)
    suggestion_id = Column(Integer, ForeignKey('ai_suggestions.id'))
    user = Column(String)
    decision = Column(String)  # e.g., 'accept', 'override:reply_with_details'
    note = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class Action(Base):
    __tablename__ = 'actions'

    id = Column(Integer, primary_key=True, index=True)
    thread_id = Column(Integer, ForeignKey('email_threads.id'))
    action_type = Column(String)
    status = Column(String, default='pending')
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    thread = relationship("EmailThread", back_populates="actions")


class EmailDraft(Base):
    __tablename__ = 'email_drafts'

    id = Column(Integer, primary_key=True, index=True)
    thread_id = Column(Integer, ForeignKey('email_threads.id'))
    message_id = Column(Integer, ForeignKey('email_messages.id'), nullable=True)
    suggestion_id = Column(Integer, ForeignKey('ai_suggestions.id'), nullable=True)
    body = Column(Text)
    status = Column(String, default='draft')  # draft | sent
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow)
    sent_at = Column(DateTime, nullable=True)

    # JSON/text blobs to record values provided when the draft was generated
    customer_provided = Column(Text, nullable=True)
    responder_provided = Column(Text, nullable=True)

    thread = relationship("EmailThread")
    # message and suggestion relationships not required for basic flow