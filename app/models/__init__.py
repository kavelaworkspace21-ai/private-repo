from app.models.tenant import Tenant
from app.models.audit import AuditLog
from app.models.user import User
from app.models.client import Client
from app.models.case import Case
from app.models.document import Document
from app.models.hearing import Hearing
from app.models.fee_collected import FeeCollected
from app.models.fee_due import FeeDue
from app.models.diary_entry import DiaryEntry
from app.models.diary_task import DiaryTask
from app.models.filing_deadline import FilingDeadline
from app.models.opposing_counsel import OpposingCounsel
from app.models.ai_chat import Conversation, AiMessage
from app.models.user_activity import UserActivity
from app.models.generated_draft import GeneratedDraft
from app.models.notification import Notification
from app.models.document_version import DocumentVersion
from app.models.consent import ConsentRecord
from app.models.draft_version import GeneratedDraftVersion
from app.models.backup_run import BackupRun
from app.models.scheduled_job_run import ScheduledJobRun
from app.models.data_rights import DataRightsRequest
from app.models.misuse_report import MisuseReport
from app.models.billing import (
    SubscriptionPlan, Subscription, UsageEvent, Invoice, WebhookEvent,
)
from app.models.workbench import WorkflowSession, WorkflowArtifact, WorkbenchUpload

__all__ = [
    "Tenant", "AuditLog",
    "User",
    "Client", "Case", "Document",
    "Hearing", "FeeCollected", "FeeDue",
    "DiaryEntry", "DiaryTask", "FilingDeadline", "OpposingCounsel",
    "Conversation", "AiMessage",
    "UserActivity",
    "GeneratedDraft",
    "Notification",
    "DocumentVersion",
    "ConsentRecord",
    "GeneratedDraftVersion",
    "BackupRun",
    "ScheduledJobRun",
    "DataRightsRequest",
    "MisuseReport",
    "SubscriptionPlan", "Subscription", "UsageEvent", "Invoice", "WebhookEvent",
    "WorkflowSession", "WorkflowArtifact", "WorkbenchUpload",
]

# ── Auto-fill tenant_id on child rows from their parent Case (full §5 compliance) ──
from sqlalchemy import event, text as _text

_CHILD_MODELS = [
    Hearing, Document, FeeCollected, FeeDue,
    DiaryEntry, DiaryTask, FilingDeadline, OpposingCounsel,
]


def _fill_tenant_from_case(mapper, connection, target):
    if getattr(target, "tenant_id", None) is None and getattr(target, "case_id", None):
        row = connection.execute(
            _text("SELECT tenant_id FROM cases WHERE id = :cid"),
            {"cid": target.case_id},
        ).fetchone()
        if row:
            target.tenant_id = row[0]


for _m in _CHILD_MODELS:
    event.listen(_m, "before_insert", _fill_tenant_from_case)
