"""Shared enums and value objects."""

from __future__ import annotations

from enum import StrEnum


class RunStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    NEEDS_CLARIFICATION = "needs_clarification"
    ACCESS_DENIED = "access_denied"
    AWAITING_APPROVAL = "awaiting_approval"
    REJECTED = "rejected"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ErrorCategory(StrEnum):
    INVALID_TOOL = "invalid_tool"
    INVALID_ARGUMENTS = "invalid_arguments"
    TENANT_ACCESS_DENIED = "tenant_access_denied"
    STATE_CHANGE_NOT_AUTHORIZED = "state_change_not_authorized"
    APPROVAL_REQUIRED = "approval_required"
    LIMIT_REACHED = "limit_reached"
    TIMEOUT = "timeout"
    TRANSIENT_PROVIDER = "transient_provider"
    PROVIDER_ERROR = "provider_error"
    INVALID_MODEL_OUTPUT = "invalid_model_output"
    NOT_FOUND = "not_found"
    INTERNAL = "internal"


class ToolStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    REJECTED = "rejected"
    APPROVAL_REQUIRED = "approval_required"
    DEDUPLICATED = "deduplicated"


class OptimizationMode(StrEnum):
    BASELINE = "baseline"
    OPTIMIZED = "optimized"


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
