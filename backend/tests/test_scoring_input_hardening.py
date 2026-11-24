"""Malformed scoring inputs are a 422, never a 500 or a stored NaN /
out-of-range score."""

from __future__ import annotations

import pytest

DREAD_OK = {"D": 5, "R": 5, "E": 5, "A": 5, "Di": 5}
CVSS_OK = {"AV": "N", "AC": "L", "PR": "N", "UI": "N", "S": "U", "C": "H", "I": "H", "A": "H"}


@pytest.mark.parametrize("model,inputs", [
    ("cvss31", {**CVSS_OK, "AV": ["N"]}),        # unhashable → was TypeError / 500
    ("cvss31", {**CVSS_OK, "S": {"x": 1}}),
    ("cvss31", {**CVSS_OK, "C": 1}),
    ("dread", {**DREAD_OK, "D": "nan"}),
    ("dread", {**DREAD_OK, "D": "inf"}),
    ("dread", {**DREAD_OK, "D": True}),
    ("dread", {**DREAD_OK, "D": 1e9}),           # declared max is 10
    ("dread", {**DREAD_OK, "D": -3}),
    ("dread", {**DREAD_OK, "D": [5]}),
])
async def test_bad_inputs_are_422(client, make_user, authenticate_as, model, inputs):
    authenticate_as(await make_user(role="operator"))
    r = await client.post("/scoring/evaluate", json={"model_id": model, "inputs": inputs})
    assert r.status_code == 422, (r.status_code, r.text)


async def test_good_inputs_still_score(client, make_user, authenticate_as):
    authenticate_as(await make_user(role="operator"))
    r = await client.post("/scoring/evaluate", json={"model_id": "dread", "inputs": {**DREAD_OK, "D": "7"}})
    assert r.status_code == 200, r.text
    r = await client.post("/scoring/evaluate", json={"model_id": "cvss31", "inputs": CVSS_OK})
    assert r.status_code == 200 and r.json()["score"] == 9.8, r.text
