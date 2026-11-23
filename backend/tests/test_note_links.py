"""Note link/unlink follow the note-edit ownership rule, and a unique
violation that slips past an existence check is a 409, not a 500."""

from __future__ import annotations

import uuid

from tests.test_authz_boundaries import _assign, _make_engagement, _make_engagement_role, _make_finding


async def test_links_need_edit_any_on_someone_elses_note(client, db_session, make_user, authenticate_as):
    from models.note import Note
    eng = await _make_engagement(db_session)
    finding = await _make_finding(db_session, eng)
    author, other = await make_user(), await make_user()
    role = await _make_engagement_role(db_session, ["engagement_view", "note_view", "note_edit", "finding_view"])
    for u in (author, other):
        await _assign(db_session, u, eng, role)
    note = Note(id=str(uuid.uuid4()), engagement_id=eng.id, title="n", content="c", created_by=author.id)
    db_session.add(note)
    await db_session.flush()
    authenticate_as(other)
    assert (await client.post(f"/notes/{note.id}/findings/{finding.id}")).status_code == 403
    authenticate_as(author)
    assert (await client.post(f"/notes/{note.id}/findings/{finding.id}")).status_code == 204
    assert (await client.post(f"/notes/{note.id}/findings/{finding.id}")).status_code == 409
    authenticate_as(other)
    assert (await client.delete(f"/notes/{note.id}/findings/{finding.id}")).status_code == 403


async def test_unlisted_unique_violation_is_409():
    import main
    from sqlalchemy.exc import IntegrityError

    class Orig(Exception):
        pass

    exc = IntegrityError("INSERT ...", {}, Orig('duplicate key value violates unique constraint "note_findings_pkey"'))
    r = await main._integrity_conflict(None, exc)
    assert r.status_code == 409


async def test_note_link_map_needs_note_view(client, db_session, make_user, authenticate_as):
    """The linked-notes map carries note titles, so it follows the notes
    list's note_view rule; a member without it gets empty maps (their
    tables still load, just without note tooltips)."""
    from models.associations import NoteFinding
    from models.note import Note
    eng = await _make_engagement(db_session)
    finding = await _make_finding(db_session, eng)
    note = Note(id=str(uuid.uuid4()), engagement_id=eng.id, title="ZZsecret note title", content="c")
    db_session.add(note)
    await db_session.flush()
    db_session.add(NoteFinding(note_id=note.id, finding_id=finding.id))
    await db_session.flush()

    reader, blind = await make_user(), await make_user()
    await _assign(db_session, reader, eng, await _make_engagement_role(db_session, ["engagement_view", "note_view"]))
    await _assign(db_session, blind, eng, await _make_engagement_role(db_session, ["engagement_view", "finding_view"]))

    authenticate_as(reader)
    r = await client.get(f"/engagements/{eng.id}/note-links")
    assert r.status_code == 200
    assert r.json()["finding"][finding.id] == [{"id": note.id, "title": "ZZsecret note title"}]

    authenticate_as(blind)
    r = await client.get(f"/engagements/{eng.id}/note-links")
    assert r.status_code == 200
    assert "ZZsecret" not in r.text
    assert all(v == {} for v in r.json().values())
