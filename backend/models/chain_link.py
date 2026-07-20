from sqlalchemy import Column, String, Text, ForeignKey, UniqueConstraint, Index
from database import Base, AuditMixin
import uuid


# The three entity types that can participate in an attack chain. Testcases
# are the "buckets" of work; findings and vault items (credentials/keys) are
# the causal linkage that connect them. A testcase → testcase edge is
# intentionally NOT allowed here — that relationship is the organizational
# `testcases.parent_id` tree, not a causal chain (enforced in the router).
CHAIN_NODE_TYPES = frozenset({"testcase", "finding", "vault_item"})

# The default (and, for v1, only) relation. Kept as a column so future
# relation flavours ("pivoted_to", "escalated_via", …) are additive without
# a schema change. Direction carries the meaning: source → target reads as
# "source led to target" (equivalently "target discovered_by source").
CHAIN_RELATION_DEFAULT = "led_to"


class ChainLink(Base, AuditMixin):
    """A directed causal edge in an engagement's attack chain.

    Polymorphic over CHAIN_NODE_TYPES. The (type, id) pairs are NOT real
    foreign keys — SQLAlchemy can't constrain a column that points at three
    different tables — so referential integrity is maintained by the app:
    each entity's delete path sweeps the chain_links it appears in (as source
    or target), and the attack-graph builder skips any edge whose endpoints
    no longer resolve. `engagement_id` IS a real FK and cascades, so deleting
    an engagement drops all its chain edges.
    """
    __tablename__ = "chain_links"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    # Indexed via the explicit Index in __table_args__ below (which the
    # migration creates); don't also pass index=True here or the ORM would
    # declare a second, migration-less index on the same column.
    engagement_id = Column(
        String, ForeignKey("engagements.id", ondelete="CASCADE"),
        nullable=False,
    )

    source_type = Column(String(20), nullable=False)   # testcase | finding | vault_item
    source_id = Column(String, nullable=False, index=True)
    target_type = Column(String(20), nullable=False)
    target_id = Column(String, nullable=False, index=True)

    relation = Column(String(30), nullable=False, default=CHAIN_RELATION_DEFAULT,
                      server_default=CHAIN_RELATION_DEFAULT)
    note = Column(Text, nullable=True)  # e.g. "used dumped NTLM hash to PtH into DC01"

    __table_args__ = (
        # A given directed pair links at most once. (The reverse direction is
        # a distinct edge and a distinct row — but the router also blocks
        # creating the inverse of an existing edge to avoid A→B and B→A both
        # existing, which would be a nonsensical 2-cycle.)
        UniqueConstraint(
            "source_type", "source_id", "target_type", "target_id",
            name="uq_chain_link_edge",
        ),
        Index("ix_chain_links_engagement", "engagement_id"),
    )
