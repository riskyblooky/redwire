from sqlalchemy import Column, String, ForeignKey, Table, Text, Boolean, DateTime
from sqlalchemy.orm import relationship
from database import Base
from datetime import datetime
import json


class ClientUserAccess(Base):
    """Grants a user read access to a client (and all its descendants)."""
    __tablename__ = "client_user_access"

    client_id = Column(String, ForeignKey("clients.id", ondelete="CASCADE"), primary_key=True)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    granted_by = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    granted_at = Column(DateTime, default=datetime.utcnow, nullable=False)

class EngagementAssignment(Base):
    __tablename__ = "engagement_assignments"
    
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    engagement_id = Column(String, ForeignKey("engagements.id", ondelete="CASCADE"), primary_key=True)
    role_id = Column(String, ForeignKey("engagement_roles.id", ondelete="SET NULL"), nullable=True)

    # Relationships
    role = relationship("EngagementRole")
    user = relationship("User", back_populates="assignment_details")
    engagement = relationship("Engagement", back_populates="assignment_details")

class FindingAsset(Base):
    __tablename__ = "finding_assets"
    
    finding_id = Column(String, ForeignKey("findings.id", ondelete="CASCADE"), primary_key=True)
    asset_id = Column(String, ForeignKey("assets.id", ondelete="CASCADE"), primary_key=True)
    port_ids = Column(Text, nullable=True)  # JSON array of port IDs
    remediated = Column(Boolean, default=False, nullable=False)
    remediated_at = Column(DateTime, nullable=True)
    remediated_by = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    @property
    def parsed_port_ids(self) -> list[str] | None:
        """Parse port_ids JSON string into a list, returning None on failure."""
        if not self.port_ids:
            return None
        try:
            return json.loads(self.port_ids)
        except (json.JSONDecodeError, TypeError):
            return None

class FindingTag(Base):
    __tablename__ = "finding_tags"
    
    finding_id = Column(String, ForeignKey("findings.id", ondelete="CASCADE"), primary_key=True)
    tag_id = Column(String, ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True)

class TestCaseTag(Base):
    __tablename__ = "testcase_tags"
    
    testcase_id = Column(String, ForeignKey("testcases.id", ondelete="CASCADE"), primary_key=True)
    tag_id = Column(String, ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True)

class FindingTestCase(Base):
    __tablename__ = "finding_testcases"
    
    finding_id = Column(String, ForeignKey("findings.id", ondelete="CASCADE"), primary_key=True)
    testcase_id = Column(String, ForeignKey("testcases.id", ondelete="CASCADE"), primary_key=True)

class VaultItemFinding(Base):
    __tablename__ = "vault_item_findings"
    
    vault_item_id = Column(String, ForeignKey("vault_items.id", ondelete="CASCADE"), primary_key=True)
    finding_id = Column(String, ForeignKey("findings.id", ondelete="CASCADE"), primary_key=True)

class VaultItemTestCase(Base):
    __tablename__ = "vault_item_testcases"
    
    vault_item_id = Column(String, ForeignKey("vault_items.id", ondelete="CASCADE"), primary_key=True)
    testcase_id = Column(String, ForeignKey("testcases.id", ondelete="CASCADE"), primary_key=True)

class VaultItemAsset(Base):
    __tablename__ = "vault_item_assets"

    vault_item_id = Column(String, ForeignKey("vault_items.id", ondelete="CASCADE"), primary_key=True)
    asset_id = Column(String, ForeignKey("assets.id", ondelete="CASCADE"), primary_key=True)

class CleanupArtifactFinding(Base):
    __tablename__ = "cleanup_artifact_findings"
    
    cleanup_artifact_id = Column(String, ForeignKey("cleanup_artifacts.id", ondelete="CASCADE"), primary_key=True)
    finding_id = Column(String, ForeignKey("findings.id", ondelete="CASCADE"), primary_key=True)

class CleanupArtifactTestCase(Base):
    __tablename__ = "cleanup_artifact_testcases"
    
    cleanup_artifact_id = Column(String, ForeignKey("cleanup_artifacts.id", ondelete="CASCADE"), primary_key=True)
    testcase_id = Column(String, ForeignKey("testcases.id", ondelete="CASCADE"), primary_key=True)

class CleanupArtifactAsset(Base):
    __tablename__ = "cleanup_artifact_assets"
    
    cleanup_artifact_id = Column(String, ForeignKey("cleanup_artifacts.id", ondelete="CASCADE"), primary_key=True)
    asset_id = Column(String, ForeignKey("assets.id", ondelete="CASCADE"), primary_key=True)

class TestCaseAsset(Base):
    __tablename__ = "testcase_assets"

    testcase_id = Column(String, ForeignKey("testcases.id", ondelete="CASCADE"), primary_key=True)
    asset_id = Column(String, ForeignKey("assets.id", ondelete="CASCADE"), primary_key=True)
    port_ids = Column(Text, nullable=True)  # JSON array of port IDs

    @property
    def parsed_port_ids(self) -> list[str] | None:
        """Parse port_ids JSON string into a list, returning None on failure."""
        if not self.port_ids:
            return None
        try:
            return json.loads(self.port_ids)
        except (json.JSONDecodeError, TypeError):
            return None

class NoteAsset(Base):
    __tablename__ = "note_assets"

    note_id = Column(String, ForeignKey("notes.id", ondelete="CASCADE"), primary_key=True)
    asset_id = Column(String, ForeignKey("assets.id", ondelete="CASCADE"), primary_key=True)

class NoteTestCase(Base):
    __tablename__ = "note_testcases"

    note_id = Column(String, ForeignKey("notes.id", ondelete="CASCADE"), primary_key=True)
    testcase_id = Column(String, ForeignKey("testcases.id", ondelete="CASCADE"), primary_key=True)

class NoteFinding(Base):
    __tablename__ = "note_findings"

    note_id = Column(String, ForeignKey("notes.id", ondelete="CASCADE"), primary_key=True)
    finding_id = Column(String, ForeignKey("findings.id", ondelete="CASCADE"), primary_key=True)

class NoteVaultItem(Base):
    __tablename__ = "note_vault_items"

    note_id = Column(String, ForeignKey("notes.id", ondelete="CASCADE"), primary_key=True)
    vault_item_id = Column(String, ForeignKey("vault_items.id", ondelete="CASCADE"), primary_key=True)

class NoteCleanupArtifact(Base):
    __tablename__ = "note_cleanup_artifacts"

    note_id = Column(String, ForeignKey("notes.id", ondelete="CASCADE"), primary_key=True)
    cleanup_artifact_id = Column(String, ForeignKey("cleanup_artifacts.id", ondelete="CASCADE"), primary_key=True)

class IntelItemFinding(Base):
    __tablename__ = "intel_item_findings"

    intel_item_id = Column(String, ForeignKey("intel_items.id", ondelete="CASCADE"), primary_key=True)
    finding_id = Column(String, ForeignKey("findings.id", ondelete="CASCADE"), primary_key=True)

class IntelItemTestCase(Base):
    __tablename__ = "intel_item_testcases"

    intel_item_id = Column(String, ForeignKey("intel_items.id", ondelete="CASCADE"), primary_key=True)
    testcase_id = Column(String, ForeignKey("testcases.id", ondelete="CASCADE"), primary_key=True)

class IntelItemNote(Base):
    __tablename__ = "intel_item_notes"

    intel_item_id = Column(String, ForeignKey("intel_items.id", ondelete="CASCADE"), primary_key=True)
    note_id = Column(String, ForeignKey("notes.id", ondelete="CASCADE"), primary_key=True)

class InfraItemFinding(Base):
    __tablename__ = "infra_item_findings"

    infra_item_id = Column(String, ForeignKey("infra_items.id", ondelete="CASCADE"), primary_key=True)
    finding_id = Column(String, ForeignKey("findings.id", ondelete="CASCADE"), primary_key=True)

class InfraItemTestCase(Base):
    __tablename__ = "infra_item_testcases"

    infra_item_id = Column(String, ForeignKey("infra_items.id", ondelete="CASCADE"), primary_key=True)
    testcase_id = Column(String, ForeignKey("testcases.id", ondelete="CASCADE"), primary_key=True)

class InfraItemNote(Base):
    __tablename__ = "infra_item_notes"

    infra_item_id = Column(String, ForeignKey("infra_items.id", ondelete="CASCADE"), primary_key=True)
    note_id = Column(String, ForeignKey("notes.id", ondelete="CASCADE"), primary_key=True)


class InfraVaultAccess(Base):
    """Per-infra-item vault access grant. Admins/Team Leads bypass this.

    can_manage=True is the per-grant marker for "this grantee may
    grant/revoke ACL rows on this item." A grantee with can_manage=False
    can use the vault content (depending on their global INFRA_VAULT_*
    permissions) but cannot onboard or remove other users. This avoids
    the "every grantee is a granter" trap (GHSA-58q3-f33p-w84m).
    """
    __tablename__ = "infra_vault_access"

    infra_item_id = Column(String, ForeignKey("infra_items.id", ondelete="CASCADE"), primary_key=True)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    granted_by = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    granted_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    can_manage = Column(Boolean, default=False, server_default="false", nullable=False)


class FindingAttackTechnique(Base):
    """M2M: maps a Finding to one or more MITRE ATT&CK technique IDs.

    The technique_id is a plain string (e.g. "T1059.001") — not a FK to a
    techniques table. The frontend resolves IDs to names/descriptions via
    a static ATT&CK dataset (~100 KB). This avoids needing a DB table of
    600+ techniques that would require periodic migrations.
    """
    __tablename__ = "finding_attack_techniques"

    finding_id = Column(String, ForeignKey("findings.id", ondelete="CASCADE"), primary_key=True)
    technique_id = Column(String(20), primary_key=True)  # e.g. "T1059.001"
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class TestCaseAttackTechnique(Base):
    """M2M: maps a TestCase to one or more MITRE ATT&CK technique IDs.

    Mirrors FindingAttackTechnique — same ID-as-string convention, same
    rationale (no static technique table in the DB).
    """
    __tablename__ = "testcase_attack_techniques"

    testcase_id = Column(String, ForeignKey("testcases.id", ondelete="CASCADE"), primary_key=True)
    technique_id = Column(String(20), primary_key=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
