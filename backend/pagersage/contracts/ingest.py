"""Run-time ingest formats: what Kestrel Pay's injector (and a real CD system or Alertmanager)
POSTs to PagerSage. Tasks B10 (/ingest/*) and B02 (/alerts).

References use service names and person handles, like the seed files; ids continue the
history's (dep-0416, cfg-0061).
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from pagersage.contracts.schema import DeployStatus
from pagersage.contracts.seed import ConfigChangeId, DeployId, Epoch, Handle, Sha, Slug
from pagersage.contracts.tools import OpenIncidentResult


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CommitIn(_In):
    sha: Sha
    message: str
    author: Handle
    ts: Epoch
    files_changed: int | None = Field(default=None, ge=1)
    lines_changed: int | None = Field(default=None, ge=1)


class DeployIn(_In):
    """POST /ingest/deploy: a deploy finished."""

    id: DeployId
    service: Slug
    version: str
    ts: Epoch
    deployed_by: Handle
    status: DeployStatus = DeployStatus.OK
    env: str = "prod"
    commits: list[CommitIn] = Field(min_length=1)


class ConfigChangeIn(_In):
    """POST /ingest/config-change: a config value changed. Values are strings."""

    id: ConfigChangeId
    service: Slug
    key: str
    old: str
    new: str
    ts: Epoch
    made_by: Handle


class IngestResult(BaseModel):
    id: str
    service_id: str


# ── POST /alerts: Alertmanager webhook (version 4) ────────────────────────


class AlertmanagerAlert(BaseModel):
    """One alert in the webhook. PagerSage reads labels `service`, `signal`, `severity` and
    annotations `value`, `threshold` and optional `health` (0-1, drives live weights)."""

    model_config = ConfigDict(extra="allow")

    status: str
    labels: dict[str, str]
    annotations: dict[str, str] = Field(default_factory=dict)
    startsAt: datetime  # noqa: N815 (Alertmanager's field name)


class AlertmanagerWebhook(BaseModel):
    model_config = ConfigDict(extra="allow")

    status: str
    alerts: list[AlertmanagerAlert]


class AlertsResult(BaseModel):
    incidents: list[OpenIncidentResult]
    ignored: int = Field(description="Resolved alerts in the payload (not acted on)")
