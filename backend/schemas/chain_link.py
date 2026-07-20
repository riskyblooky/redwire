from pydantic import BaseModel, Field
from typing import Optional, List


class ChainNodeRef(BaseModel):
    """A resolved reference to a chain endpoint, ready for rendering."""
    type: str
    id: str
    label: Optional[str] = None      # None when the entity no longer resolves (dangling)
    sub: Optional[str] = None        # category / item_type
    severity: Optional[str] = None   # findings only
    status: Optional[str] = None     # findings / testcases


class ChainLinkCreate(BaseModel):
    source_type: str
    source_id: str
    target_type: str
    target_id: str
    note: Optional[str] = Field(None, max_length=2000)


class ChainLinkNoteUpdate(BaseModel):
    note: Optional[str] = Field(None, max_length=2000)


class ChainLinkOut(BaseModel):
    id: str
    relation: str
    note: Optional[str] = None
    source: ChainNodeRef
    target: ChainNodeRef


class ChainNeighbor(BaseModel):
    """One end of a chain edge, seen from a focused entity's perspective."""
    link_id: str
    relation: str
    note: Optional[str] = None
    node: ChainNodeRef


class ChainLinksForEntity(BaseModel):
    upstream: List[ChainNeighbor]    # things that led to this entity (its causes)
    downstream: List[ChainNeighbor]  # things this entity led to (its effects)
    candidates: List[ChainNodeRef]   # flat-linked items not yet chained — promotable
