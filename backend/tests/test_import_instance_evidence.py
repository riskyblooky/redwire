"""A scanner finding seen on several hosts is merged into one finding; the
per-host evidence (port / location and the scanner's output) survives the
merge in the finding's technical details."""

from __future__ import annotations

from sqlalchemy import select

from tests.test_authz_boundaries import _make_engagement
from tests.test_parsers import _BURP_XML, _b
from tests.test_review_imports import _nuclei

_NESSUS = """<?xml version="1.0"?>
<NessusClientData_v2><Report name="r">
  <ReportHost name="10.9.0.1"><HostProperties><tag name="host-ip">10.9.0.1</tag></HostProperties>
    <ReportItem port="445" protocol="tcp" svc_name="cifs" pluginID="777" pluginName="Weak Thing" severity="2">
      <risk_factor>Medium</risk_factor><description>d</description>
      <plugin_output>first host says ALPHA</plugin_output>
    </ReportItem>
  </ReportHost>
  <ReportHost name="10.9.0.2"><HostProperties><tag name="host-ip">10.9.0.2</tag></HostProperties>
    <ReportItem port="8443" protocol="tcp" svc_name="www" pluginID="777" pluginName="Weak Thing" severity="2">
      <risk_factor>Medium</risk_factor><description>d</description>
      <plugin_output>second host says BRAVO</plugin_output>
    </ReportItem>
  </ReportHost>
</Report></NessusClientData_v2>"""


def test_parsers_keep_every_instance():
    from utils.parsers import burp as burp_parser, nessus as nessus_parser
    f = nessus_parser.parse(_NESSUS.encode()).findings
    assert len(f) == 1 and len(f[0].affected_asset_indices) == 2
    assert [(i.location, i.detail) for i in f[0].instances] == [
        ("445/tcp (cifs)", "first host says ALPHA"), ("8443/tcp (www)", "second host says BRAVO")]

    xss = [x for x in burp_parser.parse(_b(_BURP_XML)).findings if x.title.startswith("Cross-site")][0]
    assert [i.location for i in xss.instances] == ["/search parameter q", "/q"]


async def test_import_writes_per_host_evidence(client, db_session, make_user, authenticate_as):
    from models.finding import Finding
    eng = await _make_engagement(db_session)
    authenticate_as(await make_user(role="admin"))
    r = await client.post("/imports/commit", data={"engagement_id": eng.id},
                          files={"file": ("s.nessus", _NESSUS.encode(), "application/xml")})
    assert r.status_code == 200, r.text
    td = (await db_session.execute(select(Finding.technical_details)
                                   .where(Finding.engagement_id == eng.id))).scalar_one()
    for part in ("`10.9.0.1` — `445/tcp (cifs)`", "first host says ALPHA",
                 "`10.9.0.2` — `8443/tcp (www)`", "second host says BRAVO"):
        assert part in td


async def test_reimport_adds_evidence_for_new_hosts(client, db_session, make_user, authenticate_as):
    from models.finding import Finding
    eng = await _make_engagement(db_session)
    authenticate_as(await make_user(role="admin"))
    post = lambda body: client.post("/imports/commit", data={"engagement_id": eng.id},
                                    files={"file": ("n.jsonl", body, "application/json")})
    assert (await post(_nuclei("10.8.8.1"))).status_code == 200
    assert (await post(_nuclei("10.8.8.1", "10.8.8.2"))).status_code == 200
    td = (await db_session.execute(select(Finding.technical_details)
                                   .where(Finding.engagement_id == eng.id))).scalar_one()
    assert td.count("10.8.8.1:8080/admin") == 1   # not repeated on re-import
    assert "http://10.8.8.2:8080/admin" in td
