"""Agent tool signatures (task S02). Bodies are stubs; each names the task that implements it.

Rules for implementers:
- Keep the signature and return type. Change them only as a deliberate contracts change.
- Read tools run named queries from backend/queries/ via `pagersage.queries.load` and
  `graph.ro_query`. Write tools are the ONLY way agents change the graph.
- The docstring becomes the Claude tool description (task A02 wraps these with @beta_tool),
  so keep the first line short and say when to use the tool.
- On "no data" return an empty list, not an error; raise ToolError with a hint when the
  input is wrong (A02 turns it into an is_error tool_result).
"""

import functools
import json
import math
import re
import threading
import time
from typing import Literal, NoReturn

import httpx
from falkordb import Graph
from pydantic import BaseModel, Field
from redis.exceptions import ResponseError

from pagersage import db, embeddings, queries
from pagersage.config import get_settings
from pagersage.contracts.events import AgentEvent, EventKind, Highlight
from pagersage.contracts.schema import (
    ActionKind,
    AgentName,
    AlertSignal,
    ChangeType,
    DeployStatus,
    IncidentStatus,
    Rel,
    Severity,
    agent_id,
    alert_id,
    config_change_id,
    decision_id,
    event_id,
    handoff_id,
    person_id,
    postmortem_id,
)
from pagersage.contracts.schema import deploy_id as deploy_id_for
from pagersage.contracts.schema import incident_id as new_incident_id


class ToolError(Exception):
    """Bad input the agent can fix. The message is shown to the agent as a hint."""


def _todo(task: str) -> NoReturn:
    raise NotImplementedError(f"Not implemented yet: task {task} on the PagerSage task board")


# ═════════════════════════════════════════════════════════════════════════
# Result types
# ═════════════════════════════════════════════════════════════════════════


class ServiceMatch(BaseModel):
    id: str
    name: str
    score: float


class ImpactedService(BaseModel):
    id: str
    name: str
    tier: int
    team: str | None


class CommitRef(BaseModel):
    sha: str
    message: str
    author: str | None = Field(description="Person handle")


class Suspect(BaseModel):
    change_id: str = Field(description="Deploy id (dep-...) or ConfigChange id (cfg-...)")
    change_type: ChangeType
    service_id: str
    ts: int
    dist: int = Field(description="Path weight from the alerting service; 0 = same service")
    fragility: float
    commits: list[CommitRef] = Field(default_factory=list)
    score: float
    score_parts: dict[str, float] = Field(
        description="recency, distance, fragility, anomaly factors that multiply into score"
    )


class RootCausePath(BaseModel):
    services: list[str] = Field(description="Service ids from the alerting service to the suspect")
    path_weight: int
    change_id: str
    commits: list[str] = Field(description="Commit shas in the change")
    authors: list[str] = Field(description="Person handles")
    highlight: Highlight


class PageTarget(BaseModel):
    handle: str
    team: str
    reason: Literal["on_call", "recent_author"]


class RunbookRef(BaseModel):
    id: str
    title: str
    success_count: int


class SimilarIncident(BaseModel):
    id: str
    title: str
    score: float = Field(
        description="Cosine similarity, 1 - the index's distance (higher is closer)"
    )
    shared_services: int
    runbooks: list[RunbookRef] = Field(default_factory=list)
    postmortem_titles: list[str] = Field(default_factory=list)


class SimilarIncidents(BaseModel):
    graph_ranked: list[SimilarIncident] = Field(description="Vector candidates re-ranked by graph")
    vector_only: list[SimilarIncident] = Field(description="Same candidates, vector order only")


class RunbookHit(BaseModel):
    id: str
    title: str
    steps: list[str]
    success_count: int
    fail_count: int
    success_rate: float = Field(description="(success+1)/(success+fail+2)")


class PolicyHit(BaseModel):
    id: str
    name: str
    rule: str


class Expert(BaseModel):
    handle: str
    name: str
    score: float
    reasons: dict[str, int] = Field(
        description="commits, incidents_resolved, postmortems_written, team_member counts"
    )


class BusFactorRisk(BaseModel):
    service_id: str
    tier: int
    sole_author: str = Field(description="Only person who committed to it recently")


class ServiceScore(BaseModel):
    id: str
    name: str
    fragility: float = Field(description="Betweenness on DEPENDS_ON")
    criticality: float = Field(description="PageRank on DEPENDS_ON")


class DecisionRecord(BaseModel):
    id: str
    agent: str
    what: str
    why: str
    confidence: float
    evidence: list[str]
    precedents: list[str]
    policies: list[str]


class HandoffRecord(BaseModel):
    id: str
    ts: int
    from_agent: str
    to_agent: str
    note: str


class IncidentReplay(BaseModel):
    incident_id: str
    title: str
    status: str
    decisions: list[DecisionRecord]
    handoffs: list[HandoffRecord]
    event_count: int


class ActionResult(BaseModel):
    action: ActionKind
    ok: bool
    detail: str
    url: str | None = None


class AlertIn(BaseModel):
    """Alert as the detector hands it over (parsed from Alertmanager JSON by task B02)."""

    service_id: str
    signal: AlertSignal
    value: float
    threshold: float
    severity: Severity
    ts: int


class OpenIncidentResult(BaseModel):
    incident_id: str
    alert_id: str
    merged: bool = Field(description="True when the alert joined an incident opened <10 min ago")


# ═════════════════════════════════════════════════════════════════════════
# Read tools: one named query each
# ═════════════════════════════════════════════════════════════════════════


# RediSearch operators. Text with none of them is split into words (so `payments-db` is not
# "payments NOT db"); text with them is the agent's own query and is passed through.
_SEARCH_SYNTAX = re.compile(r"[*%|\"@~]")


def _search_terms(q: str) -> str:
    """'payments db' -> '%payments%|db*': fuzzy (edit distance 1) for words of 4+ letters,
    prefix for shorter ones, any word may match (more matching words score higher)."""
    words = re.findall(r"[a-z0-9]+", q.lower())
    if not words:
        raise ToolError(f"No words to search for in {q!r}. Pass a service name, e.g. 'payments'.")
    return "|".join(f"%{w}%" if len(w) >= 4 else f"{w}*" for w in words)


def find_service(q: str, limit: int = 3) -> list[ServiceMatch]:
    """Find services by name from free text. Supports prefixes (pay*) and typos.

    Use first when you only have a name from an alert or a question.
    """
    if not 1 <= limit <= 20:
        raise ToolError("limit must be between 1 and 20")
    q = q.strip()
    terms = q if _SEARCH_SYNTAX.search(q) else _search_terms(q)
    # An explicit @field query is used as is; otherwise names first, then descriptions.
    scoped = [terms] if "@" in terms else [f"@name:({terms})", f"@description:({terms})"]
    graph, query = db.get_graph(), queries.load("find_service")
    found: dict[str, ServiceMatch] = {}
    for text in scoped:
        try:
            rows = graph.ro_query(query, {"q": text, "limit": limit}).result_set
        except ResponseError as e:
            raise ToolError(f"Bad search syntax in {q!r} ({e}). Try plain words.") from e
        for sid, name, score in rows:
            found.setdefault(sid, ServiceMatch(id=sid, name=name, score=score))
        if len(found) >= limit:
            break
    return list(found.values())[:limit]


def _require_service(graph: Graph, service_id: str) -> None:
    [[n]] = graph.ro_query(queries.load("service_exists"), {"sid": service_id}).result_set
    if not n:
        raise ToolError(
            f"No service with id {service_id!r}. Ids look like 'svc:payments-db'; "
            "call find_service with the name to get one."
        )


def blast_radius(service_id: str, max_depth: int = 3) -> list[ImpactedService]:
    """List services that are hurt if this service is down (everything that calls it).

    Excludes the service itself. Ordered by tier, most critical first.
    """
    if not 1 <= max_depth <= 6:
        raise ToolError("max_depth must be between 1 and 6")
    graph = db.get_graph()
    _require_service(graph, service_id)
    rows = graph.ro_query(
        queries.load("blast_radius"), {"sid": service_id, "max_depth": max_depth}
    ).result_set
    return [ImpactedService(id=i, name=n, tier=t, team=team) for i, n, t, team in rows]


# Suspect score (G08) = recency x distance x fragility x anomaly, each part shown to the agent:
#   recency   = 0.5 ** (age / 6 h)            newer changes first; halves every 6 hours
#   distance  = 1 / (1 + hops)                hops along DEPENDS_ON from the alerting service
#   fragility = 1 + fragility / max fragility betweenness, normalised to 1..2
#   anomaly   = 1 + 10 * max(0, worst_dep_health - health)
# anomaly is how much sicker the service is than everything below it. A sick service whose
# dependencies are sicker is a victim (anomaly 1); the sickest service at the bottom of the
# chain is the likely cause. Hops, not path weight: live weights steer root_cause_path, but a
# raw weight would swamp the other factors.
RECENCY_HALF_LIFE = 6 * 3600
ANOMALY_GAIN = 10.0


def _now() -> int:
    return int(time.time())


# Incident ids, alert ids, timeline seqs and handoff/decision numbers are "highest + 1": the
# API thread and agent threads hold this lock around read-then-write so no two writers pick
# the same number.
_write_lock = threading.RLock()


def _locked(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        with _write_lock:
            return fn(*args, **kwargs)

    return wrapper


def _score_parts(ts: int, hops: int, ctx: tuple[float, float, float, float]) -> dict[str, float]:
    fragility, health, worst_dep_health, max_fragility = ctx
    return {
        "recency": 0.5 ** (max(_now() - ts, 0) / RECENCY_HALF_LIFE),
        "distance": 1.0 / (1 + hops),
        "fragility": 1.0 + (fragility / max_fragility if max_fragility else 0.0),
        "anomaly": 1.0 + ANOMALY_GAIN * max(0.0, worst_dep_health - health),
    }


def suspect_changes(service_id: str, since: int) -> list[Suspect]:
    """Rank recent deploys and config changes on this service and everything it depends on.

    The root cause is usually downstream of the alerting service. `since` is epoch seconds.
    Results are sorted by score, highest first; score_parts explains each score.
    """
    if since < 0:
        raise ToolError("since is epoch seconds, e.g. the alert time minus 2 hours")
    graph = db.get_graph()
    _require_service(graph, service_id)
    rows = graph.ro_query(
        queries.load("suspect_changes"), {"sid": service_id, "since": since}
    ).result_set
    if not rows:
        return []
    sids = sorted({r[2] for r in rows})
    context = {
        sid: tuple(rest)
        for sid, *rest in graph.ro_query(queries.load("suspect_context"), {"sids": sids}).result_set
    }
    suspects = []
    for change_id, change_type, sid, ts, dist, hops, commits in rows:
        parts = _score_parts(ts, hops, context[sid])
        suspects.append(
            Suspect(
                change_id=change_id,
                change_type=ChangeType(change_type),
                service_id=sid,
                ts=ts,
                dist=dist,
                fragility=context[sid][0],
                commits=[CommitRef(**c) for c in commits if c["sha"]],
                score=math.prod(parts.values()),
                score_parts=parts,
            )
        )
    return sorted(suspects, key=lambda s: (-s.score, s.change_id))


def root_cause_path(
    alerting_service_id: str, suspect_service_id: str, change_id: str
) -> RootCausePath:
    """Return the dependency path from the alerting service to the suspect change, with
    the commits and authors behind it. Call once you have picked a suspect."""
    graph = db.get_graph()
    for sid in (alerting_service_id, suspect_service_id):
        _require_service(graph, sid)
    rows = graph.ro_query(queries.load("change_details"), {"cid": change_id}).result_set
    if not rows:
        raise ToolError(
            f"No change with id {change_id!r}. Use a change_id from suspect_changes "
            "(dep-0416, cfg-0061)."
        )
    [[kind, changed_sid, links]] = rows
    if changed_sid != suspect_service_id:
        raise ToolError(f"{change_id} changed {changed_sid}, not {suspect_service_id}.")

    if alerting_service_id == suspect_service_id:
        services, weight = [alerting_service_id], 0
    else:
        found = graph.ro_query(
            queries.load("root_cause_path"),
            {"alerting": alerting_service_id, "suspect": suspect_service_id},
        ).result_set
        if not found:
            raise ToolError(
                f"{suspect_service_id} is not downstream of {alerting_service_id}; "
                "pick a suspect from suspect_changes for this service."
            )
        [[services, weight]] = found

    links = [x for x in links if x["person"] or x["sha"]]
    commits = sorted({x["sha"] for x in links if x["sha"]})
    people = sorted({(x["handle"], x["person"]) for x in links if x["person"]})
    edges = [(a, Rel.DEPENDS_ON.value, b) for a, b in zip(services, services[1:], strict=False)]
    if kind == ChangeType.DEPLOY:
        edges.append((change_id, Rel.TARGETED.value, suspect_service_id))
        edges += [(change_id, Rel.CONTAINS.value, sha) for sha in commits]
        edges += sorted(
            {(x["person"], Rel.AUTHORED.value, x["sha"]) for x in links if x["person"] and x["sha"]}
        )
    else:
        edges.append((change_id, Rel.CHANGED.value, suspect_service_id))
        edges += [(pid, Rel.MADE.value, change_id) for _, pid in people]
    nodes = [*services, change_id, *commits, *(pid for _, pid in people)]
    return RootCausePath(
        services=services,
        path_weight=weight,
        change_id=change_id,
        commits=commits,
        authors=[handle for handle, _ in people],
        highlight=Highlight(nodes=nodes, edges=edges),
    )


def who_to_page(service_id: str, now: int | None = None) -> list[PageTarget]:
    """Who to page for a service: the owning team's current on-call, then recent authors."""
    graph = db.get_graph()
    _require_service(graph, service_id)
    rows = graph.ro_query(
        queries.load("who_to_page"), {"sid": service_id, "now": _now() if now is None else now}
    ).result_set
    on_call = [r for r in rows if r[2] == "on_call"]
    paged = {r[0] for r in on_call}
    # Newest first, ties by handle; the on-call person is not paged twice.
    authors = sorted((r for r in rows if r[2] == "recent_author"), key=lambda r: (-r[3], r[0]))
    authors = [r for r in authors if r[0] not in paged][:2]
    return [PageTarget(handle=h, team=t, reason=reason) for h, t, reason, _ in on_call + authors]


# similar_incidents (G12): vector search picks CANDIDATES by text; the graph ranks them by
#   1. services shared with the root-cause path (AFFECTED)
#   2. whether its cause (CAUSED_BY a deploy or config change) hit a service on the path
#   3. newest first, among candidates that share any of the path: the latest precedent
#      reflects today's config and runbooks (INC-042 over INC-031 over INC-019)
#   4. text similarity
SIMILAR_CANDIDATES = 10


def similar_incidents(
    incident_id: str, path_service_ids: list[str], limit: int = 3
) -> SimilarIncidents:
    """Find past incidents like this one: vector search on the incident text, re-ranked by
    how many services on the root-cause path they share. Includes runbooks that worked."""
    if not 1 <= limit <= SIMILAR_CANDIDATES:
        raise ToolError(f"limit must be between 1 and {SIMILAR_CANDIDATES}")
    graph = db.get_graph()
    rows = graph.ro_query(queries.load("incident_embedding_state"), {"iid": incident_id}).result_set
    if not rows:
        raise ToolError(f"No incident with id {incident_id!r} (ids look like 'INC-051').")
    if not rows[0][1]:
        raise ToolError(f"{incident_id} has no embedding yet: call set_triage first.")
    rows = graph.ro_query(
        queries.load("similar_incidents"), {"iid": incident_id, "k": SIMILAR_CANDIDATES + 1}
    ).result_set

    path = set(path_service_ids)
    ranked = []
    for iid, title, sim, opened_at, affected, cause_services, postmortems, runbooks in rows:
        shared = len(path.intersection(affected))
        worked = {r["id"]: r for r in runbooks if r["id"] and r["worked"]}
        item = SimilarIncident(
            id=iid,
            title=title,
            score=sim,
            shared_services=shared,
            runbooks=[
                RunbookRef(id=r["id"], title=r["title"], success_count=r["success_count"])
                for r in sorted(worked.values(), key=lambda r: r["id"])
            ],
            postmortem_titles=sorted(postmortems),
        )
        cause_on_path = bool(path.intersection(cause_services))
        key = (shared, cause_on_path, opened_at if shared else 0, sim)
        ranked.append((key, item))
    vector_only = sorted((item for _, item in ranked), key=lambda i: -i.score)[:limit]
    graph_ranked = [item for _, item in sorted(ranked, key=lambda x: x[0], reverse=True)][:limit]
    return SimilarIncidents(graph_ranked=graph_ranked, vector_only=vector_only)


def best_runbook(service_id: str, limit: int = 3) -> list[RunbookHit]:
    """Runbooks for a service, best success rate first (procedural memory)."""
    if not 1 <= limit <= 20:
        raise ToolError("limit must be between 1 and 20")
    graph = db.get_graph()
    _require_service(graph, service_id)
    rows = graph.ro_query(
        queries.load("best_runbook"), {"sid": service_id, "limit": limit}
    ).result_set
    return [
        RunbookHit(id=i, title=t, steps=steps, success_count=ok, fail_count=bad, success_rate=rate)
        for i, t, steps, ok, bad, rate in rows
    ]


def check_policy(action: ActionKind, service_id: str) -> list[PolicyHit]:
    """Policies that apply before taking this action on this service. Empty list = none.

    Call before every page, issue and rollback; cite the policy ids in record_decision.
    """
    if action not in set(ActionKind):
        raise ToolError(f"action must be one of {[a.value for a in ActionKind]}, got {action!r}")
    graph = db.get_graph()
    _require_service(graph, service_id)
    rows = graph.ro_query(
        queries.load("check_policy"), {"action": ActionKind(action).value, "sid": service_id}
    ).result_set
    return [PolicyHit(id=i, name=n, rule=r) for i, n, r in rows]


# who_knows score: a resolved incident or a postmortem shows deeper knowledge than one commit.
EXPERT_WEIGHTS = {"commits": 1, "incidents_resolved": 3, "postmortems_written": 2, "team_member": 2}
# bus_factor: "recently" = the last 90 days, Kestrel Pay's whole history window.
BUS_FACTOR_DAYS = 90


def who_knows(service_id: str, limit: int = 5) -> list[Expert]:
    """People who know a service best, from commits, incidents resolved and postmortems."""
    if not 1 <= limit <= 20:
        raise ToolError("limit must be between 1 and 20")
    graph = db.get_graph()
    _require_service(graph, service_id)
    experts = []
    for handle, name, *counts in graph.ro_query(
        queries.load("who_knows"), {"sid": service_id}
    ).result_set:
        reasons = dict(zip(EXPERT_WEIGHTS, counts, strict=True))
        score = float(sum(EXPERT_WEIGHTS[k] * v for k, v in reasons.items()))
        experts.append(Expert(handle=handle, name=name, score=score, reasons=reasons))
    return sorted(experts, key=lambda e: (-e.score, e.handle))[:limit]


def bus_factor(max_tier: int = 1) -> list[BusFactorRisk]:
    """Services up to this tier where only one person has committed recently."""
    if not 1 <= max_tier <= 3:
        raise ToolError("max_tier must be 1, 2 or 3")
    rows = (
        db.get_graph()
        .ro_query(
            queries.load("bus_factor"),
            {"max_tier": max_tier, "since": _now() - BUS_FACTOR_DAYS * 86400},
        )
        .result_set
    )
    return [BusFactorRisk(service_id=s, tier=t, sole_author=a) for s, t, a in rows]


def fragile_services(limit: int = 5) -> list[ServiceScore]:
    """Services whose failure would cut the most dependency paths (highest betweenness)."""
    if not 1 <= limit <= 30:
        raise ToolError("limit must be between 1 and 30")
    rows = db.get_graph().ro_query(queries.load("fragile_services"), {"limit": limit}).result_set
    return [ServiceScore(id=i, name=n, fragility=f, criticality=c) for i, n, f, c in rows]


def _seq(node_id: str) -> int:
    """dec:INC-051:10 -> 10, so decision 10 sorts after decision 2."""
    return int(node_id.rsplit(":", 1)[1])


def replay_incident(incident_id: str) -> IncidentReplay:
    """Every decision (with evidence, precedents, policies) and handoff for an incident."""
    rows = db.get_graph().ro_query(queries.load("replay_incident"), {"iid": incident_id}).result_set
    if not rows:
        raise ToolError(f"No incident with id {incident_id!r} (ids look like 'INC-051').")
    [[iid, title, status, decisions, handoffs, event_count]] = rows
    decisions = sorted(decisions, key=lambda d: (d["ts"] or 0, _seq(d["id"])))
    handoffs = sorted(handoffs, key=lambda h: (h["ts"] or 0, _seq(h["id"])))
    return IncidentReplay(
        incident_id=iid,
        title=title or "",
        status=status or "",
        decisions=[
            DecisionRecord(
                id=d["id"],
                agent=d["agent"] or "",
                what=d["what"] or "",
                why=d["why"] or "",
                confidence=d["confidence"] or 0.0,
                evidence=sorted(d["evidence"]),
                precedents=sorted(d["precedents"]),
                policies=sorted(d["policies"]),
            )
            for d in decisions
        ],
        handoffs=[
            HandoffRecord(
                id=h["id"], ts=h["ts"], from_agent=h["from"], to_agent=h["to"], note=h["note"]
            )
            for h in handoffs
        ],
        event_count=event_count,
    )


# ═════════════════════════════════════════════════════════════════════════
# Write tools: the only way agents change the graph
# ═════════════════════════════════════════════════════════════════════════


@_locked
def set_triage(
    incident_id: str,
    title: str,
    severity: Severity,
    impacted_service_ids: list[str],
    summary: str,
) -> None:
    """Record triage: title, severity, AFFECTED services, summary. Moves the incident to
    investigating and stores the incident embedding used by similar_incidents."""
    if severity not in set(Severity):
        raise ToolError(f"severity must be one of {[s.value for s in Severity]}, got {severity!r}")
    title, summary = title.strip(), summary.strip()
    if not title or not summary:
        raise ToolError("title and summary must not be empty")
    sids = list(dict.fromkeys(impacted_service_ids))
    if not sids:
        raise ToolError("List at least one impacted service id, e.g. the alerting service.")
    graph = db.get_graph()
    rows = graph.ro_query(queries.load("incident_status"), {"iid": incident_id}).result_set
    if not rows:
        raise ToolError(f"No incident with id {incident_id!r} (ids look like 'INC-051').")
    if rows[0][0] == IncidentStatus.RESOLVED:
        raise ToolError(f"{incident_id} is already resolved.")
    known = {r[0] for r in graph.ro_query(queries.load("services_exist"), {"ids": sids}).result_set}
    if missing := [s for s in sids if s not in known]:
        raise ToolError(
            f"Unknown service ids {missing}: use ids from blast_radius or find_service."
        )
    [vector] = embeddings.embed([embeddings.incident_text(title, summary)])
    graph.query(
        queries.load("triage_write"),
        {
            "iid": incident_id,
            "title": title,
            "severity": Severity(severity).value,
            "summary": summary,
            "embedding": vector,
            "sids": sids,
        },
    )


@_locked
def record_cause(incident_id: str, change_id: str, confidence: float) -> None:
    """Write CAUSED_BY {confidence} from the incident to a Deploy or ConfigChange (0-1)."""
    if not 0.0 <= confidence <= 1.0:
        raise ToolError(f"confidence must be between 0 and 1, got {confidence}")
    graph = db.get_graph()
    if not graph.ro_query(queries.load("incident_status"), {"iid": incident_id}).result_set:
        raise ToolError(f"No incident with id {incident_id!r} (ids look like 'INC-051').")
    if not graph.ro_query(queries.load("change_details"), {"cid": change_id}).result_set:
        raise ToolError(
            f"No change with id {change_id!r}. Use a change_id from suspect_changes "
            "(dep-0416, cfg-0061)."
        )
    graph.query(
        queries.load("cause_write"),
        {"iid": incident_id, "cid": change_id, "confidence": confidence, "now": _now()},
    )


@_locked
def link_similar(incident_id: str, other_incident_id: str, score: float) -> None:
    """Write SIMILAR_TO {score} to a past incident and back-fill PRECEDENT_FOR links."""
    if not 0.0 <= score <= 1.0:
        raise ToolError(f"score must be between 0 and 1, got {score}")
    if incident_id == other_incident_id:
        raise ToolError("Link to a different, past incident from similar_incidents.")
    graph = db.get_graph()
    ids = [incident_id, other_incident_id]
    known = {r[0] for r in graph.ro_query(queries.load("incidents_exist"), {"ids": ids}).result_set}
    if missing := [i for i in ids if i not in known]:
        raise ToolError(f"No incident with id {missing[0]!r}: use ids from similar_incidents.")
    params = {"iid": incident_id, "other": other_incident_id}
    graph.query(queries.load("similar_write"), {**params, "score": score})
    graph.query(queries.load("precedents_backfill"), params)


@_locked
def record_decision(
    incident_id: str,
    agent: AgentName,
    what: str,
    why: str,
    confidence: float,
    evidence_ids: list[str],
    policy_ids: list[str] | None = None,
) -> str:
    """Record a decision with the node ids it is based on. Returns the decision id.

    Links ABOUT, MADE_BY, BASED_ON, APPLIED_POLICY and PRECEDENT_FOR (from decisions on
    similar incidents). Evidence ids may be any node id, including commit shas.
    """
    if not 0.0 <= confidence <= 1.0:
        raise ToolError(f"confidence must be between 0 and 1, got {confidence}")
    agent = AgentName(agent)
    policy_ids = policy_ids or []
    graph = db.get_graph()
    # Check everything before the first write, so bad input leaves no half-made decision.
    rows = graph.ro_query(queries.load("decision_count"), {"iid": incident_id}).result_set
    if not rows:
        raise ToolError(f"No incident with id {incident_id!r} (ids look like 'INC-051').")
    evidence = list(dict.fromkeys(evidence_ids))
    if evidence:
        found = graph.ro_query(queries.load("nodes_exist"), {"ids": evidence}).result_set
        if missing := [nid for nid, n in found if not n]:
            raise ToolError(f"Unknown evidence ids {missing}: use ids returned by other tools.")
    if policy_ids:
        known = {
            r[0]
            for r in graph.ro_query(queries.load("policies_exist"), {"ids": policy_ids}).result_set
        }
        if missing := sorted(set(policy_ids) - known):
            raise ToolError(f"Unknown policy ids {missing}: use ids from check_policy.")

    did = decision_id(incident_id, rows[0][1] + 1)
    graph.query(
        queries.load("decision_create"),
        {
            "did": did,
            "iid": incident_id,
            "agent_id": agent_id(agent),
            "agent": agent.value,
            "model": getattr(get_settings(), f"model_{agent.value}"),
            "what": what,
            "why": why,
            "now": _now(),
            "confidence": confidence,
        },
    )
    if evidence:
        graph.query(queries.load("decision_evidence"), {"did": did, "evidence": evidence})
    if policy_ids:
        graph.query(queries.load("decision_policies"), {"did": did, "policies": policy_ids})
    graph.query(queries.load("decision_precedents"), {"did": did})
    return did


@_locked
def handoff(
    incident_id: str,
    from_agent: AgentName,
    to_agent: AgentName,
    note: str,
    state_patch: dict[str, object],
) -> str:
    """Hand the incident to the next agent. Call this last. Returns the handoff id.

    `note` is what the next agent must know; `state_patch` merges into Incident.state.
    """
    from_agent, to_agent = AgentName(from_agent), AgentName(to_agent)
    if from_agent == to_agent:
        raise ToolError("Hand off to a different agent.")
    graph = db.get_graph()
    rows = graph.ro_query(queries.load("handoff_state"), {"iid": incident_id}).result_set
    if not rows:
        raise ToolError(f"No incident with id {incident_id!r} (ids look like 'INC-051').")
    [[state, last_seq, handoffs]] = rows
    try:
        merged = json.dumps(json.loads(state or "{}") | state_patch, sort_keys=True)
    except TypeError as e:
        raise ToolError(f"state_patch must be plain JSON (strings, numbers, lists): {e}") from e

    now, seq = _now(), (last_seq or 0) + 1
    event = AgentEvent(
        incident_id=incident_id,
        seq=seq,
        ts=now,
        agent=from_agent,
        kind=EventKind.HANDOFF,
        summary=note[:300],
        data={"from": from_agent.value, "to": to_agent.value, "note": note},
    )
    hid = handoff_id(incident_id, handoffs + 1)
    settings = get_settings()
    graph.query(
        queries.load("handoff_write"),
        {
            "iid": incident_id,
            "hid": hid,
            "now": now,
            "note": note,
            "state": merged,
            "event": event.to_node_props(),
            "prev_event": event_id(incident_id, last_seq) if last_seq else None,
            "from_id": agent_id(from_agent),
            "from": from_agent.value,
            "from_model": getattr(settings, f"model_{from_agent.value}"),
            "to_id": agent_id(to_agent),
            "to": to_agent.value,
            "to_model": getattr(settings, f"model_{to_agent.value}"),
        },
    )
    return hid


@_locked
def write_postmortem(incident_id: str, title: str, body: str) -> str:
    """Write the postmortem for a resolved incident and refresh its embedding. Returns its id."""
    title, body = title.strip(), body.strip()
    if not title or not body:
        raise ToolError("title and body must not be empty")
    graph = db.get_graph()
    rows = graph.ro_query(queries.load("postmortem_context"), {"iid": incident_id}).result_set
    if not rows:
        raise ToolError(f"No incident with id {incident_id!r} (ids look like 'INC-051').")
    [[status, inc_title, summary]] = rows
    if status != IncidentStatus.RESOLVED:
        raise ToolError(f"{incident_id} is {status}, not resolved: postmortems come after resolve.")
    [vector] = embeddings.embed([embeddings.incident_text(inc_title or title, summary or "")])
    pid = postmortem_id(incident_id)
    graph.query(
        queries.load("postmortem_write"),
        {
            "iid": incident_id,
            "pid": pid,
            "title": title,
            "body": body,
            "now": _now(),
            "agent_id": agent_id(AgentName.SCRIBE),
            "agent": AgentName.SCRIBE.value,
            "model": get_settings().model_scribe,
            "embedding": vector,
        },
    )
    return pid


@_locked
def record_runbook_outcome(runbook_id: str, incident_id: str, worked: bool) -> None:
    """Record whether a runbook fixed the incident; updates success/fail counts."""
    graph = db.get_graph()
    if not graph.ro_query(queries.load("runbook_exists"), {"rb": runbook_id}).result_set:
        raise ToolError(f"No runbook with id {runbook_id!r}: use an id from best_runbook.")
    if not graph.ro_query(queries.load("incident_status"), {"iid": incident_id}).result_set:
        raise ToolError(f"No incident with id {incident_id!r} (ids look like 'INC-051').")
    graph.query(
        queries.load("runbook_outcome"),
        {"rb": runbook_id, "iid": incident_id, "worked": worked, "now": _now()},
    )


# ═════════════════════════════════════════════════════════════════════════
# Actions: external side effects (Responder), always policy-checked first
# ═════════════════════════════════════════════════════════════════════════


# Actions (B07-B09) call out over HTTP through _post, which tests replace.
_post = httpx.post
HTTP_TIMEOUT = 5.0


def _action_context(graph: Graph, incident_id: str, person: str | None = None) -> list:
    rows = graph.ro_query(
        queries.load("action_context"), {"iid": incident_id, "pid": person}
    ).result_set
    if not rows:
        raise ToolError(f"No incident with id {incident_id!r} (ids look like 'INC-051').")
    return rows[0]


def _record_action(incident_id: str, result: ActionResult, summary: str, **data: object) -> None:
    """Every action, sent or not, lands on the timeline so the UI and the Scribe see it."""
    append_event(
        incident_id,
        EventKind.ACTION,
        summary if result.ok else f"{summary} (failed: {result.detail})",
        data={"action": result.action.value, "ok": result.ok, "url": result.url, **data},
    )


def page_owner(incident_id: str, handle: str, message: str) -> ActionResult:
    """Page a person on Discord about this incident."""
    graph = db.get_graph()
    title, severity, services, name, tz = _action_context(graph, incident_id, person_id(handle))
    if name is None:
        raise ToolError(f"No person with handle {handle!r}: use a handle from who_to_page.")
    url = get_settings().discord_webhook_url
    content = (
        f"\U0001f6a8 **{incident_id}** [{severity}] {title}\n"
        f"Paging **{name}** (@{handle}, {tz}) about {', '.join(sorted(set(services))) or 'it'}.\n"
        f"{message}"
    )[:2000]  # Discord's message limit
    if not url:
        result = ActionResult(
            action=ActionKind.PAGE, ok=False, detail="DISCORD_WEBHOOK_URL is not set; not sent"
        )
    else:
        try:
            r = _post(
                url,
                json={
                    "username": "PagerSage",
                    "content": content,
                    "allowed_mentions": {"parse": []},
                },
                timeout=HTTP_TIMEOUT,
            )
            ok = r.status_code < 300
            detail = f"Paged {handle} on Discord" if ok else f"Discord said {r.status_code}"
        except httpx.HTTPError as e:
            ok, detail = False, f"Discord unreachable: {type(e).__name__}"
        result = ActionResult(action=ActionKind.PAGE, ok=ok, detail=detail)
    _record_action(
        incident_id, result, f"Paged {handle} on Discord", handle=handle, message=message
    )
    return result


def _event_highlights(graph: Graph, incident_id: str) -> list[Highlight]:
    return [
        Highlight.model_validate_json(props.get("highlight") or "{}")
        for [props] in graph.ro_query(
            queries.load("incident_events"), {"iid": incident_id, "after_seq": 0}
        ).result_set
    ]


def merged_highlight(graph: Graph, incident_id: str) -> Highlight:
    """Every node and edge the incident's timeline events asked to highlight, first seen first."""
    nodes: dict[str, None] = {}
    edges: dict[tuple[str, str, str], None] = {}
    for h in _event_highlights(graph, incident_id):
        nodes.update(dict.fromkeys(h.nodes))
        edges.update(dict.fromkeys(tuple(e) for e in h.edges))
    return Highlight(nodes=list(nodes), edges=list(edges))


def root_cause_highlight(graph: Graph, incident_id: str) -> Highlight:
    """The newest highlight that walks a DEPENDS_ON path (what root_cause_path returns), else
    everything highlighted so far."""
    for h in reversed(_event_highlights(graph, incident_id)):
        if any(rel == Rel.DEPENDS_ON for _, rel, _ in h.edges):
            return h
    return merged_highlight(graph, incident_id)


_CHANGE_ID = re.compile(r"(dep|cfg)-\d{4}")
_SHA = re.compile(r"[0-9a-f]{7,40}")


def _issue_footer(incident_id: str, title: str, severity: str, h: Highlight) -> str:
    services = [n.removeprefix("svc:") for n in h.nodes if n.startswith("svc:")]
    changes = [n for n in h.nodes if _CHANGE_ID.fullmatch(n)]
    commits = [n[:7] for n in h.nodes if _SHA.fullmatch(n)]
    lines = ["", "---", f"**Incident:** {incident_id} [{severity}] {title}"]
    if services:
        lines.append(f"**Root-cause path:** {' → '.join(services)}")
    if changes:
        lines.append(f"**Suspect change:** {', '.join(changes)}")
    if commits:
        lines.append(f"**Commits:** {', '.join(commits)}")
    lines.append("_Opened by PagerSage from the incident graph._")
    return "\n".join(lines)


def open_issue(incident_id: str, title: str, body: str) -> ActionResult:
    """Open a GitHub issue in the demo repo with the root-cause path and suspect commit."""
    graph = db.get_graph()
    inc_title, severity, _, _, _ = _action_context(graph, incident_id)
    full_body = (
        body
        + "\n"
        + _issue_footer(incident_id, inc_title, severity, root_cause_highlight(graph, incident_id))
    )
    settings = get_settings()
    if not (settings.github_token and settings.github_issues_repo):
        result = ActionResult(
            action=ActionKind.ISSUE,
            ok=False,
            detail="GITHUB_TOKEN or GITHUB_ISSUES_REPO is not set; not opened",
        )
    else:
        try:
            r = _post(
                f"https://api.github.com/repos/{settings.github_issues_repo}/issues",
                json={"title": f"[{incident_id}] {title}"[:250], "body": full_body},
                headers={
                    "Authorization": f"Bearer {settings.github_token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
                timeout=HTTP_TIMEOUT,
            )
            if r.status_code == 201:
                url = r.json().get("html_url")
                result = ActionResult(
                    action=ActionKind.ISSUE, ok=True, detail=f"Opened {url}", url=url
                )
            else:
                result = ActionResult(
                    action=ActionKind.ISSUE, ok=False, detail=f"GitHub said {r.status_code}"
                )
        except httpx.HTTPError as e:
            result = ActionResult(
                action=ActionKind.ISSUE, ok=False, detail=f"GitHub unreachable: {type(e).__name__}"
            )
    _record_action(incident_id, result, "Opened a GitHub issue", title=title)
    return result


@_locked
def rollback(service_id: str, deploy_id: str) -> ActionResult:
    """Roll a service back past a deploy. Simulated: writes a rolled_back Deploy node."""
    graph = db.get_graph()
    _require_service(graph, service_id)
    rows = graph.ro_query(queries.load("rollback_context"), {"did": deploy_id}).result_set
    if not rows:
        raise ToolError(f"No deploy with id {deploy_id!r}: use a change_id from suspect_changes.")
    [[sid, status, _, previous, last_deploy]] = rows
    if sid != service_id:
        raise ToolError(f"{deploy_id} deployed {sid}, not {service_id}.")
    if status == DeployStatus.ROLLED_BACK:
        raise ToolError(f"{deploy_id} is already rolled back.")
    if previous is None:
        raise ToolError(f"Nothing to roll back to: {deploy_id} is {sid}'s first deploy on record.")
    new_id = deploy_id_for(_next_number(last_deploy))
    graph.query(
        queries.load("rollback_write"),
        {"old": deploy_id, "sid": sid, "new": new_id, "version": previous, "now": _now()},
    )
    name = sid.removeprefix("svc:")
    return ActionResult(
        action=ActionKind.ROLLBACK,
        ok=True,
        detail=f"Simulated rollback: {name} back to {previous} ({new_id} undoes {deploy_id})",
    )


def _revert_config(service_id: str, change_id: str) -> ActionResult:
    graph = db.get_graph()
    [[sid, key, old, new, status, last]] = graph.ro_query(
        queries.load("revert_config_context"), {"cid": change_id}
    ).result_set
    if sid != service_id:
        raise ToolError(f"{change_id} changed {sid}, not {service_id}.")
    if status == DeployStatus.ROLLED_BACK:
        raise ToolError(f"{change_id} is already reverted.")
    new_id = config_change_id(_next_number(last))
    graph.query(
        queries.load("revert_config_write"),
        {"old": change_id, "sid": sid, "new": new_id, "now": _now()},
    )
    return ActionResult(
        action=ActionKind.ROLLBACK,
        ok=True,
        detail=f"Simulated revert: {sid.removeprefix('svc:')} {key} back to {old} "
        f"({new_id} undoes {change_id}, which set {new})",
    )


# ═════════════════════════════════════════════════════════════════════════
# System functions: called by the API and orchestrator, never exposed to agents
# ═════════════════════════════════════════════════════════════════════════


MERGE_WINDOW = 600  # seconds: an alert joins a related incident opened at most this long ago


def append_event(
    incident_id: str,
    kind: EventKind,
    summary: str,
    ts: int | None = None,
    agent: AgentName | None = None,
    data: dict[str, object] | None = None,
    highlight: Highlight | None = None,
) -> AgentEvent:
    """Append one Event to an incident's timeline (seq = last + 1, NEXT from the last)."""
    with _write_lock:
        graph = db.get_graph()
        rows = graph.ro_query(queries.load("incident_last_seq"), {"iid": incident_id}).result_set
        if not rows:
            raise ToolError(f"No incident with id {incident_id!r} (ids look like 'INC-051').")
        last_seq = rows[0][1]
        event = AgentEvent(
            incident_id=incident_id,
            seq=(last_seq or 0) + 1,
            ts=_now() if ts is None else ts,
            agent=agent,
            kind=kind,
            summary=summary[:300],
            data=data or {},
            highlight=highlight or Highlight(),
        )
        graph.query(
            queries.load("event_append"),
            {
                "iid": incident_id,
                "event": event.to_node_props(),
                "prev_event": event_id(incident_id, last_seq) if last_seq else None,
            },
        )
        return event


def _next_number(last_id: str | None) -> int:
    """'alt-00060' -> 61, 'INC-050' -> 51, None -> 1."""
    return int(re.sub(r"\D", "", last_id)) + 1 if last_id else 1


def open_or_merge_incident(alert: AlertIn) -> OpenIncidentResult:
    """Store the alert; merge into an open incident from the last 10 minutes that has an alert
    on the same service or one within 3 DEPENDS_ON hops, otherwise open a new one."""
    with _write_lock:
        graph = db.get_graph()
        _require_service(graph, alert.service_id)
        [[last_alert, last_incident]] = graph.ro_query(queries.load("last_ids")).result_set
        aid = alert_id(_next_number(last_alert))
        props = {
            "id": aid,
            "ts": alert.ts,
            "signal": alert.signal.value,
            "value": alert.value,
            "threshold": alert.threshold,
            "severity": alert.severity.value,
        }
        found = graph.ro_query(
            queries.load("related_open_incident"),
            {"sid": alert.service_id, "ts": alert.ts, "window": MERGE_WINDOW},
        ).result_set
        name = alert.service_id.removeprefix("svc:")
        what = f"{name} {alert.signal.value} {alert.value:g} (threshold {alert.threshold:g})"
        if found:
            iid, merged = found[0][0], True
            graph.query(
                queries.load("incident_add_alert"),
                {
                    "iid": iid,
                    "sid": alert.service_id,
                    "severity": alert.severity.value,
                    "alert": props,
                },
            )
        else:
            iid, merged = new_incident_id(_next_number(last_incident)), False
            graph.query(
                queries.load("incident_open"),
                {
                    "iid": iid,
                    "title": what,
                    "severity": alert.severity.value,
                    "ts": alert.ts,
                    "sid": alert.service_id,
                    "alert": props,
                },
            )
        append_event(
            iid,
            EventKind.STATUS,
            f"Alert {aid}: {what}. "
            + ("Joined the open incident." if merged else "Incident opened."),
            ts=alert.ts,
            data={"alert_id": aid, "service_id": alert.service_id, "merged": merged},
            highlight=Highlight(nodes=[alert.service_id, aid]),
        )
        return OpenIncidentResult(incident_id=iid, alert_id=aid, merged=merged)


def live_weight(health: float) -> int:
    """DEPENDS_ON.weight for an edge into a service with this health: clip(round(100 * health),
    5, 100). Healthy = 100, sick = cheap, so weighted shortest paths run through the sick part
    of the system. (The plan's 100 * (1 - health) made sick services expensive instead.)"""
    return min(100, max(5, round(100 * health)))


def update_live_weights(service_id: str, health: float) -> None:
    """Set Service.health and DEPENDS_ON.weight = clip(round(100 * health), 5, 100)
    on edges into this service (integers)."""
    if not 0.0 <= health <= 1.0:
        raise ToolError(f"health must be between 0 and 1, got {health}")
    graph = db.get_graph()
    _require_service(graph, service_id)
    graph.query(
        queries.load("update_live_weights"),
        {"sid": service_id, "health": health, "weight": live_weight(health)},
    )


@_locked
def resolve_incident(incident_id: str, summary: str) -> None:
    """Mark the incident resolved; the orchestrator then runs the Scribe."""
    graph = db.get_graph()
    rows = graph.ro_query(queries.load("incident_status"), {"iid": incident_id}).result_set
    if not rows:
        raise ToolError(f"No incident with id {incident_id!r} (ids look like 'INC-051').")
    if rows[0][0] == IncidentStatus.RESOLVED:
        raise ToolError(f"{incident_id} is already resolved.")
    [[services]] = graph.query(
        queries.load("incident_resolve"), {"iid": incident_id, "now": _now(), "summary": summary}
    ).result_set
    for sid in sorted(set(services)):  # the alerts are over: live weights back to healthy
        update_live_weights(sid, 1.0)
    append_event(incident_id, EventKind.STATUS, f"Resolved: {summary}")


@_locked
def mark_needs_human(incident_id: str, reason: str) -> None:
    """An agent could not finish (refusal, tool-call cap, timeout, no handoff, API error):
    status needs_human and an error event saying why. The pipeline stops there."""
    graph = db.get_graph()
    rows = graph.ro_query(queries.load("incident_status"), {"iid": incident_id}).result_set
    if not rows:
        raise ToolError(f"No incident with id {incident_id!r} (ids look like 'INC-051').")
    graph.query(
        queries.load("incident_set_status"),
        {"iid": incident_id, "status": IncidentStatus.NEEDS_HUMAN.value},
    )
    append_event(incident_id, EventKind.ERROR, f"Needs a human: {reason}", data={"reason": reason})


@_locked
def revert_change(incident_id: str, change_id: str) -> ActionResult:
    """A person reverted the incident's cause from the UI (U09). Simulated: a deploy is rolled
    back (rollback), a config change gets a new ConfigChange setting the key back. Logs an
    action event and moves an open incident to mitigated."""
    graph = db.get_graph()
    rows = graph.ro_query(queries.load("incident_status"), {"iid": incident_id}).result_set
    if not rows:
        raise ToolError(f"No incident with id {incident_id!r} (ids look like 'INC-051').")
    status = rows[0][0]
    if status == IncidentStatus.RESOLVED:
        raise ToolError(f"{incident_id} is already resolved.")
    found = graph.ro_query(queries.load("change_details"), {"cid": change_id}).result_set
    if not found:
        raise ToolError(f"No change with id {change_id!r} (dep-0416, cfg-0061).")
    [[kind, sid, _]] = found
    revert = rollback if kind == ChangeType.DEPLOY else _revert_config
    result = revert(sid, change_id)
    append_event(
        incident_id,
        EventKind.ACTION,
        result.detail,
        data={"action": result.action.value, "ok": result.ok, "change_id": change_id},
        highlight=Highlight(nodes=[change_id, sid]),
    )
    graph.query(
        queries.load("incident_set_status"),
        {"iid": incident_id, "status": IncidentStatus.MITIGATED.value},
    )
    return result


# ═════════════════════════════════════════════════════════════════════════
# Which agent may call what (task A02 builds each agent's tool list from this)
# ═════════════════════════════════════════════════════════════════════════

AGENT_TOOLS: dict[AgentName, tuple[str, ...]] = {
    AgentName.TRIAGE: ("find_service", "blast_radius", "set_triage", "handoff"),
    AgentName.INVESTIGATOR: (
        "suspect_changes",
        "root_cause_path",
        "record_cause",
        "record_decision",
        "handoff",
    ),
    AgentName.HISTORIAN: (
        "similar_incidents",
        "best_runbook",
        "link_similar",
        "record_decision",
        "handoff",
    ),
    AgentName.RESPONDER: (
        "who_to_page",
        "check_policy",
        "page_owner",
        "open_issue",
        "rollback",
        "record_decision",
        "handoff",
    ),
    AgentName.SCRIBE: (
        "replay_incident",
        "best_runbook",
        "write_postmortem",
        "record_runbook_outcome",
    ),
    AgentName.BRAIN: (
        "find_service",
        "blast_radius",
        "who_knows",
        "bus_factor",
        "fragile_services",
        "replay_incident",
    ),
}

SYSTEM_FUNCTIONS: tuple[str, ...] = (
    "open_or_merge_incident",
    "update_live_weights",
    "resolve_incident",
    "mark_needs_human",
    "revert_change",
)
