from sqlalchemy import Column, String, Integer, Float, Text, ForeignKey
from database import Base, AuditMixin
import uuid


class ScanImport(Base, AuditMixin):
    """A record of a scanner-output import (nmap, nessus, burp, nuclei, …).

    Captures the scan's provenance — the exact command line and scanner
    metadata — alongside what the import produced, so operators can revisit the
    scans menu and see which command generated the assets/findings, when it ran,
    and how much it touched. AuditMixin supplies created_by / created_at.
    """
    __tablename__ = "scan_imports"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    engagement_id = Column(
        String, ForeignKey("engagements.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )

    source_tool = Column(String(50), nullable=False)     # nmap | nessus | burp | nuclei
    source_format = Column(String(50), nullable=True)
    filename = Column(String(255), nullable=True)

    # Scan provenance, as reported by the scanner output.
    command = Column(Text, nullable=True)                # e.g. the nmap args line
    scanner = Column(String(120), nullable=True)
    scanner_version = Column(String(60), nullable=True)
    started_at = Column(String(60), nullable=True)       # human start time, verbatim
    finished_at = Column(String(60), nullable=True)      # human finish time, verbatim
    elapsed_seconds = Column(Float, nullable=True)
    summary = Column(Text, nullable=True)                # runstats summary line
    hosts_total = Column(Integer, nullable=True)
    hosts_up = Column(Integer, nullable=True)
    hosts_down = Column(Integer, nullable=True)

    # What the import produced.
    assets_created = Column(Integer, default=0)
    assets_merged = Column(Integer, default=0)
    findings_created = Column(Integer, default=0)
    ports_added = Column(Integer, default=0)
