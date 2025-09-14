from pydantic import BaseModel
from typing import List, Optional

class EmailMessage(BaseModel):
    sender: str
    recipient: str
    subject: str
    body: str
    timestamp: str

class IntentRecognitionResponse(BaseModel):
    intent: str
    confidence: float
    entities: Optional[dict] = None

class EmailThread(BaseModel):
    messages: List[EmailMessage]
    thread_id: str
    status: str  # e.g., 'open', 'closed', 'pending'