"""The one list of AI tools: the MCP server's catalog and the in-app chat's.

Both used to keep their own hand-written list. They drifted from each other
and from the API (MCP write tools that always 422'd, stats tools calling
routes that don't exist, an in-app ``list_notes`` that was advertised but
never dispatched, a status enum that matched nothing).

Each ``ToolSpec`` says what the model sees (name, description, JSON schema)
and how the call reaches the API:

- ``method`` + ``path``: the REST route. ``{arg}`` placeholders in the path
  are filled from the arguments.
- ``query``: arguments sent as query parameters (``"*"`` = all of them),
  ``query_rename`` maps an argument name to its parameter name.
- Every other argument goes in the JSON body for POST/PUT/PATCH;
  ``body_keeps`` are query arguments that also stay in the body. GET and
  DELETE ignore arguments not in the path or query.
- ``scope_args``: arguments the model passes as scope confirmation (the
  engagement a row belongs to) that the API doesn't take; never sent.
- ``handler``: a named special case in the MCP server (composite stats,
  ``ai_chat``); ``calls`` lists the routes it uses so the test can check them.
- ``redact_vault_secrets``: strip username/password/note before the model
  sees the result (GHSA-q4x9-5gmc-fxh5 b1).
- ``taxonomy``: fields whose legal values come from the configurable-types
  taxonomy at call time instead of a fixed enum.
- ``mcp`` / ``in_app``: which catalogs carry the tool. In-app tools run
  through ``routers.ai._execute_mcp_tool`` (direct DB queries).

The MCP server reads this list from ``GET /ai/tool-registry``.
``tests/test_ai_tool_registry.py`` checks every entry against the real
routes and request schemas.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Optional, Union

from models.engagement import EngagementStatus

WRITE_PREFIXES = ("create_", "update_", "delete_")


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: dict
    method: Optional[str] = None
    path: Optional[str] = None
    query: Union[tuple, str] = ()
    query_rename: dict = field(default_factory=dict)
    body_keeps: tuple = ()
    scope_args: tuple = ()
    handler: Optional[str] = None
    calls: tuple = ()
    redact_vault_secrets: bool = False
    taxonomy: dict = field(default_factory=dict)
    mcp: bool = True
    in_app: bool = False

    @property
    def is_write(self) -> bool:
        return self.name.startswith(WRITE_PREFIXES)


TOOLS: list[ToolSpec] = [
    ToolSpec(
        name='get_field_examples',
        description="Fetch a few real examples of ONE field's text from other records of the same type — e.g. how the 'description' field reads across other findings — to match the house style, tone, depth and format when writing that field. Call this when the user asks to write a field 'like our other findings' (or other records). Returns ONLY that single field from each example, never a whole record.",
        input_schema={'type': 'object',
                      'properties': {'resource_type': {'type': 'string',
                                                       'enum': ['finding', 'testcase', 'engagement', 'asset'],
                                                       'description': 'The record type to pull examples from (the type '
                                                                      'you are editing).'},
                                     'field_name': {'type': 'string',
                                                    'description': "The field to pull examples of, e.g. 'description', "
                                                                   "'impact', 'mitigations', 'steps_to_reproduce'."},
                                     'limit': {'type': 'integer',
                                               'description': 'How many examples to return (1-5, default 3).'}},
                      'required': ['resource_type', 'field_name']},
        mcp=False,
        in_app=True,
    ),
    ToolSpec(
        name='list_engagements',
        description='List all penetration test engagements. Optionally filter by status. Valid statuses: PROPOSED, SCOPING, PLANNING, IN_PROGRESS, REPORTING, COMPLETED, ON_HOLD.',
        input_schema={'type': 'object',
                      'properties': {'status': {'type': 'string',
                                                'description': 'Filter by engagement status. Must be one of: PROPOSED, '
                                                               'SCOPING, PLANNING, IN_PROGRESS, REPORTING, COMPLETED, '
                                                               'ON_HOLD.',
                                                'enum': ['PROPOSED',
                                                         'SCOPING',
                                                         'PLANNING',
                                                         'IN_PROGRESS',
                                                         'REPORTING',
                                                         'COMPLETED',
                                                         'ON_HOLD']}}},
        method='GET',
        path='/engagements',
        query=('status',),
        in_app=True,
    ),
    ToolSpec(
        name='get_engagement',
        description='Get detailed information about a specific engagement by its ID.',
        input_schema={'type': 'object',
                      'properties': {'engagement_id': {'type': 'string', 'description': 'The engagement UUID'}},
                      'required': ['engagement_id']},
        method='GET',
        path='/engagements/{engagement_id}',
        in_app=True,
    ),
    ToolSpec(
        name='list_findings',
        description='List vulnerability findings for a specific engagement. Returns title, severity, status, and category.',
        input_schema={'type': 'object',
                      'properties': {'engagement_id': {'type': 'string', 'description': 'The engagement UUID'}},
                      'required': ['engagement_id']},
        method='GET',
        path='/findings',
        query=('engagement_id',),
        in_app=True,
    ),
    ToolSpec(
        name='get_finding',
        description='Get full details of a specific finding including description, impact, steps to reproduce, mitigations, and affected assets.',
        input_schema={'type': 'object',
                      'properties': {'finding_id': {'type': 'string', 'description': 'The finding UUID'},
                                     'engagement_id': {'type': 'string', 'description': 'The engagement UUID'}},
                      'required': ['finding_id', 'engagement_id']},
        method='GET',
        path='/findings/{finding_id}',
        in_app=True,
        scope_args=('engagement_id',),
    ),
    ToolSpec(
        name='create_finding',
        description='Create a new vulnerability finding in an engagement. Requires a title, severity and description. To rate it with a scoring model (CVSS 3.1, USAF RAC, ...), also pass score_model + score_inputs; the server then computes the severity.',
        input_schema={'type': 'object',
                      'properties': {'engagement_id': {'type': 'string', 'description': 'The engagement UUID'},
                                     'title': {'type': 'string', 'description': 'Finding title'},
                                     'severity': {'type': 'string',
                                                  'description': 'Severity level',
                                                  'enum': ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFO']},
                                     'description': {'type': 'string',
                                                     'description': 'Detailed description (markdown, required)'},
                                     'impact': {'type': 'string', 'description': 'Business/technical impact (markdown)'},
                                     'mitigations': {'type': 'string',
                                                     'description': 'Recommended remediation (markdown)'},
                                     'category': {'type': 'string', 'description': 'Finding category'},
                                     'score_model': {'type': 'string',
                                                     'description': "Optional scoring model id (e.g. 'cvss31', "
                                                                    "'usaf-rac'). Call list_scoring_models for the "
                                                                    'models this engagement permits and '
                                                                    'get_scoring_model for its metric ids and allowed '
                                                                    'values. Use together with score_inputs.'},
                                     'score_inputs': {'type': 'object',
                                                      'description': 'Metric values for score_model, keyed by metric id '
                                                                     '(e.g. {"AV": "N", "AC": "L", ...} for cvss31). '
                                                                     'When given, the server computes severity, score '
                                                                     'and vector from these and they override '
                                                                     '`severity`.'}},
                      'required': ['engagement_id', 'title', 'severity', 'description']},
        method='POST',
        path='/findings',
    ),
    ToolSpec(
        name='update_finding',
        description='Update fields on an existing finding. Only specified fields are changed.',
        input_schema={'type': 'object',
                      'properties': {'finding_id': {'type': 'string', 'description': 'The finding UUID'},
                                     'engagement_id': {'type': 'string', 'description': 'The engagement UUID'},
                                     'title': {'type': 'string', 'description': 'New title'},
                                     'severity': {'type': 'string',
                                                  'enum': ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFO']},
                                     'status': {'type': 'string',
                                                'description': 'New finding status',
                                                'enum': ['OPEN', 'IN_REVIEW', 'VERIFIED', 'REMEDIATED', 'CLOSED']},
                                     'description': {'type': 'string', 'description': 'Updated description (markdown)'},
                                     'impact': {'type': 'string', 'description': 'Updated impact (markdown)'},
                                     'mitigations': {'type': 'string', 'description': 'Updated mitigations (markdown)'},
                                     'score_model': {'type': 'string',
                                                     'description': "Optional scoring model id (e.g. 'cvss31', "
                                                                    "'usaf-rac'). Call list_scoring_models for the "
                                                                    'models this engagement permits and '
                                                                    'get_scoring_model for its metric ids and allowed '
                                                                    'values. Use together with score_inputs.'},
                                     'score_inputs': {'type': 'object',
                                                      'description': 'Metric values for score_model, keyed by metric id '
                                                                     '(e.g. {"AV": "N", "AC": "L", ...} for cvss31). '
                                                                     'When given, the server computes severity, score '
                                                                     'and vector from these and they override '
                                                                     '`severity`.'}},
                      'required': ['finding_id', 'engagement_id']},
        method='PUT',
        path='/findings/{finding_id}',
        scope_args=('engagement_id',),
    ),
    ToolSpec(
        name='list_scoring_models',
        description="List the finding scoring models permitted for an engagement (site policy combined with the engagement's own policy), the default model, and whether the model is locked. Omit engagement_id for the site-wide policy.",
        input_schema={'type': 'object',
                      'properties': {'engagement_id': {'type': 'string',
                                                       'description': 'The engagement UUID (optional)'}}},
        method='GET',
        path='/scoring/effective-policy',
        query=('engagement_id',),
    ),
    ToolSpec(
        name='get_scoring_model',
        description="Get a scoring model's definition: its metrics (ids, labels, allowed option values or numeric ranges) — the keys and values to send as score_inputs on create_finding / update_finding.",
        input_schema={'type': 'object',
                      'properties': {'model_id': {'type': 'string',
                                                  'description': 'Scoring model id from list_scoring_models (e.g. '
                                                                 "'cvss31')",
                                                  'pattern': '^[A-Za-z0-9_-]{1,64}$'}},
                      'required': ['model_id']},
        method='GET',
        path='/scoring/models/{model_id}',
    ),
    ToolSpec(
        name='list_assets',
        description='List target assets for a specific engagement. Returns hostname/IP, type, and status.',
        input_schema={'type': 'object',
                      'properties': {'engagement_id': {'type': 'string', 'description': 'The engagement UUID'}},
                      'required': ['engagement_id']},
        method='GET',
        path='/assets',
        query=('engagement_id',),
        in_app=True,
    ),
    ToolSpec(
        name='get_asset',
        description='Get full details of a specific asset including ports, linked findings, and metadata.',
        input_schema={'type': 'object',
                      'properties': {'asset_id': {'type': 'string', 'description': 'The asset UUID'},
                                     'engagement_id': {'type': 'string', 'description': 'The engagement UUID'}},
                      'required': ['asset_id', 'engagement_id']},
        method='GET',
        path='/assets/{asset_id}',
        scope_args=('engagement_id',),
    ),
    ToolSpec(
        name='create_asset',
        description='Create a new target asset in an engagement. Requires a name, asset_type and identifier.',
        input_schema={'type': 'object',
                      'properties': {'engagement_id': {'type': 'string', 'description': 'The engagement UUID'},
                                     'name': {'type': 'string', 'description': 'Asset name (hostname, IP, URL, etc.)'},
                                     'asset_type': {'type': 'string',
                                                    'description': 'Type of asset',
                                                    'enum': ['IP_ADDRESS',
                                                             'DOMAIN',
                                                             'URL',
                                                             'APPLICATION',
                                                             'SERVER',
                                                             'NETWORK',
                                                             'OTHER']},
                                     'identifier': {'type': 'string',
                                                    'description': "The asset's address: IP, hostname, URL or CIDR "
                                                                   '(required by the API)'},
                                     'description': {'type': 'string', 'description': 'Optional description'},
                                     'in_scope': {'type': 'boolean',
                                                  'description': 'Whether asset is in scope (default true)'}},
                      'required': ['engagement_id', 'name', 'asset_type', 'identifier']},
        method='POST',
        path='/assets',
        taxonomy={'asset_type': 'asset'},
    ),
    ToolSpec(
        name='update_asset',
        description='Update fields on an existing asset. Only specified fields are changed.',
        input_schema={'type': 'object',
                      'properties': {'asset_id': {'type': 'string', 'description': 'The asset UUID'},
                                     'engagement_id': {'type': 'string', 'description': 'The engagement UUID'},
                                     'name': {'type': 'string', 'description': 'Updated name'},
                                     'asset_type': {'type': 'string',
                                                    'enum': ['IP_ADDRESS',
                                                             'DOMAIN',
                                                             'URL',
                                                             'APPLICATION',
                                                             'SERVER',
                                                             'NETWORK',
                                                             'OTHER']},
                                     'description': {'type': 'string', 'description': 'Updated description'},
                                     'in_scope': {'type': 'boolean', 'description': 'Updated scope status'}},
                      'required': ['asset_id', 'engagement_id']},
        method='PUT',
        path='/assets/{asset_id}',
        taxonomy={'asset_type': 'asset'},
        scope_args=('engagement_id',),
    ),
    ToolSpec(
        name='list_testcases',
        description='List test cases for a specific engagement. Returns title, category, status, and result.',
        input_schema={'type': 'object',
                      'properties': {'engagement_id': {'type': 'string', 'description': 'The engagement UUID'}},
                      'required': ['engagement_id']},
        method='GET',
        path='/testcases',
        query=('engagement_id',),
        in_app=True,
    ),
    ToolSpec(
        name='get_testcase',
        description='Get full details of a specific test case including steps, expected result, and linked findings.',
        input_schema={'type': 'object',
                      'properties': {'testcase_id': {'type': 'string', 'description': 'The test case UUID'},
                                     'engagement_id': {'type': 'string', 'description': 'The engagement UUID'}},
                      'required': ['testcase_id', 'engagement_id']},
        method='GET',
        path='/testcases/{testcase_id}',
        scope_args=('engagement_id',),
    ),
    ToolSpec(
        name='create_testcase',
        description='Create a new test case in an engagement. Requires a title, category and description.',
        input_schema={'type': 'object',
                      'properties': {'engagement_id': {'type': 'string', 'description': 'The engagement UUID'},
                                     'title': {'type': 'string', 'description': 'Test case title'},
                                     'category': {'type': 'string',
                                                  'description': 'Category (e.g. Reconnaissance, Exploitation)'},
                                     'description': {'type': 'string', 'description': 'Detailed description (markdown)'},
                                     'steps': {'type': 'string', 'description': 'Test steps (markdown)'},
                                     'expected_result': {'type': 'string', 'description': 'Expected outcome (markdown)'},
                                     'parent_id': {'type': 'string',
                                                   'description': 'Parent test case UUID for nesting'}},
                      'required': ['engagement_id', 'title', 'category', 'description']},
        method='POST',
        path='/testcases',
    ),
    ToolSpec(
        name='update_testcase',
        description='Update fields on an existing test case. Only specified fields are changed.',
        input_schema={'type': 'object',
                      'properties': {'testcase_id': {'type': 'string', 'description': 'The test case UUID'},
                                     'engagement_id': {'type': 'string', 'description': 'The engagement UUID'},
                                     'title': {'type': 'string', 'description': 'Updated title'},
                                     'category': {'type': 'string', 'description': 'Updated category'},
                                     'description': {'type': 'string', 'description': 'Updated description (markdown)'},
                                     'steps': {'type': 'string', 'description': 'Updated steps (markdown)'},
                                     'expected_result': {'type': 'string',
                                                         'description': 'Updated expected result (markdown)'},
                                     'actual_result': {'type': 'string',
                                                       'description': 'What actually happened (markdown)'},
                                     'is_executed': {'type': 'boolean', 'description': 'Whether the test has been run'},
                                     'is_successful': {'type': 'boolean',
                                                       'description': 'Whether the test succeeded (the attack worked)'}},
                      'required': ['testcase_id', 'engagement_id']},
        method='PUT',
        path='/testcases/{testcase_id}',
        scope_args=('engagement_id',),
    ),
    ToolSpec(
        name='list_notes',
        description='List notes for a specific engagement.',
        input_schema={'type': 'object',
                      'properties': {'engagement_id': {'type': 'string', 'description': 'The engagement UUID'}},
                      'required': ['engagement_id']},
        method='GET',
        path='/engagements/{engagement_id}/notes',
        in_app=True,
    ),
    ToolSpec(
        name='get_note',
        description='Get full details of a specific note including content and linked resources.',
        input_schema={'type': 'object',
                      'properties': {'note_id': {'type': 'string', 'description': 'The note UUID'}},
                      'required': ['note_id']},
        method='GET',
        path='/notes/{note_id}',
    ),
    ToolSpec(
        name='create_note',
        description='Create a new note in an engagement.',
        input_schema={'type': 'object',
                      'properties': {'engagement_id': {'type': 'string', 'description': 'The engagement UUID'},
                                     'title': {'type': 'string', 'description': 'Note title'},
                                     'content': {'type': 'string', 'description': 'Note content (markdown)'}},
                      'required': ['engagement_id', 'title']},
        method='POST',
        path='/engagements/{engagement_id}/notes',
    ),
    ToolSpec(
        name='update_note',
        description="Update a note's title or content.",
        input_schema={'type': 'object',
                      'properties': {'note_id': {'type': 'string', 'description': 'The note UUID'},
                                     'title': {'type': 'string', 'description': 'Updated title'},
                                     'content': {'type': 'string', 'description': 'Updated content (markdown)'}},
                      'required': ['note_id']},
        method='PATCH',
        path='/notes/{note_id}',
    ),
    ToolSpec(
        name='list_vault_items',
        description='List vault items (credentials, keys, secrets) for a specific engagement.',
        input_schema={'type': 'object',
                      'properties': {'engagement_id': {'type': 'string', 'description': 'The engagement UUID'}},
                      'required': ['engagement_id']},
        method='GET',
        path='/vault',
        query=('engagement_id',),
        redact_vault_secrets=True,
    ),
    ToolSpec(
        name='create_vault_item',
        description='Create a new vault item (credential, key, or note) in an engagement.',
        input_schema={'type': 'object',
                      'properties': {'engagement_id': {'type': 'string', 'description': 'The engagement UUID'},
                                     'name': {'type': 'string', 'description': 'Item name / label'},
                                     'item_type': {'type': 'string',
                                                   'description': 'Type of vault item',
                                                   'enum': ['Credential', 'Key', 'File', 'Note']},
                                     'username': {'type': 'string', 'description': 'Username (for credentials)'},
                                     'password': {'type': 'string', 'description': 'Password (for credentials)'},
                                     'note': {'type': 'string', 'description': 'Additional notes'}},
                      'required': ['engagement_id', 'name', 'item_type']},
        method='POST',
        path='/vault',
        redact_vault_secrets=True,
        taxonomy={'item_type': 'vault'},
    ),
    ToolSpec(
        name='update_vault_item',
        description='Update fields on an existing vault item. Only specified fields are changed.',
        input_schema={'type': 'object',
                      'properties': {'item_id': {'type': 'string', 'description': 'The vault item UUID'},
                                     'engagement_id': {'type': 'string', 'description': 'The engagement UUID'},
                                     'name': {'type': 'string', 'description': 'Updated name'},
                                     'username': {'type': 'string', 'description': 'Updated username'},
                                     'password': {'type': 'string', 'description': 'Updated password'},
                                     'note': {'type': 'string', 'description': 'Updated notes'}},
                      'required': ['item_id', 'engagement_id']},
        method='PATCH',
        path='/vault/{item_id}',
        redact_vault_secrets=True,
        scope_args=('engagement_id',),
    ),
    ToolSpec(
        name='list_cleanup_artifacts',
        description='List cleanup artifacts (files, accounts, backdoors to remove) for an engagement.',
        input_schema={'type': 'object',
                      'properties': {'engagement_id': {'type': 'string', 'description': 'The engagement UUID'}},
                      'required': ['engagement_id']},
        method='GET',
        path='/cleanup-artifacts',
        query=('engagement_id',),
    ),
    ToolSpec(
        name='get_cleanup_artifact',
        description='Get full details of a specific cleanup artifact.',
        input_schema={'type': 'object',
                      'properties': {'artifact_id': {'type': 'string', 'description': 'The cleanup artifact UUID'},
                                     'engagement_id': {'type': 'string', 'description': 'The engagement UUID'}},
                      'required': ['artifact_id', 'engagement_id']},
        method='GET',
        path='/cleanup-artifacts/{artifact_id}',
        scope_args=('engagement_id',),
    ),
    ToolSpec(
        name='create_cleanup_artifact',
        description='Create a new cleanup artifact in an engagement.',
        input_schema={'type': 'object',
                      'properties': {'engagement_id': {'type': 'string', 'description': 'The engagement UUID'},
                                     'title': {'type': 'string', 'description': 'Artifact title'},
                                     'artifact_type': {'type': 'string',
                                                       'description': 'Type of cleanup item',
                                                       'enum': ['SSH Key',
                                                                'File',
                                                                'Account',
                                                                'Permission',
                                                                'Backdoor',
                                                                'Implant',
                                                                'Other']},
                                     'location': {'type': 'string', 'description': 'Where the artifact is located'},
                                     'description': {'type': 'string', 'description': 'Details about the artifact'}},
                      'required': ['engagement_id', 'title', 'artifact_type']},
        method='POST',
        path='/cleanup-artifacts',
        taxonomy={'artifact_type': 'cleanup'},
    ),
    ToolSpec(
        name='update_cleanup_artifact',
        description='Update fields on an existing cleanup artifact. Only specified fields are changed.',
        input_schema={'type': 'object',
                      'properties': {'artifact_id': {'type': 'string', 'description': 'The cleanup artifact UUID'},
                                     'engagement_id': {'type': 'string', 'description': 'The engagement UUID'},
                                     'title': {'type': 'string', 'description': 'Updated title'},
                                     'location': {'type': 'string', 'description': 'Updated location'},
                                     'description': {'type': 'string', 'description': 'Updated description'},
                                     'status': {'type': 'string',
                                                'description': 'Updated cleanup status',
                                                'enum': ['PENDING', 'CLEANED', 'PARTIALLY_CLEANED', 'NOT_APPLICABLE']}},
                      'required': ['artifact_id', 'engagement_id']},
        method='PATCH',
        path='/cleanup-artifacts/{artifact_id}',
        scope_args=('engagement_id',),
    ),
    ToolSpec(
        name='list_finding_templates',
        description='List all finding templates. These are reusable vulnerability definitions that can be applied to engagements.',
        input_schema={'type': 'object', 'properties': {}},
        method='GET',
        path='/templates',
    ),
    ToolSpec(
        name='get_finding_template',
        description='Get full details of a specific finding template.',
        input_schema={'type': 'object',
                      'properties': {'template_id': {'type': 'string', 'description': 'The template UUID'}},
                      'required': ['template_id']},
        method='GET',
        path='/templates/{template_id}',
    ),
    ToolSpec(
        name='create_finding_template',
        description='Create a new finding template for reuse across engagements.',
        input_schema={'type': 'object',
                      'properties': {'title': {'type': 'string', 'description': 'Template title'},
                                     'description': {'type': 'string', 'description': 'Description (markdown)'},
                                     'impact': {'type': 'string', 'description': 'Impact statement (markdown)'},
                                     'mitigations': {'type': 'string', 'description': 'Remediation steps (markdown)'},
                                     'category': {'type': 'string', 'description': 'Finding category'}},
                      'required': ['title', 'description']},
        method='POST',
        path='/templates',
    ),
    ToolSpec(
        name='update_finding_template',
        description='Update fields on an existing finding template.',
        input_schema={'type': 'object',
                      'properties': {'template_id': {'type': 'string', 'description': 'The template UUID'},
                                     'title': {'type': 'string', 'description': 'Updated title'},
                                     'description': {'type': 'string', 'description': 'Updated description (markdown)'},
                                     'impact': {'type': 'string', 'description': 'Updated impact (markdown)'},
                                     'mitigations': {'type': 'string', 'description': 'Updated mitigations (markdown)'},
                                     'category': {'type': 'string', 'description': 'Updated category'}},
                      'required': ['template_id']},
        method='PUT',
        path='/templates/{template_id}',
    ),
    ToolSpec(
        name='list_testcase_templates',
        description='List all test case templates. These are reusable test procedures for engagements.',
        input_schema={'type': 'object', 'properties': {}},
        method='GET',
        path='/testcase-templates',
    ),
    ToolSpec(
        name='get_testcase_template',
        description='Get full details of a specific test case template.',
        input_schema={'type': 'object',
                      'properties': {'template_id': {'type': 'string', 'description': 'The template UUID'}},
                      'required': ['template_id']},
        method='GET',
        path='/testcase-templates/{template_id}',
    ),
    ToolSpec(
        name='create_testcase_template',
        description='Create a new test case template for reuse across engagements.',
        input_schema={'type': 'object',
                      'properties': {'title': {'type': 'string', 'description': 'Template title'},
                                     'category': {'type': 'string',
                                                  'description': 'Category (e.g. Reconnaissance, Exploitation)'},
                                     'description': {'type': 'string', 'description': 'Description (markdown)'},
                                     'steps': {'type': 'string', 'description': 'Test steps (markdown)'},
                                     'expected_result': {'type': 'string',
                                                         'description': 'Expected outcome (markdown)'}},
                      'required': ['title', 'category', 'description']},
        method='POST',
        path='/testcase-templates',
    ),
    ToolSpec(
        name='update_testcase_template',
        description='Update fields on an existing test case template.',
        input_schema={'type': 'object',
                      'properties': {'template_id': {'type': 'string', 'description': 'The template UUID'},
                                     'title': {'type': 'string', 'description': 'Updated title'},
                                     'category': {'type': 'string', 'description': 'Updated category'},
                                     'description': {'type': 'string', 'description': 'Updated description (markdown)'},
                                     'steps': {'type': 'string', 'description': 'Updated steps (markdown)'},
                                     'expected_result': {'type': 'string',
                                                         'description': 'Updated expected result (markdown)'}},
                      'required': ['template_id']},
        method='PUT',
        path='/testcase-templates/{template_id}',
    ),
    ToolSpec(
        name='search',
        description='Global search across all resources (engagements, findings, assets, test cases, notes). Returns matching items with type, title, and context.',
        input_schema={'type': 'object',
                      'properties': {'query': {'type': 'string', 'description': 'Search query string'}},
                      'required': ['query']},
        method='GET',
        path='/search',
        query=('query',),
        query_rename={'query': 'q'},
        in_app=True,
    ),
    ToolSpec(
        name='get_engagement_stats',
        description='Get statistics for a specific engagement: finding counts by severity, test case progress, asset count, and remediation status.',
        input_schema={'type': 'object',
                      'properties': {'engagement_id': {'type': 'string', 'description': 'The engagement UUID'}},
                      'required': ['engagement_id']},
        handler='engagement_stats',
        calls=(('GET', '/engagements/{engagement_id}/counts'), ('GET', '/stats/overview'), ('GET', '/stats/severity-distribution'), ('GET', '/stats/findings-by-status')),
        in_app=True,
    ),
    ToolSpec(
        name='get_global_stats',
        description='Get platform-wide statistics: total engagements, findings, assets, and severity breakdowns.',
        input_schema={'type': 'object', 'properties': {}},
        handler='global_stats',
        calls=(('GET', '/stats/overview'), ('GET', '/stats/severity-distribution')),
        in_app=True,
    ),
    ToolSpec(
        name='delete_finding',
        description='Permanently delete a finding from an engagement. Irreversible.',
        input_schema={'type': 'object',
                      'properties': {'finding_id': {'type': 'string', 'description': 'The finding UUID'},
                                     'engagement_id': {'type': 'string',
                                                       'description': 'The engagement UUID (scope confirmation)'}},
                      'required': ['finding_id', 'engagement_id']},
        method='DELETE',
        path='/findings/{finding_id}',
        scope_args=('engagement_id',),
    ),
    ToolSpec(
        name='delete_asset',
        description='Permanently delete an asset from an engagement. Irreversible.',
        input_schema={'type': 'object',
                      'properties': {'asset_id': {'type': 'string', 'description': 'The asset UUID'},
                                     'engagement_id': {'type': 'string',
                                                       'description': 'The engagement UUID (scope confirmation)'}},
                      'required': ['asset_id', 'engagement_id']},
        method='DELETE',
        path='/assets/{asset_id}',
        scope_args=('engagement_id',),
    ),
    ToolSpec(
        name='delete_testcase',
        description='Permanently delete a test case from an engagement. Optionally cascade to child test cases.',
        input_schema={'type': 'object',
                      'properties': {'testcase_id': {'type': 'string', 'description': 'The test case UUID'},
                                     'engagement_id': {'type': 'string',
                                                       'description': 'The engagement UUID (scope confirmation)'},
                                     'cascade': {'type': 'boolean',
                                                 'description': 'If true, also delete all child test cases recursively '
                                                                '(default false)'}},
                      'required': ['testcase_id', 'engagement_id']},
        method='DELETE',
        path='/testcases/{testcase_id}',
        query=('cascade',),
        scope_args=('engagement_id',),
    ),
    ToolSpec(
        name='delete_note',
        description='Permanently delete a note. Irreversible.',
        input_schema={'type': 'object',
                      'properties': {'note_id': {'type': 'string', 'description': 'The note UUID'}},
                      'required': ['note_id']},
        method='DELETE',
        path='/notes/{note_id}',
    ),
    ToolSpec(
        name='get_vault_item',
        description='Get a single vault item by ID. Returns metadata only (no plaintext credentials); call the reveal endpoint via the UI to fetch decrypted secrets with audit logging.',
        input_schema={'type': 'object',
                      'properties': {'item_id': {'type': 'string', 'description': 'The vault item UUID'}},
                      'required': ['item_id']},
        method='GET',
        path='/vault/{item_id}',
        redact_vault_secrets=True,
    ),
    ToolSpec(
        name='delete_vault_item',
        description='Permanently delete a vault item from an engagement. Irreversible — credential cannot be recovered.',
        input_schema={'type': 'object',
                      'properties': {'item_id': {'type': 'string', 'description': 'The vault item UUID'},
                                     'engagement_id': {'type': 'string',
                                                       'description': 'The engagement UUID (scope confirmation)'}},
                      'required': ['item_id', 'engagement_id']},
        method='DELETE',
        path='/vault/{item_id}',
        scope_args=('engagement_id',),
    ),
    ToolSpec(
        name='delete_cleanup_artifact',
        description='Permanently delete a cleanup artifact from an engagement. Irreversible.',
        input_schema={'type': 'object',
                      'properties': {'artifact_id': {'type': 'string', 'description': 'The cleanup artifact UUID'},
                                     'engagement_id': {'type': 'string',
                                                       'description': 'The engagement UUID (scope confirmation)'}},
                      'required': ['artifact_id', 'engagement_id']},
        method='DELETE',
        path='/cleanup-artifacts/{artifact_id}',
        scope_args=('engagement_id',),
    ),
    ToolSpec(
        name='list_intel_items',
        description='List threat intelligence items (CVEs, advisories, blog posts, news). Supports search across title/CVE/content, type and severity filters, sorting, and pagination.',
        input_schema={'type': 'object',
                      'properties': {'search': {'type': 'string',
                                                'description': 'Search across title, CVE ID, and content'},
                                     'item_type': {'type': 'string',
                                                   'description': 'Filter by intel item type',
                                                   'enum': ['CVE', 'ADVISORY', 'ARTICLE', 'ZINE', 'EXPLOIT', 'OTHER']},
                                     'severity': {'type': 'string',
                                                  'description': 'Filter by severity',
                                                  'enum': ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFO']},
                                     'sort_by': {'type': 'string',
                                                 'enum': ['title',
                                                          'created_at',
                                                          'published_at',
                                                          'item_type',
                                                          'severity',
                                                          'source'],
                                                 'description': 'Sort column (default created_at)'},
                                     'sort_dir': {'type': 'string',
                                                  'enum': ['asc', 'desc'],
                                                  'description': 'Sort direction (default desc)'},
                                     'limit': {'type': 'integer',
                                               'minimum': 1,
                                               'maximum': 500,
                                               'description': 'Page size (default 50, max 500)'},
                                     'offset': {'type': 'integer',
                                                'minimum': 0,
                                                'description': 'Page offset (default 0)'}}},
        method='GET',
        path='/intel/items',
        query='*',
    ),
    ToolSpec(
        name='get_intel_item',
        description='Get full details of a single threat-intel item, including attachments and linked findings/assets/test cases.',
        input_schema={'type': 'object',
                      'properties': {'item_id': {'type': 'string', 'description': 'The intel item UUID'}},
                      'required': ['item_id']},
        method='GET',
        path='/intel/items/{item_id}',
    ),
    ToolSpec(
        name='list_intel_for_entity',
        description="List all threat-intel items that have been linked to a specific finding, test case, or note in RedWire. For free-form lookups like 'is there intel about CVE-2023-12345?' use list_intel_items with a search query instead.",
        input_schema={'type': 'object',
                      'properties': {'entity_type': {'type': 'string',
                                                     'enum': ['finding', 'testcase', 'note'],
                                                     'description': 'Which kind of RedWire resource the intel is linked '
                                                                    'to'},
                                     'entity_id': {'type': 'string',
                                                   'description': 'The UUID of the finding / test case / note'}},
                      'required': ['entity_type', 'entity_id']},
        method='GET',
        path='/intel/by-entity',
        query=('entity_type', 'entity_id'),
    ),
    ToolSpec(
        name='list_intel_feeds',
        description='List configured threat-intel feed sources (RSS, CVE feeds, etc.) with their refresh status.',
        input_schema={'type': 'object', 'properties': {}},
        method='GET',
        path='/intel/feeds',
    ),
    ToolSpec(
        name='ai_chat',
        description="Send a message to the built-in AI assistant for cybersecurity advice. Provide context about what you're working on.",
        input_schema={'type': 'object',
                      'properties': {'message': {'type': 'string', 'description': 'The message/question to send'},
                                     'editor_content': {'type': 'string',
                                                        'description': 'Optional: current editor content for context'},
                                     'field_context': {'type': 'object',
                                                       'description': 'Optional: field context (resourceType, '
                                                                      'fieldName)',
                                                       'properties': {'resourceType': {'type': 'string'},
                                                                      'fieldName': {'type': 'string'}}}},
                      'required': ['message']},
        handler='ai_chat',
        calls=(('POST', '/ai/chat'),),
    ),
]

# Enums that mirror a model enum are taken from it, so they can't go stale.
for _spec in TOOLS:
    if _spec.name == "list_engagements":
        _spec.input_schema["properties"]["status"]["enum"] = [s.value for s in EngagementStatus]

BY_NAME: dict[str, ToolSpec] = {t.name: t for t in TOOLS}


def mcp_catalog() -> list[dict]:
    """What ``GET /ai/tool-registry`` returns to the MCP server."""
    return [asdict(t) for t in TOOLS if t.mcp]


def in_app_tools() -> list[ToolSpec]:
    return [t for t in TOOLS if t.in_app]


def openai_tools() -> list[dict]:
    """The in-app chat's tool-use array (OpenAI function format)."""
    return [{"type": "function", "function": {
        "name": t.name, "description": t.description, "parameters": t.input_schema,
    }} for t in in_app_tools()]
