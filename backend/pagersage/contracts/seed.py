"""Kestrel Pay company file formats that PagerSage ingests, and the checks that keep them
consistent. The files themselves belong to Kestrel Pay (kestrel-pay/company/, tasks K1-K3).

A company directory holds:
  topology.yaml   services and DEPENDS_ON edges            (required)
  org.yaml        teams, people, OWNS, on-call rotation    (required)
  runbooks.yaml   runbooks per service                     (optional)
  policies.yaml   action policies                          (optional)

Generated history is JSON Lines in kestrel-pay/history/export/ (task K5), one object per line:
  deploys.jsonl          Deploy, TARGETED, CONTAINS, DEPLOYED
  commits.jsonl          Commit, AUTHORED
  config_changes.jsonl   ConfigChange, CHANGED, MADE
  incidents.jsonl        Incident, Alert, Event, Postmortem, CAUSED_BY, AFFECTED, RESOLVED, WROTE
References use service names, person handles and ids, never graph ids (svc:..., person:...).

Format examples live in kestrel-pay/company/examples/.
"""

import json
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Annotated
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationInfo,
    field_validator,
    model_validator,
)

from pagersage.contracts.events import EventKind
from pagersage.contracts.schema import (
    ActionKind,
    AlertSignal,
    DeployStatus,
    IncidentStatus,
    Severity,
)

Slug = Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9-]*$")]
Handle = Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9_-]*$")]
DeployId = Annotated[str, StringConstraints(pattern=r"^dep-\d{4}$")]
ConfigChangeId = Annotated[str, StringConstraints(pattern=r"^cfg-\d{4}$")]
IncidentId = Annotated[str, StringConstraints(pattern=r"^INC-\d{3}$")]
AlertId = Annotated[str, StringConstraints(pattern=r"^alt-\d{5}$")]
Sha = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{7,40}$")]
Epoch = Annotated[int, Field(ge=0, description="Epoch seconds")]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ── topology.yaml ─────────────────────────────────────────────────────────


class Dependency(_Strict):
    to: Slug
    calls_per_min: int = Field(ge=0)
    p99_ms: int = Field(ge=0)


class ServiceSpec(_Strict):
    name: Slug
    tier: int = Field(ge=1, le=3)
    language: str
    description: str
    depends_on: list[Dependency] = Field(default_factory=list)


class Topology(_Strict):
    services: list[ServiceSpec] = Field(min_length=1)

    @model_validator(mode="after")
    def _edges_point_at_known_services(self) -> "Topology":
        names = [s.name for s in self.services]
        dupes = {n for n in names if names.count(n) > 1}
        if dupes:
            raise ValueError(f"Duplicate service names: {sorted(dupes)}")
        known = set(names)
        for s in self.services:
            for d in s.depends_on:
                if d.to == s.name:
                    raise ValueError(f"{s.name} depends on itself")
                if d.to not in known:
                    raise ValueError(f"{s.name} depends on unknown service {d.to!r}")
        return self


# ── org.yaml ──────────────────────────────────────────────────────────────


class TeamSpec(_Strict):
    slug: Slug
    name: str
    slack_channel: Annotated[str, StringConstraints(pattern=r"^#[a-z0-9-]+$")]
    owns: list[Slug] = Field(default_factory=list)


class PersonSpec(_Strict):
    handle: Handle
    name: str
    team: Slug
    role: str
    timezone: str

    @field_validator("timezone")
    @classmethod
    def _real_timezone(cls, v: str) -> str:
        try:
            ZoneInfo(v)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"Unknown IANA timezone {v!r}") from exc
        return v


class OnCall(_Strict):
    start: date = Field(description="First day of the rotation (UTC midnight)")
    rotation_days: int = Field(default=7, ge=1, le=28)
    teams: dict[Slug, list[Handle]] = Field(description="Team slug -> handles in rotation order")


class Org(_Strict):
    teams: list[TeamSpec] = Field(min_length=1)
    people: list[PersonSpec] = Field(min_length=1)
    on_call: OnCall


# ── runbooks.yaml / policies.yaml ─────────────────────────────────────────


class RunbookSpec(_Strict):
    slug: Slug
    title: str
    service: Slug
    steps: list[str] = Field(min_length=1)


class Runbooks(_Strict):
    runbooks: list[RunbookSpec] = Field(default_factory=list)


class PolicySpec(_Strict):
    slug: Slug
    name: str
    rule: str
    actions: list[ActionKind] = Field(min_length=1)
    max_tier: int | None = Field(default=None, ge=1, le=3, description="Applies to tiers <= this")


class Policies(_Strict):
    policies: list[PolicySpec] = Field(default_factory=list)


# ── the whole directory ───────────────────────────────────────────────────


class SeedBundle(_Strict):
    topology: Topology
    org: Org
    runbooks: Runbooks = Field(default_factory=Runbooks)
    policies: Policies = Field(default_factory=Policies)

    @model_validator(mode="after")
    def _cross_checks(self) -> "SeedBundle":
        services = {s.name for s in self.topology.services}
        teams = {t.slug for t in self.org.teams}
        handles = [p.handle for p in self.org.people]
        if len(set(handles)) != len(handles):
            raise ValueError("Duplicate person handles")
        team_of = {p.handle: p.team for p in self.org.people}

        owners: dict[str, list[str]] = {}
        for t in self.org.teams:
            for svc in t.owns:
                if svc not in services:
                    raise ValueError(f"Team {t.slug} owns unknown service {svc!r}")
                owners.setdefault(svc, []).append(t.slug)
        unowned = sorted(services - owners.keys())
        if unowned:
            raise ValueError(f"Services with no owning team: {unowned}")
        shared = sorted(s for s, o in owners.items() if len(o) > 1)
        if shared:
            raise ValueError(f"Services owned by more than one team: {shared}")

        for p in self.org.people:
            if p.team not in teams:
                raise ValueError(f"{p.handle} is in unknown team {p.team!r}")
        for team, rota in self.org.on_call.teams.items():
            if team not in teams:
                raise ValueError(f"On-call rotation for unknown team {team!r}")
            for h in rota:
                if h not in team_of:
                    raise ValueError(f"On-call handle {h!r} is not a person")
                if team_of[h] != team:
                    raise ValueError(f"{h} is on call for {team} but is a member of {team_of[h]}")
        for rb in self.runbooks.runbooks:
            if rb.service not in services:
                raise ValueError(f"Runbook {rb.slug} is for unknown service {rb.service!r}")
        return self


def load_seed_dir(path: Path) -> SeedBundle:
    """Read and validate a seed directory. Raises pydantic.ValidationError on bad data."""

    def read(name: str, required: bool) -> object:
        f = path / name
        if not f.is_file():
            if required:
                raise FileNotFoundError(f"Missing {f}")
            return None
        return yaml.safe_load(f.read_text(encoding="utf-8"))

    data = {"topology": read("topology.yaml", True), "org": read("org.yaml", True)}
    if (rb := read("runbooks.yaml", False)) is not None:
        data["runbooks"] = rb
    if (pol := read("policies.yaml", False)) is not None:
        data["policies"] = pol
    return SeedBundle.model_validate(data)


# ── history/export/*.jsonl ────────────────────────────────────────────────


class DeployRecord(_Strict):
    """deploys.jsonl. Commits are listed by sha; their details are in commits.jsonl."""

    id: DeployId
    service: Slug
    version: str
    ts: Epoch
    status: DeployStatus = DeployStatus.OK
    env: str = "prod"
    deployed_by: Handle
    commits: list[Sha] = Field(min_length=1)


class CommitRecord(_Strict):
    """commits.jsonl. Each commit ships in exactly one deploy."""

    sha: Sha
    message: str
    author: Handle
    ts: Epoch
    files_changed: int = Field(ge=1)
    lines_changed: int = Field(ge=1)


class ConfigChangeRecord(_Strict):
    """config_changes.jsonl. Values are strings, as they appear in the service's config.yaml."""

    id: ConfigChangeId
    service: Slug
    key: str
    old: str
    new: str
    ts: Epoch
    made_by: Handle


class AlertRecord(_Strict):
    id: AlertId
    service: Slug
    signal: AlertSignal
    value: float
    threshold: float
    severity: Severity
    ts: Epoch


class TimelineEntry(_Strict):
    """Becomes an Event node (agent null: past incidents were handled by people)."""

    ts: Epoch
    kind: EventKind
    text: str = Field(max_length=300)


class Cause(_Strict):
    change: Annotated[str, StringConstraints(pattern=r"^(dep|cfg)-\d{4}$")]
    confidence: float = Field(ge=0, le=1)


class RunbookOutcome(_Strict):
    runbook: Slug
    worked: bool
    ts: Epoch


class PostmortemRecord(_Strict):
    """Its id is postmortem_id(incident id)."""

    title: str
    body: str
    ts: Epoch
    author: Handle


class IncidentRecord(_Strict):
    """incidents.jsonl. Past incidents are all resolved."""

    id: IncidentId
    title: str
    severity: Severity
    status: IncidentStatus = IncidentStatus.RESOLVED
    opened_at: Epoch
    resolved_at: Epoch
    summary: str
    affected: list[Slug] = Field(min_length=1)
    caused_by: list[Cause] = Field(default_factory=list, description="Empty = no change to blame")
    alerts: list[AlertRecord] = Field(min_length=1)
    timeline: list[TimelineEntry] = Field(min_length=1)
    runbooks: list[RunbookOutcome] = Field(default_factory=list)
    resolved_by: Handle
    postmortem: PostmortemRecord | None = None

    @model_validator(mode="after")
    def _times_line_up(self) -> "IncidentRecord":
        if self.resolved_at < self.opened_at:
            raise ValueError(f"{self.id} resolves before it opens")
        stamps = [e.ts for e in self.timeline]
        if stamps != sorted(stamps):
            raise ValueError(f"{self.id} timeline is not in time order")
        for ts in stamps + [r.ts for r in self.runbooks]:
            if not self.opened_at <= ts <= self.resolved_at:
                raise ValueError(f"{self.id} has a timeline or runbook entry outside the incident")
        return self


class History(_Strict):
    deploys: list[DeployRecord]
    commits: list[CommitRecord]
    config_changes: list[ConfigChangeRecord]
    incidents: list[IncidentRecord]

    @model_validator(mode="after")
    def _cross_checks(self, info: ValidationInfo) -> "History":
        for what, ids in (
            ("deploy", [d.id for d in self.deploys]),
            ("commit", [c.sha for c in self.commits]),
            ("config change", [c.id for c in self.config_changes]),
            ("incident", [i.id for i in self.incidents]),
            ("alert", [a.id for i in self.incidents for a in i.alerts]),
        ):
            if dupes := sorted(x for x, n in Counter(ids).items() if n > 1):
                raise ValueError(f"Duplicate {what} ids: {dupes[:5]}")

        commit_ts = {c.sha: c.ts for c in self.commits}
        shipped = [sha for d in self.deploys for sha in d.commits]
        if missing := sorted(set(shipped) - commit_ts.keys()):
            raise ValueError(f"Deploys reference unknown commits: {missing[:5]}")
        if twice := sorted(s for s, n in Counter(shipped).items() if n > 1):
            raise ValueError(f"Commits shipped by more than one deploy: {twice[:5]}")
        if orphans := sorted(commit_ts.keys() - set(shipped)):
            raise ValueError(f"Commits no deploy ships: {orphans[:5]}")
        for d in self.deploys:
            if any(commit_ts[s] > d.ts for s in d.commits):
                raise ValueError(f"{d.id} ships a commit made after the deploy")

        changes = {d.id for d in self.deploys} | {c.id for c in self.config_changes}
        for i in self.incidents:
            for c in i.caused_by:
                if c.change not in changes:
                    raise ValueError(f"{i.id} is caused by unknown change {c.change!r}")

        seed = (info.context or {}).get("seed")
        if isinstance(seed, SeedBundle):
            self._check_against(seed)
        return self

    def _check_against(self, seed: SeedBundle) -> None:
        services = {s.name for s in seed.topology.services}
        handles = {p.handle for p in seed.org.people}
        runbooks = {rb.slug for rb in seed.runbooks.runbooks}

        def known(kind: str, value: str, pool: set[str], where: str) -> None:
            if value not in pool:
                raise ValueError(f"{where} references unknown {kind} {value!r}")

        for d in self.deploys:
            known("service", d.service, services, d.id)
            known("person", d.deployed_by, handles, d.id)
        for c in self.commits:
            known("person", c.author, handles, c.sha)
        for c in self.config_changes:
            known("service", c.service, services, c.id)
            known("person", c.made_by, handles, c.id)
        for i in self.incidents:
            for svc in i.affected + [a.service for a in i.alerts]:
                known("service", svc, services, i.id)
            known("person", i.resolved_by, handles, i.id)
            if i.postmortem:
                known("person", i.postmortem.author, handles, i.id)
            for r in i.runbooks:
                known("runbook", r.runbook, runbooks, i.id)


HISTORY_FILES = {
    "deploys": "deploys.jsonl",
    "commits": "commits.jsonl",
    "config_changes": "config_changes.jsonl",
    "incidents": "incidents.jsonl",
}


def load_history_dir(path: Path, seed: SeedBundle | None = None) -> History:
    """Read and validate a history export directory. With `seed`, also check every service,
    person and runbook it mentions exists. Raises pydantic.ValidationError on bad data."""
    data: dict[str, list[object]] = {}
    for field, name in HISTORY_FILES.items():
        f = path / name
        if not f.is_file():
            raise FileNotFoundError(f"Missing {f}")
        lines = f.read_text(encoding="utf-8").splitlines()
        data[field] = [json.loads(line) for line in lines if line.strip()]
    return History.model_validate(data, context={"seed": seed})
