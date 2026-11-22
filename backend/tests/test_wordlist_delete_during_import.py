"""A wordlist deleted while its import runs: the import stops after the
batch in flight and removes the entries it inserted, instead of carrying
on and leaving a partial list under a deleted wordlist."""

from __future__ import annotations

import sqlalchemy
import sqlalchemy.orm

from routers import wordlist as wl


class _Query:
    def __init__(self, sess, model):
        self.sess, self.model = sess, model

    def filter(self, *a):
        return self

    def first(self):
        return None if self.sess.meta_deleted else object()

    def delete(self, **kw):
        self.sess.deleted_entries = True
        return 0


class _Session:
    def __init__(self, *a, **kw):
        self.commits = 0
        self.meta_deleted = False
        self.deleted_entries = False
        _Session.last = self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def add_all(self, rows):
        self.inserted = getattr(self, "inserted", 0) + len(rows)

    def commit(self):
        self.commits += 1
        self.meta_deleted = True          # an admin deletes it right after batch 1

    def query(self, model):
        return _Query(self, model)


class _Engine:
    def dispose(self):
        pass


def test_import_stops_and_cleans_up(tmp_path, monkeypatch):
    f = tmp_path / "words.txt"
    f.write_text("\n".join(f"pw{i}" for i in range(25)))
    monkeypatch.setattr(sqlalchemy, "create_engine", lambda *a, **kw: _Engine())
    monkeypatch.setattr(sqlalchemy.orm, "Session", _Session)
    added = []
    monkeypatch.setattr(wl.bloom_service, "add_many", lambda pws: added.extend(pws))
    monkeypatch.setattr(wl, "compute_all_hashes", lambda p: {"ntlm": "", "md5": "", "sha1": ""})
    monkeypatch.setattr(wl, "ensure_within", lambda *a: False)

    # batch_size is a local (10000); a 25-line file is one final batch.
    wl._process_wordlist_sync(str(f), "meta-1")
    s = _Session.last
    assert s.deleted_entries                    # its rows removed
    assert added == []                          # not added to the Bloom filter
