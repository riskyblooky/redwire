"""
RedWire Demo Seed Script — Meridian Financial Red Team Operation
================================================================
Creates a rich, realistic red-team engagement that walks the full attack
narrative (external recon → foothold → privilege escalation → domain
dominance): findings with CVSS scores, assets with port data, a test-case
tree, cleanup artifacts, engagement phases, and notes.

Unlike the old direct-DB seeder, this drives the **REST API** so every create
flows through the normal handlers — which means the **activity log / feed** is
populated exactly as if a real operator had entered the data. It authenticates
by minting a short-lived JWT for an existing ADMIN user (no password needed);
all writes then go through the API layer.

Run with:
    docker exec redwire-backend python seed_demo.py

Options (env):
    SEED_API_URL   Base API URL (default http://localhost:8000)
    SEED_FORCE=1   Create even if an engagement with the same name exists

Idempotent by default: skips if an engagement with the same name already exists.

Data lives in the sibling ``seed_demo_data.json`` (extracted from the original
Meridian engagement) so the narrative can be edited without touching this logic.
"""
import asyncio
import json
import os
from datetime import datetime, timedelta
from pathlib import Path

import httpx
from sqlalchemy import select

from database import AsyncSessionLocal
from models.user import User, UserRole
from auth.jwt import create_access_token

API_URL = os.getenv("SEED_API_URL", "http://localhost:8000").rstrip("/")
FORCE = os.getenv("SEED_FORCE", "").lower() in ("1", "true", "yes")
DATA_FILE = Path(os.getenv("SEED_DATA_FILE") or (Path(__file__).resolve().parent / "seed_demo_data.json"))

# Re-anchor the (fixed) exported dates so the demo always looks current:
# the engagement starts ~20 days before "now" and every other date shifts with it.
START_OFFSET_DAYS = 20


def _iso(dt: datetime) -> str:
    return dt.isoformat()


async def _get_admin_token() -> tuple[str, str]:
    """Mint an access token for any ADMIN user (open a short DB session only for this)."""
    async with AsyncSessionLocal() as db:
        admin = (
            await db.execute(select(User).where(User.role == UserRole.ADMIN).limit(1))
        ).scalar_one_or_none()
        if not admin:
            raise SystemExit("No ADMIN user found — seed the platform first.")
        return create_access_token({"sub": admin.id}), (admin.username or admin.email)


def _date_shift(data: dict):
    """Compute a timedelta that maps the exported engagement start to (now - START_OFFSET_DAYS)."""
    orig_start = datetime.fromisoformat(data["engagement"]["start_date"])
    target_start = datetime.utcnow() - timedelta(days=START_OFFSET_DAYS)
    return target_start - orig_start


def _shift(iso_str, delta):
    if not iso_str:
        return None
    return _iso(datetime.fromisoformat(iso_str) + delta)


async def seed():
    data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    eng_data = data["engagement"]
    name = eng_data["name"]
    delta = _date_shift(data)

    token, who = await _get_admin_token()
    headers = {"Authorization": f"Bearer {token}"}

    async with httpx.AsyncClient(base_url=API_URL, headers=headers, timeout=30.0) as api:
        # ── Idempotency guard ──────────────────────────────────────────
        existing = (await api.get("/engagements", params={"q": name, "limit": 50})).json()
        rows = existing if isinstance(existing, list) else existing.get("items", [])
        if any(e.get("name") == name for e in rows) and not FORCE:
            print(f"⚠️  Engagement '{name}' already exists — skipping. (SEED_FORCE=1 to override)")
            return

        print(f"Seeding as: {who}  →  {API_URL}")

        # ── 1. Engagement ──────────────────────────────────────────────
        eng_payload = {
            "name": name,
            "client_name": eng_data["client_name"],
            "engagement_type": eng_data["engagement_type"],
            "status": eng_data["status"],
            "description": eng_data.get("description"),
            "scope": eng_data.get("scope"),
            "objectives": eng_data.get("objectives"),
            "start_date": _shift(eng_data["start_date"], delta),
            "end_date": _shift(eng_data.get("end_date"), delta),
        }
        r = await api.post("/engagements", json=eng_payload)
        r.raise_for_status()
        eng = r.json()
        eid = eng["id"]
        print(f"✓ Engagement created: {eid}")

        # ── 2. Phase dates (phases auto-created on engagement create) ──
        phases = (await api.get(f"/engagements/{eid}/phases")).json()
        by_name = {p["phase_name"]: p for p in phases}
        phase_updates = []
        for p in data["phases"]:
            match = by_name.get(p["phase_name"])
            if match:
                phase_updates.append({
                    "id": match["id"],
                    "planned_start": _shift(p.get("planned_start"), delta),
                    "planned_end": _shift(p.get("planned_end"), delta),
                })
        if phase_updates:
            await api.put(f"/engagements/{eid}/phases", json=phase_updates)
        print(f"✓ {len(phase_updates)} phase date ranges set")

        # ── 3. Assets (+ ports) ────────────────────────────────────────
        asset_ids: dict[str, str] = {}
        port_count = 0
        for a in data["assets"]:
            r = await api.post("/assets", json={
                "engagement_id": eid,
                "name": a["name"],
                "asset_type": a["asset_type"],
                "identifier": a["identifier"],
                "description": a.get("description"),
                "notes": a.get("notes"),
                "in_scope": a.get("in_scope", True),
                "is_scanned": a.get("is_scanned", False),
                "is_pwned": a.get("is_pwned", False),
            })
            r.raise_for_status()
            aid = r.json()["id"]
            asset_ids[a["name"]] = aid
            for port in a.get("ports", []):
                pr = await api.post(f"/assets/{aid}/ports", json={
                    "port_number": port["port_number"],
                    "protocol": port.get("protocol", "TCP"),
                    "state": port.get("state", "OPEN"),
                    "service_name": port.get("service_name"),
                    "version": port.get("version"),
                })
                if pr.status_code < 300:
                    port_count += 1
        print(f"✓ {len(asset_ids)} assets, {port_count} ports")

        # ── 4. Findings (create → set status; link assets by name) ─────
        for f in data["findings"]:
            link_ids = [asset_ids[n] for n in f.get("asset_names", []) if n in asset_ids]
            r = await api.post("/findings", json={
                "engagement_id": eid,
                "title": f["title"],
                "category": f.get("category"),
                "description": f["description"],
                "severity": f["severity"],
                "impact": f.get("impact"),
                "technical_details": f.get("technical_details"),
                "steps_to_reproduce": f.get("steps_to_reproduce"),
                "mitigations": f.get("mitigations"),
                "references": f.get("references"),
                "cvss_score": f.get("cvss_score"),
                "cvss_vector": f.get("cvss_vector"),
                "asset_ids": link_ids,
            })
            r.raise_for_status()
            fid = r.json()["id"]
            # Findings are always created OPEN; move to the real status via update.
            if f.get("status") and f["status"] != "OPEN":
                await api.put(f"/findings/{fid}", json={"status": f["status"]})
        print(f"✓ {len(data['findings'])} findings")

        # ── 5. Test cases (tree: parents before children; link assets) ─
        tc_id_map: dict[str, str] = {}   # original export id -> new id
        pending = list(data["testcases"])
        created = 0
        # Iterate until every node whose parent is resolved has been created.
        while pending:
            progressed = False
            still: list[dict] = []
            for t in pending:
                parent_orig = t.get("parent_id")
                if parent_orig and parent_orig not in tc_id_map:
                    still.append(t)     # parent not created yet
                    continue
                payload = {
                    "engagement_id": eid,
                    "title": t["title"],
                    "category": t["category"],
                    "description": t["description"],
                    "steps": t.get("steps"),
                    "expected_result": t.get("expected_result"),
                    "actual_result": t.get("actual_result"),
                    "is_executed": bool(t.get("is_executed")),
                    "is_successful": t.get("is_successful"),
                    "notes": t.get("notes"),
                }
                if parent_orig:
                    payload["parent_id"] = tc_id_map[parent_orig]
                r = await api.post("/testcases", json=payload)
                r.raise_for_status()
                new_id = r.json()["id"]
                tc_id_map[t["id"]] = new_id
                created += 1
                progressed = True
                for n in t.get("asset_names", []):
                    if n in asset_ids:
                        await api.post(f"/testcases/{new_id}/assets/{asset_ids[n]}")
            pending = still
            if not progressed:
                # Orphaned parents (shouldn't happen) — create the rest as roots.
                for t in pending:
                    r = await api.post("/testcases", json={
                        "engagement_id": eid, "title": t["title"], "category": t["category"],
                        "description": t["description"], "steps": t.get("steps"),
                        "expected_result": t.get("expected_result"),
                        "actual_result": t.get("actual_result"),
                        "is_executed": bool(t.get("is_executed")),
                        "is_successful": t.get("is_successful"), "notes": t.get("notes"),
                    })
                    if r.status_code < 300:
                        created += 1
                break
        print(f"✓ {created} test cases")

        # ── 6. Notes ───────────────────────────────────────────────────
        for n in data["notes"]:
            await api.post(f"/engagements/{eid}/notes", json={
                "title": n["title"], "content": n.get("content", ""),
            })
        print(f"✓ {len(data['notes'])} notes")

        # ── 7. Cleanup artifacts ───────────────────────────────────────
        for c in data["cleanup"]:
            await api.post("/cleanup-artifacts", json={
                "engagement_id": eid,
                "title": c["title"],
                "artifact_type": c["artifact_type"],
                "status": c.get("status", "PENDING"),
                "location": c.get("location"),
                "description": c.get("description"),
                "cleanup_notes": c.get("cleanup_notes"),
            })
        print(f"✓ {len(data['cleanup'])} cleanup artifacts")

        print("\n" + "=" * 60)
        print("🚀  MERIDIAN DEMO SEED COMPLETE (via API — activity log populated)")
        print("=" * 60)
        print(f"  Engagement: {name}")
        print(f"  URL:        /engagements/{eid}")
        print("=" * 60)


if __name__ == "__main__":
    asyncio.run(seed())
