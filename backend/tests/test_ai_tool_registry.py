"""Every AI tool in utils/ai_tool_registry.py matches the API it calls.

The MCP and in-app catalogs used to be hand-kept copies that drifted: write
tools that always 422'd, stats tools pointing at routes that don't exist,
an advertised in-app tool with no executor, enums that matched nothing.
"""

from __future__ import annotations

import enum
import re

import pytest
from fastapi.routing import APIRoute

from main import app
from utils.ai_tool_registry import TOOLS, BY_NAME, mcp_catalog, openai_tools

_ROUTES = {(m, r.path): r for r in app.routes if isinstance(r, APIRoute) for m in r.methods}
_HTTP_TOOLS = [t for t in TOOLS if t.method]


def _route(method, path):
    r = _ROUTES.get((method, path))
    assert r is not None, f"no {method} {path} route"
    return r


def _body_model(route):
    params = route.dependant.body_params
    if not params:
        return None
    assert len(params) == 1, f"{route.path}: multiple body params"
    return params[0].type_ if hasattr(params[0], "type_") else params[0].field_info.annotation


def _query_names(route):
    return {p.alias or p.name for p in route.dependant.query_params}


def _path_args(path):
    return set(re.findall(r"{(\w+)}", path))


def test_names_unique_and_catalogs_built():
    assert len(BY_NAME) == len(TOOLS)
    assert {t["name"] for t in mcp_catalog()} == {t.name for t in TOOLS if t.mcp}
    assert {t["function"]["name"] for t in openai_tools()} == {t.name for t in TOOLS if t.in_app}


@pytest.mark.parametrize("spec", _HTTP_TOOLS, ids=lambda s: s.name)
def test_route_exists_and_arguments_fit(spec):
    route = _route(spec.method, spec.path)
    props = spec.input_schema.get("properties", {})
    required = set(spec.input_schema.get("required", []))

    # Path placeholders are required arguments and match the route's.
    path_args = _path_args(spec.path)
    assert path_args <= required, f"path args {path_args - required} not required"
    assert {p.name for p in route.dependant.path_params} == path_args

    # Query arguments are real query parameters of the endpoint.
    qnames = _query_names(route)
    query_args = set(props) if spec.query == "*" else set(spec.query)
    for arg in query_args:
        assert arg in props, f"query arg {arg!r} not in the schema"
        assert spec.query_rename.get(arg, arg) in qnames, f"{arg!r} isn't a query param of {spec.path}"

    for arg in spec.scope_args:
        assert arg in props and arg not in query_args and arg not in path_args, arg

    model = _body_model(route)
    if spec.method in ("POST", "PUT", "PATCH"):
        body_args = (set(props) - path_args - query_args - set(spec.scope_args)) | set(spec.body_keeps)
        assert model is not None, f"{spec.path} takes no body"
        fields = model.model_fields
        assert body_args <= set(fields), f"not in {model.__name__}: {body_args - set(fields)}"
        # Whatever the endpoint requires, the tool requires too.
        must = {n for n, f in fields.items() if f.is_required()}
        assert must <= required, f"{model.__name__} requires {must - required}"
        # Enums the schema advertises are the model's.
        for name in body_args:
            ann = fields[name].annotation
            inner = [a for a in getattr(ann, "__args__", (ann,)) if isinstance(a, type) and issubclass(a, enum.Enum)]
            if inner and "enum" in props[name]:
                assert set(props[name]["enum"]) == {e.value for e in inner[0]}, name


@pytest.mark.parametrize("spec", [t for t in TOOLS if t.handler], ids=lambda s: s.name)
def test_handler_routes_exist(spec):
    assert spec.calls
    for method, path in spec.calls:
        _route(method, path)


@pytest.mark.parametrize("spec", TOOLS, ids=lambda s: s.name)
def test_write_classification_matches_method(spec):
    # The MCP write-tool gate goes by name prefix: a writing method must
    # carry one, and a read tool must not.
    if spec.method:
        assert spec.is_write == (spec.method != "GET"), spec.name
    for f in spec.taxonomy:
        assert f in spec.input_schema["properties"], f


@pytest.mark.parametrize("spec", [t for t in TOOLS if t.in_app], ids=lambda s: s.name)
async def test_in_app_tool_has_an_executor(spec, db_session, make_user):
    """Each in-app tool reaches a handler in routers.ai._execute_mcp_tool
    (a missing one answers "Unknown tool")."""
    from fastapi import HTTPException
    from routers.ai import _execute_mcp_tool
    from tests.test_authz_boundaries import _make_engagement
    eng = await _make_engagement(db_session)
    admin = await make_user(role="admin")
    args = {}
    for name in spec.input_schema.get("required", []):
        if name == "engagement_id":
            args[name] = eng.id
        elif name.endswith("_id"):
            args[name] = "00000000-0000-0000-0000-000000000000"
        else:
            schema = spec.input_schema["properties"][name]
            args[name] = schema.get("enum", ["x"])[0]
    try:
        await _execute_mcp_tool(spec.name, args, admin, db_session)
    except HTTPException as exc:
        assert "Unknown tool" not in str(exc.detail), spec.name
    except ValueError:
        pass  # a handler ran and rejected the dummy input
