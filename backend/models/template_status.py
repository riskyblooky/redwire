"""Shared workflow status enum for template-style resources.

The PostgreSQL type is `templatestatus`, created by migration 0cad1f1b2a32.
Used by finding_template, testcase_template, and runbook models.
"""
import enum


class TemplateStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    PUBLISHED = "PUBLISHED"
