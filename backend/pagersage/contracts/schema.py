"""Graph vocabulary. The node/edge model itself is build-plan.md section 3.

Code never spells a label or relationship type by hand: use these enums, so a typo is an
import error instead of a query that silently matches nothing.
"""

import re
from enum import StrEnum


class Label(StrEnum):
    SERVICE = "Service"
    TEAM = "Team"
    PERSON = "Person"
    DEPLOY = "Deploy"
    COMMIT = "Commit"
    CONFIG_CHANGE = "ConfigChange"
    ALERT = "Alert"
    INCIDENT = "Incident"
    RUNBOOK = "Runbook"
    POSTMORTEM = "Postmortem"
    DECISION = "Decision"
    POLICY = "Policy"
    AGENT = "Agent"
    HANDOFF = "Handoff"
    EVENT = "Event"


class Rel(StrEnum):
    # company layer
    DEPENDS_ON = "DEPENDS_ON"  # (Service)->(Service): a calls b
    IMPACTS = "IMPACTS"  # reverse of DEPENDS_ON for algo.BFS (no direction arg); loader syncs it
    OWNS = "OWNS"  # (Team)->(Service)
    MEMBER_OF = "MEMBER_OF"  # (Person)->(Team)
    ON_CALL = "ON_CALL"  # (Person)->(Team) {from, to}
    COLLABORATES = "COLLABORATES"  # (Person)->(Person) {deploys}: shipped together (G18)
    # change layer
    TARGETED = "TARGETED"  # (Deploy)->(Service)
    ROLLED_BACK = "ROLLED_BACK"  # (Deploy)->(Deploy): a rollback undid that deploy (B09)
    CONTAINS = "CONTAINS"  # (Deploy)->(Commit)
    AUTHORED = "AUTHORED"  # (Person)->(Commit)
    DEPLOYED = "DEPLOYED"  # (Person)->(Deploy)
    CHANGED = "CHANGED"  # (ConfigChange)->(Service)
    MADE = "MADE"  # (Person)->(ConfigChange)
    # incident layer
    FIRED_ON = "FIRED_ON"  # (Alert)->(Service)
    PART_OF = "PART_OF"  # (Alert|Event)->(Incident)
    CAUSED_BY = "CAUSED_BY"  # (Incident)->(Deploy|ConfigChange) {confidence}
    AFFECTED = "AFFECTED"  # (Incident)->(Service)
    SIMILAR_TO = "SIMILAR_TO"  # (Incident)->(Incident) {score}
    FOR = "FOR"  # (Runbook)->(Service)
    RESOLVED = "RESOLVED"  # (Runbook)->(Incident) {ts, worked} and (Person)->(Incident)
    ABOUT = "ABOUT"  # (Postmortem|Decision)->(Incident)
    WROTE = "WROTE"  # (Person|Agent)->(Postmortem); the Scribe writes live ones (A08)
    NEXT = "NEXT"  # (Event)->(Event)
    # decision traces and coordination
    BASED_ON = "BASED_ON"  # (Decision)->(evidence)
    PRECEDENT_FOR = "PRECEDENT_FOR"  # (Decision)->(Decision)
    APPLIED_POLICY = "APPLIED_POLICY"  # (Decision)->(Policy)
    MADE_BY = "MADE_BY"  # (Decision)->(Agent|Person)
    FROM = "FROM"  # (Handoff)->(Agent)
    TO = "TO"  # (Handoff)->(Agent)
    ON = "ON"  # (Handoff)->(Incident)
    ASSIGNED_TO = "ASSIGNED_TO"  # (Incident)->(Agent|Person)


class AgentName(StrEnum):
    TRIAGE = "triage"
    INVESTIGATOR = "investigator"
    HISTORIAN = "historian"
    RESPONDER = "responder"
    SCRIBE = "scribe"
    BRAIN = "brain"


class IncidentStatus(StrEnum):
    OPEN = "open"
    INVESTIGATING = "investigating"
    MITIGATED = "mitigated"
    RESOLVED = "resolved"
    NEEDS_HUMAN = "needs_human"  # agent hit a refusal, tool-call cap or timeout


class Severity(StrEnum):
    SEV1 = "sev1"
    SEV2 = "sev2"
    SEV3 = "sev3"


class AlertSignal(StrEnum):
    ERROR_RATE = "error_rate"
    LATENCY_P99 = "latency_p99"
    SATURATION = "saturation"


class DeployStatus(StrEnum):
    OK = "ok"
    ROLLED_BACK = "rolled_back"


class ChangeType(StrEnum):
    DEPLOY = "deploy"
    CONFIG = "config"


class ActionKind(StrEnum):
    PAGE = "page"
    ISSUE = "issue"
    ROLLBACK = "rollback"


# ── IDs ───────────────────────────────────────────────────────────────────
# Every node has a unique, human-readable `id` (range-indexed, task G02).
# Timestamps are epoch seconds (int) in a property named `ts` unless stated otherwise.

SLUG = re.compile(r"[a-z0-9][a-z0-9-]*")
HANDLE = re.compile(r"[a-z0-9][a-z0-9_-]*")


def _check(pattern: re.Pattern[str], value: str, what: str) -> str:
    if not pattern.fullmatch(value):
        raise ValueError(f"Invalid {what} {value!r}")
    return value


def service_id(name: str) -> str:
    return f"svc:{_check(SLUG, name, 'service name')}"


def team_id(slug: str) -> str:
    return f"team:{_check(SLUG, slug, 'team slug')}"


def person_id(handle: str) -> str:
    return f"person:{_check(HANDLE, handle, 'person handle')}"


def runbook_id(slug: str) -> str:
    return f"rb:{_check(SLUG, slug, 'runbook slug')}"


def policy_id(slug: str) -> str:
    return f"pol:{_check(SLUG, slug, 'policy slug')}"


def incident_id(n: int) -> str:
    return f"INC-{n:03d}"


def deploy_id(n: int) -> str:
    return f"dep-{n:04d}"


def config_change_id(n: int) -> str:
    return f"cfg-{n:04d}"


def alert_id(n: int) -> str:
    return f"alt-{n:05d}"


def postmortem_id(incident: str) -> str:
    """One postmortem per incident, so its id is derived from the incident id."""
    return f"pm:{incident}"


def commit_id(sha: str) -> str:
    """Commit.id equals Commit.sha, so evidence lookups by `id` work for commits too."""
    return sha


def event_id(incident: str, seq: int) -> str:
    return f"evt:{incident}:{seq}"


def agent_id(name: str) -> str:
    """Agent nodes are created on first use by the write tools (MADE_BY, FROM, TO)."""
    return f"agent:{name}"


def decision_id(incident: str, seq: int) -> str:
    return f"dec:{incident}:{seq}"


def handoff_id(incident: str, seq: int) -> str:
    return f"ho:{incident}:{seq}"
