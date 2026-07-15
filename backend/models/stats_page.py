"""
Stats Page model — a globally-shared, tabbed stats view.

Unlike the dashboard (each user has a private ``User.dashboard_layout``),
a stats page owns ONE shared layout that every viewer sees; only users
with ``MANAGE_STATS_PAGES`` can edit it. The widgets themselves are the
same global ``DashboardWidget`` definitions the dashboard uses — the
``layout`` JSON holds ``{widget_id, x, y, w, h}`` entries, so there is no
separate page↔widget membership table (the layout IS the membership,
same as the dashboard).
"""

from sqlalchemy import Column, String, Boolean, Integer, JSON
from database import Base, AuditMixin
import uuid


class StatsPage(Base, AuditMixin):
    __tablename__ = "stats_pages"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(120), nullable=False)
    icon = Column(String(50), nullable=True)          # lucide icon name
    position = Column(Integer, nullable=False, default=0)  # tab order, ascending
    # Shared layout: list of {widget_id, x, y, w, h}. Page-owned, not
    # per-user — an editor's change is what every viewer sees.
    layout = Column(JSON, nullable=False, default=list)
    is_system = Column(Boolean, nullable=False, default=False)  # seeded, undeletable
    is_active = Column(Boolean, nullable=False, default=True)
