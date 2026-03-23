from pydantic import BaseModel
from typing import Optional, Any


class DecisionRequest(BaseModel):
    type: str                    # "medication_reconciliation" | "data_quality"
    decision: str                # "approved" | "rejected"
    case_id: Optional[str] = None
    notes: Optional[str] = None
    data: Optional[Any] = None   # full AI result, stored so it can be restored on revisit


class DecisionResponse(BaseModel):
    id: str
    type: str
    decision: str
    case_id: Optional[str]
    notes: Optional[str]
    data: Optional[Any]
    timestamp: str
