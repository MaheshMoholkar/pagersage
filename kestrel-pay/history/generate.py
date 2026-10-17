"""Generate Kestrel Pay's 90 days of history (task K5): deploys, commits, config changes and
incidents as JSON Lines in history/export/, which PagerSage ingests at seed time.

Seeded and offline: the same seed and inputs give byte-identical files. All prose (commit
messages, incident titles, timelines, postmortems) comes from history/text_cache.json, written
once by an LLM (task K6); generating makes no API calls.

    cd backend && uv run python ../kestrel-pay/history/generate.py [--seed 7] [--out DIR]

The planted patterns the demo depends on (PLAN.md section 2) are built here on purpose and
asserted by tests/test_history.py:
  1. three past incidents caused by lowering payments-db max_pool_size (INC-042 is the last);
     "Raise pool + restart payments-svc" fixed all three
  2. ines is the only author on ledger-svc
  3. (topology) kafka has the highest betweenness
  4. checkout-api deploys the most, and a checkout-api deploy lands minutes before the last
     two pool incidents without causing them
"""

import argparse
import hashlib
import json
import random
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import yaml

ROOT = Path(__file__).resolve().parents[1]
EXPORT = ROOT / "history" / "export"
TEXT_CACHE = ROOT / "history" / "text_cache.json"

DEFAULT_SEED = 7
START = datetime(2026, 7, 14, tzinfo=UTC)
END = datetime(2026, 10, 12, tzinfo=UTC)  # exclusive; on-call week 1 starts here
START_TS, END_TS = int(START.timestamp()), int(END.timestamp())
DAYS = (END - START).days
FIRST_INCIDENT = 11  # INC-001..INC-010 predate the export window
CONFIG_CHANGES = 60  # scripted + random; the live scenario's change is then cfg-0061

INFRA_LANGUAGES = ("postgres", "redis", "kafka", "minio", "elasticsearch", "envoy")

# Regular deploys per service (incident causes and decoys come on top). checkout-api ships
# most: it is the noisy service whose deploys land near alerts (pattern 4).
DEPLOYS = {
    "edge": 10, "api-gateway": 24, "checkout-api": 52, "payments-svc": 34, "payments-db": 10,
    "fraud-svc": 24, "acquirer-gateway": 12, "ledger-svc": 20, "ledger-db": 9, "auth-svc": 18,
    "inventory-svc": 20, "inventory-db": 8, "pricing-svc": 16, "user-api": 22, "user-db": 7,
    "payouts-svc": 14, "reconciliation-job": 14, "webhooks-svc": 18, "notifications-svc": 16,
    "search-api": 12, "search-index": 5, "redis-cache": 6, "kafka": 7, "kafka-controller": 4,
    "schema-registry": 6, "object-store": 4,
}  # fmt: skip

# Commit author weights per service. Unlisted services: the owning team's engineers, equally.
# ledger-svc has exactly one author (pattern 2: bus factor).
BUS_FACTOR_SERVICE = "ledger-svc"
AFFINITY: dict[str, dict[str, int]] = {
    "payments-db": {"priya": 5, "hana": 2, "kwame": 1, "tomas": 1, "oliver": 1},
    "payments-svc": {"priya": 3, "tomas": 3, "oliver": 2, "hana": 2, "kwame": 2},
    "acquirer-gateway": {"kwame": 5, "hana": 2, "oliver": 1},
    "ledger-svc": {"ines": 1},
    "ledger-db": {"ines": 2, "elena": 2, "raj": 1},
    "payouts-svc": {"raj": 4, "elena": 2},
    "reconciliation-job": {"elena": 4, "raj": 2},
    "edge": {"jin": 3, "sofia": 2},
    "api-gateway": {"dev": 3, "jin": 2, "lukas": 1, "noor": 1},
    "redis-cache": {"lukas": 3, "sofia": 2, "jin": 1},
    "kafka": {"noor": 4, "jin": 2, "lukas": 1},
    "kafka-controller": {"noor": 3, "sofia": 1},
    "schema-registry": {"noor": 2, "dev": 2},
    "object-store": {"sofia": 2, "dev": 1},
    "checkout-api": {"ben": 4, "mateo": 3, "leila": 3, "yuki": 2, "amara": 2},
    "inventory-svc": {"yuki": 4, "leila": 2},
    "inventory-db": {"yuki": 3, "ben": 1},
    "pricing-svc": {"mateo": 4, "leila": 2},
    "fraud-svc": {"arjun": 4, "chloe": 2, "diego": 2},
    "auth-svc": {"fatima": 4, "diego": 2, "chloe": 1},
    "user-api": {"omar": 3, "nina": 2, "kai": 1},
    "user-db": {"omar": 2, "grace": 1},
    "search-api": {"kai": 3, "lucy": 1},
    "search-index": {"kai": 2, "omar": 1},
    "webhooks-svc": {"nina": 4, "omar": 2, "grace": 1},
    "notifications-svc": {"lucy": 3, "kai": 2},
}
CROSS_TEAM_RATE = 0.04  # platform engineers bump base images etc. in other teams' services

# Config history. Keys the scripted incidents change are left alone by the random changes.
INITIAL = {("payments-db", "max_pool_size"): 150}  # before the first scripted change
# (day, hour UTC, service, key, value, by): scripted changes that are not part of an incident.
BASELINE_CHANGES = (
    (4, 10, "payments-db", "max_pool_size", 200, "priya"),  # sized for peak; the incidents undo it
)
NEVER_CHANGED = {
    ("acquirer-gateway", "backup_acquirer"), ("object-store", "versioning"),
    ("auth-svc", "bcrypt_cost"), ("kafka-controller", "quorum_size"),
    ("kafka", "min_insync_replicas"), ("reconciliation-job", "tolerance_cents"),
}  # fmt: skip
ALTERNATIVES = {
    "waf_mode": ["block", "detect"],
    "tls_min_version": ["1.2", "1.3"],
    "email_provider": ["postmark", "sendgrid"],
    "sms_provider": ["twilio", "vonage"],
    "maxmemory_policy": ["volatile-lru", "allkeys-lru"],
    "compatibility": ["BACKWARD", "FULL"],
    "payout_cutoff_utc": ["15:00", "16:00", "17:00"],
    "schedule_utc": ["02:00", "02:30", "03:00"],
}


# ── the incident catalog ──────────────────────────────────────────────────


@dataclass(frozen=True)
class A:
    """An alert, `at` minutes after the incident opens."""

    at: int
    service: str
    signal: str
    value: float
    threshold: float
    severity: str


@dataclass(frozen=True)
class Cfg:
    """Cause: a config change made `lag` minutes before the incident."""

    service: str
    key: str
    value: Any
    by: str


@dataclass(frozen=True)
class Dep:
    """Cause: a deploy whose last commit (by `by`) carries the variant's `commit` message."""

    service: str
    by: str
    rolled_back: bool = True


@dataclass(frozen=True)
class Spec:
    day: int  # days after START
    hour: int  # UTC
    kind: str  # key into text_cache.json "incidents"; the n-th of a kind uses variant n
    severity: str
    affected: tuple[str, ...]  # first one is the owning service (resolver = its on-call)
    alerts: tuple[A, ...]
    cause: Cfg | Dep | None = None
    runbooks: tuple[tuple[str, bool, int], ...] = ()  # (slug, worked, minute)
    configs: tuple[tuple[int, str, str, Any], ...] = ()  # (minute, service, key, value) by resolver
    resolver: str | None = None
    decoy: bool = False  # a harmless checkout-api deploy minutes before (pattern 4)


POOL = ("payments-db", "payments-svc", "checkout-api")
INCIDENTS: tuple[Spec, ...] = (
    Spec(2, 14, "checkout_bad_deploy", "sev2", ("checkout-api",),
         (A(0, "checkout-api", "error_rate", 4.8, 1.0, "sev2"),), Dep("checkout-api", "ben")),
    Spec(4, 9, "acquirer_outage", "sev1", ("acquirer-gateway", "payments-svc", "checkout-api"),
         (A(0, "acquirer-gateway", "latency_p99", 4200, 2500, "sev2"),
          A(2, "checkout-api", "error_rate", 6.1, 1.0, "sev1")),
         runbooks=(("switch-acquirer-route", True, 14),),
         configs=((14, "acquirer-gateway", "primary_acquirer", "meridian"),
                  (95, "acquirer-gateway", "primary_acquirer", "northbank"))),
    Spec(6, 20, "webhooks_retry_storm", "sev2", ("webhooks-svc", "kafka"),
         (A(0, "webhooks-svc", "latency_p99", 9800, 5000, "sev2"),
          A(6, "kafka", "saturation", 0.88, 0.85, "sev3")),
         Cfg("webhooks-svc", "max_retries", 30, "nina"),
         runbooks=(("drain-webhooks-backlog", True, 22),),
         configs=((15, "webhooks-svc", "max_retries", 8),)),
    Spec(9, 3, "search_index_red", "sev3", ("search-index", "search-api"),
         (A(0, "search-api", "error_rate", 12.0, 2.0, "sev3"),), Dep("search-index", "kai")),
    Spec(11, 13, "redis_maxmemory", "sev1", ("redis-cache", "auth-svc", "checkout-api"),
         (A(0, "redis-cache", "saturation", 0.99, 0.9, "sev2"),
          A(3, "auth-svc", "error_rate", 9.5, 1.0, "sev1"),
          A(4, "checkout-api", "error_rate", 3.2, 1.0, "sev2")),
         Cfg("redis-cache", "maxmemory", "4gb", "lukas"),
         runbooks=(("restore-redis-maxmemory", True, 18),),
         configs=((18, "redis-cache", "maxmemory", "8gb"),)),
    Spec(13, 10, "payments_bad_deploy", "sev1", ("payments-svc", "checkout-api"),
         (A(0, "payments-svc", "error_rate", 5.5, 1.0, "sev1"),
          A(1, "checkout-api", "error_rate", 4.9, 1.0, "sev1")), Dep("payments-svc", "oliver")),
    Spec(15, 16, "notifications_provider", "sev3", ("notifications-svc",),
         (A(0, "notifications-svc", "error_rate", 38.0, 5.0, "sev3"),)),
    Spec(17, 12, "inventory_index_dropped", "sev2",
         ("inventory-db", "inventory-svc", "checkout-api"),
         (A(0, "inventory-svc", "latency_p99", 1850, 200, "sev2"),
          A(3, "checkout-api", "latency_p99", 2900, 800, "sev2")),
         Dep("inventory-db", "yuki", rolled_back=False),
         runbooks=(("fix-inventory-db-slow-queries", True, 27),)),
    # INC-019: first pool exhaustion. Failover is tried first and does not help.
    Spec(19, 2, "pool_exhaustion", "sev1", POOL,
         (A(0, "payments-db", "saturation", 1.0, 0.9, "sev2"),
          A(2, "checkout-api", "error_rate", 7.9, 1.0, "sev1")),
         Cfg("payments-db", "max_pool_size", 120, "tomas"),
         runbooks=(("failover-payments-db", False, 21), ("raise-payments-db-pool", True, 44)),
         configs=((44, "payments-db", "max_pool_size", 200),), resolver="hana"),
    Spec(21, 15, "fraud_model_latency", "sev2", ("fraud-svc", "payments-svc"),
         (A(0, "fraud-svc", "latency_p99", 410, 150, "sev2"),
          A(2, "payments-svc", "latency_p99", 1300, 600, "sev2")), Dep("fraud-svc", "arjun"),
         runbooks=(("fraud-rules-fallback", True, 9),),
         configs=((9, "fraud-svc", "scoring_mode", "rules"),
                  (31, "fraud-svc", "scoring_mode", "model"))),
    Spec(23, 11, "checkout_bad_deploy", "sev1", ("checkout-api",),
         (A(0, "checkout-api", "error_rate", 11.3, 1.0, "sev1"),), Dep("checkout-api", "mateo")),
    Spec(25, 18, "gateway_timeout", "sev2", ("api-gateway", "checkout-api"),
         (A(0, "api-gateway", "error_rate", 3.9, 1.0, "sev2"),),
         Cfg("api-gateway", "upstream_timeout_ms", 800, "dev"),
         runbooks=(("raise-api-gateway-timeouts", True, 16),),
         configs=((16, "api-gateway", "upstream_timeout_ms", 3000),)),
    Spec(28, 8, "ledger_consumer_stuck", "sev2", ("ledger-svc", "payouts-svc"),
         (A(0, "ledger-svc", "latency_p99", 54000, 5000, "sev2"),), Dep("ledger-svc", "ines"),
         runbooks=(("replay-ledger-events", True, 35),), resolver="ines"),
    Spec(30, 23, "auth_key_expiry", "sev1", ("auth-svc", "api-gateway"),
         (A(0, "auth-svc", "error_rate", 22.0, 1.0, "sev1"),
          A(1, "api-gateway", "error_rate", 14.0, 1.0, "sev1")),
         runbooks=(("rotate-auth-signing-key", True, 19),)),
    Spec(32, 5, "kafka_disk_full", "sev2", ("kafka", "ledger-svc", "webhooks-svc"),
         (A(0, "kafka", "saturation", 0.95, 0.85, "sev2"),
          A(5, "ledger-svc", "latency_p99", 21000, 5000, "sev2")),
         Cfg("kafka", "retention_hours", 720, "noor"),
         runbooks=(("reassign-kafka-partitions", True, 31),),
         configs=((24, "kafka", "retention_hours", 168),)),
    Spec(34, 14, "edge_waf_block", "sev1", ("edge", "checkout-api"),
         (A(0, "edge", "error_rate", 18.0, 2.0, "sev1"),), Dep("edge", "sofia")),
    Spec(36, 10, "acquirer_timeout_config", "sev2", ("acquirer-gateway", "payments-svc"),
         (A(0, "payments-svc", "error_rate", 3.4, 1.0, "sev2"),),
         Cfg("acquirer-gateway", "read_timeout_ms", 1000, "kwame"),
         runbooks=(("switch-acquirer-route", False, 12),),
         configs=((12, "acquirer-gateway", "primary_acquirer", "meridian"),
                  (24, "acquirer-gateway", "read_timeout_ms", 2500),
                  (27, "acquirer-gateway", "primary_acquirer", "northbank"))),
    Spec(38, 16, "payouts_batch_failed", "sev2", ("payouts-svc", "ledger-svc"),
         (A(0, "payouts-svc", "error_rate", 100.0, 1.0, "sev2"),), Dep("payouts-svc", "raj")),
    Spec(40, 21, "webhooks_bad_deploy", "sev2", ("webhooks-svc",),
         (A(0, "webhooks-svc", "error_rate", 27.0, 5.0, "sev2"),), Dep("webhooks-svc", "omar")),
    Spec(43, 7, "search_index_red", "sev3", ("search-index", "search-api"),
         (A(0, "search-index", "saturation", 0.97, 0.9, "sev3"),
          A(2, "search-api", "error_rate", 8.0, 2.0, "sev3"))),
    # INC-031: second pool exhaustion, with a checkout-api deploy just before it.
    Spec(45, 15, "pool_exhaustion", "sev1", POOL,
         (A(0, "payments-db", "saturation", 0.99, 0.9, "sev2"),
          A(1, "checkout-api", "error_rate", 9.4, 1.0, "sev1"),
          A(2, "payments-svc", "latency_p99", 2600, 600, "sev2")),
         Cfg("payments-db", "max_pool_size", 100, "oliver"),
         runbooks=(("raise-payments-db-pool", True, 17),),
         configs=((17, "payments-db", "max_pool_size", 200),), resolver="priya", decoy=True),
    Spec(47, 12, "fraud_false_declines", "sev2", ("fraud-svc", "payments-svc"),
         (A(0, "payments-svc", "error_rate", 6.6, 1.0, "sev2"),),
         Cfg("fraud-svc", "block_threshold", 0.6, "arjun"),
         configs=((14, "fraud-svc", "block_threshold", 0.85),)),
    Spec(50, 17, "checkout_bad_deploy", "sev2", ("checkout-api",),
         (A(0, "checkout-api", "latency_p99", 3100, 800, "sev2"),), Dep("checkout-api", "leila")),
    Spec(52, 4, "redis_primary_down", "sev1",
         ("redis-cache", "auth-svc", "checkout-api", "webhooks-svc"),
         (A(0, "redis-cache", "error_rate", 100.0, 1.0, "sev1"),
          A(1, "auth-svc", "error_rate", 31.0, 1.0, "sev1")),
         runbooks=(("failover-redis-cache", True, 11),)),
    Spec(54, 13, "schema_registry_reject", "sev1",
         ("schema-registry", "kafka", "payments-svc", "checkout-api"),
         (A(0, "payments-svc", "error_rate", 4.1, 1.0, "sev1"),
          A(2, "checkout-api", "error_rate", 2.7, 1.0, "sev2")), Dep("schema-registry", "dev")),
    Spec(56, 3, "reconciliation_mismatch", "sev3", ("reconciliation-job",),
         (A(0, "reconciliation-job", "error_rate", 14.0, 0.5, "sev3"),),
         Dep("reconciliation-job", "elena")),
    Spec(58, 19, "acquirer_outage", "sev1", ("acquirer-gateway", "payments-svc", "checkout-api"),
         (A(0, "acquirer-gateway", "error_rate", 35.0, 2.0, "sev1"),
          A(1, "checkout-api", "error_rate", 8.8, 1.0, "sev1")),
         runbooks=(("switch-acquirer-route", True, 9),),
         configs=((9, "acquirer-gateway", "primary_acquirer", "meridian"),
                  (64, "acquirer-gateway", "primary_acquirer", "northbank"))),
    Spec(61, 11, "inventory_n_plus_one", "sev2", ("inventory-svc", "inventory-db", "checkout-api"),
         (A(0, "inventory-svc", "latency_p99", 920, 200, "sev2"),
          A(2, "inventory-db", "saturation", 0.93, 0.85, "sev3")), Dep("inventory-svc", "yuki")),
    Spec(63, 9, "user_api_bad_deploy", "sev3", ("user-api",),
         (A(0, "user-api", "error_rate", 6.0, 2.0, "sev3"),), Dep("user-api", "kai")),
    Spec(65, 22, "kafka_controller_flap", "sev2",
         ("kafka-controller", "kafka", "payments-svc", "ledger-svc"),
         (A(0, "kafka", "error_rate", 3.0, 0.5, "sev2"),
          A(4, "payments-svc", "latency_p99", 900, 600, "sev3")),
         Dep("kafka-controller", "noor", rolled_back=False),
         runbooks=(("restart-kafka-controller", True, 26),)),
    Spec(67, 13, "checkout_bad_deploy", "sev2", ("checkout-api",),
         (A(0, "checkout-api", "error_rate", 3.6, 1.0, "sev2"),), Dep("checkout-api", "ben")),
    # INC-042: third pool exhaustion, the precedent the live demo repeats.
    Spec(70, 14, "pool_exhaustion", "sev1", POOL,
         (A(0, "payments-db", "saturation", 1.0, 0.9, "sev2"),
          A(2, "checkout-api", "error_rate", 8.6, 1.0, "sev1")),
         Cfg("payments-db", "max_pool_size", 90, "kwame"),
         runbooks=(("raise-payments-db-pool", True, 12),),
         configs=((12, "payments-db", "max_pool_size", 200),), resolver="priya", decoy=True),
    Spec(72, 16, "webhooks_endpoint_storm", "sev3", ("webhooks-svc",),
         (A(0, "webhooks-svc", "latency_p99", 7200, 5000, "sev3"),),
         runbooks=(("drain-webhooks-backlog", True, 20),)),
    Spec(74, 10, "notifications_provider", "sev3", ("notifications-svc",),
         (A(0, "notifications-svc", "error_rate", 52.0, 5.0, "sev3"),)),
    Spec(76, 6, "ledger_db_bloat", "sev2", ("ledger-db", "ledger-svc"),
         (A(0, "ledger-db", "latency_p99", 840, 100, "sev2"),
          A(6, "ledger-svc", "latency_p99", 16000, 5000, "sev2")),
         runbooks=(("replay-ledger-events", True, 48),), resolver="ines"),
    Spec(79, 12, "pricing_fx_stale", "sev3", ("pricing-svc", "checkout-api"),
         (A(0, "pricing-svc", "error_rate", 2.5, 1.0, "sev3"),), Dep("pricing-svc", "mateo")),
    Spec(81, 15, "payments_bad_deploy", "sev2", ("payments-svc",),
         (A(0, "payments-svc", "latency_p99", 1900, 600, "sev2"),), Dep("payments-svc", "tomas")),
    Spec(84, 9, "gateway_bad_deploy", "sev2", ("api-gateway", "user-api"),
         (A(0, "api-gateway", "error_rate", 2.8, 1.0, "sev2"),), Dep("api-gateway", "jin")),
    Spec(86, 18, "checkout_bad_deploy", "sev2", ("checkout-api",),
         (A(0, "checkout-api", "error_rate", 5.2, 1.0, "sev2"),), Dep("checkout-api", "yuki")),
    Spec(88, 2, "object_store_full", "sev3", ("object-store", "reconciliation-job"),
         (A(0, "object-store", "saturation", 0.98, 0.9, "sev3"),)),
)  # fmt: skip


# ── generation ────────────────────────────────────────────────────────────


def fmt(value: Any) -> str:
    """A config value as it reads in config.yaml."""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def fmt_alert(a: A) -> str:
    if a.signal == "error_rate":
        return f"{a.value:g}%"
    if a.signal == "saturation":
        return f"{a.value * 100:.0f}%"
    return f"{a.value:,.0f} ms"


def _join(ids: list[str]) -> str:
    return ids[0] if len(ids) == 1 else ", ".join(ids[:-1]) + " and " + ids[-1]


class _Generator:
    def __init__(self, seed: int) -> None:
        self.seed = seed
        self.rng = random.Random(seed)
        load = lambda p: yaml.safe_load(p.read_text(encoding="utf-8"))  # noqa: E731
        topology = load(ROOT / "company" / "topology.yaml")["services"]
        self.services = [s["name"] for s in topology]
        self.languages = {s["name"]: s["language"] for s in topology}
        org = load(ROOT / "company" / "org.yaml")
        self.on_call = org["on_call"]
        self.people = {p["handle"]: p for p in org["people"]}
        self.owner = {svc: t["slug"] for t in org["teams"] for svc in t["owns"]}
        self.engineers = {
            t["slug"]: [
                p["handle"]
                for p in org["people"]
                if p["team"] == t["slug"] and "manager" not in p["role"]
            ]
            for t in org["teams"]
        }
        self.config = {s: load(ROOT / "services" / s / "config.yaml") for s in self.services}
        self.text = json.loads(TEXT_CACHE.read_text(encoding="utf-8"))
        self.deploys: list[dict] = []
        self.commits: list[dict] = []
        self.changes: list[dict] = []
        self.incidents: list[dict] = []

    # time ──────────────────────────────────────────────────────────────

    def work_ts(self, handle: str) -> int:
        """A random weekday working-hours moment for this person, inside the window."""
        tz = ZoneInfo(self.people[handle]["timezone"])
        while True:
            day = START.date() + timedelta(days=self.rng.randrange(DAYS))
            local = datetime(
                day.year, day.month, day.day,
                self.rng.randint(9, 17), self.rng.randint(0, 59), self.rng.randint(0, 59),
                tzinfo=tz,
            )  # fmt: skip
            ts = int(local.timestamp())
            if local.weekday() < 5 and START_TS <= ts < END_TS - 6 * 3600:
                return ts

    def on_call_at(self, team: str, ts: int) -> str:
        """Who was on call, extending the rotation backwards from its start date."""
        rota = self.on_call["teams"][team]
        start: date = self.on_call["start"]
        start_ts = int(datetime(start.year, start.month, start.day, tzinfo=UTC).timestamp())
        weeks = (ts - start_ts) // (self.on_call["rotation_days"] * 86400)
        return rota[weeks % len(rota)]

    # people and text ───────────────────────────────────────────────────

    def author(self, service: str) -> str:
        team = self.owner[service]
        cross_team_ok = service != BUS_FACTOR_SERVICE and team != "platform"
        if cross_team_ok and self.rng.random() < CROSS_TEAM_RATE:
            return self.rng.choice(self.engineers["platform"])
        weights = AFFINITY.get(service) or {h: 1 for h in self.engineers[team]}
        handles = list(weights)
        return self.rng.choices(handles, weights=[weights[h] for h in handles])[0]

    def message(self, service: str, author: str) -> str:
        pool = self.text["commit_messages"]
        if self.people[author]["team"] != self.owner[service] or self.rng.random() < 0.25:
            return self.rng.choice(pool["_generic"])
        return self.rng.choice(pool[service])

    def name(self, handle: str) -> str:
        return self.people[handle]["name"]

    # changes ───────────────────────────────────────────────────────────

    def commit(self, service: str, author: str, before: int, message: str | None = None) -> dict:
        ts = max(START_TS, before - self.rng.randint(20 * 60, 72 * 3600))
        message = message or self.message(service, author)
        sha = hashlib.sha1(
            f"{self.seed}:{len(self.commits)}:{service}:{author}:{ts}:{message}".encode()
        ).hexdigest()
        lines = min(2000, int(self.rng.lognormvariate(3.6, 1.1)) + 1)
        files = max(1, min(40, round(lines / self.rng.uniform(15, 60))))
        c = {
            "sha": sha,
            "message": message,
            "author": author,
            "ts": ts,
            "files_changed": files,
            "lines_changed": lines,
        }
        self.commits.append(c)
        return c

    def commit_count(self, service: str) -> int:
        if self.languages[service] in INFRA_LANGUAGES:
            return self.rng.choice([1, 1, 2, 2, 3])
        return self.rng.choices(range(1, 9), weights=[10, 14, 17, 17, 14, 11, 9, 8])[0]

    def deploy(
        self,
        service: str,
        ts: int | None = None,
        *,
        bad_commit: tuple[str, str] | None = None,  # (author, message), shipped last
        rolled_back: bool = False,
    ) -> dict:
        team = self.owner[service]
        n = self.commit_count(service) - (1 if bad_commit else 0)
        authors = [self.author(service) for _ in range(max(0, n))]
        if bad_commit:
            deployer = bad_commit[0]
        elif authors[-1] in self.engineers[team] and self.rng.random() < 0.8:
            deployer = authors[-1]
        else:
            deployer = self.rng.choice(self.engineers[team])
        ts_given = ts is not None
        ts = ts if ts is not None else self.work_ts(deployer)
        commits = [self.commit(service, a, ts) for a in authors]
        commits.sort(key=lambda c: c["ts"])
        if bad_commit:
            commits.append(self.commit(service, bad_commit[0], ts, bad_commit[1]))
        d = {
            "service": service,
            "ts": ts,
            "status": "rolled_back" if rolled_back else "ok",
            "deployed_by": deployer,
            "commits": commits,
            "scripted": ts_given,
        }
        self.deploys.append(d)
        return d

    def change(self, service: str, key: str, new: Any, ts: int, by: str) -> dict:
        c = {"service": service, "key": key, "new": new, "ts": ts, "made_by": by}
        self.changes.append(c)
        return c

    # the parts ─────────────────────────────────────────────────────────

    def run(self) -> dict[str, list[dict]]:
        for day, hour, service, key, value, by in BASELINE_CHANGES:
            self.change(service, key, value, START_TS + day * 86400 + hour * 3600, by)
        drafts = [self.incident(n, spec) for n, spec in enumerate(INCIDENTS)]
        for service in self.services:
            for _ in range(DEPLOYS[service]):
                self.deploy(service)
        self.ensure_two_authors()
        self.random_config_changes()
        self.finalize()
        for draft in drafts:
            self.incidents.append(self.render(draft))
        return self.export()

    def incident(self, n: int, spec: Spec) -> dict:
        kind_seen = sum(1 for s in INCIDENTS[:n] if s.kind == spec.kind)
        variant = self.text["incidents"][spec.kind][kind_seen]
        duration = variant["timeline"][-1][0]
        opened = START_TS + spec.day * 86400 + spec.hour * 3600 + self.rng.randint(0, 59) * 60
        resolver = spec.resolver or self.on_call_at(self.owner[spec.affected[0]], opened)
        draft: dict[str, Any] = {
            "n": n, "spec": spec, "variant": variant, "opened": opened, "duration": duration,
            "resolver": resolver, "lag": self.rng.randint(6, 18), "cause": None, "decoy": None,
        }  # fmt: skip
        cause_ts = opened - draft["lag"] * 60 - self.rng.randint(0, 59)
        if isinstance(spec.cause, Cfg):
            c = spec.cause
            draft["cause"] = self.change(c.service, c.key, c.value, cause_ts, c.by)
        elif isinstance(spec.cause, Dep):
            c = spec.cause
            bad = (c.by, variant["commit"])
            draft["cause"] = self.deploy(
                c.service, cause_ts, bad_commit=bad, rolled_back=c.rolled_back
            )
        if spec.decoy:
            draft["decoy_lag"] = self.rng.randint(5, 9)
            draft["decoy"] = self.deploy("checkout-api", opened - draft["decoy_lag"] * 60)
        for minute, service, key, value in spec.configs:
            self.change(service, key, value, opened + minute * 60, resolver)
        return draft

    def ensure_two_authors(self) -> None:
        """Only ledger-svc may have a single author (pattern 2). Fixes up a regular commit,
        never one an incident's text names."""
        for service in self.services:
            if service == BUS_FACTOR_SERVICE:
                continue
            deploys = [d for d in self.deploys if d["service"] == service]
            authors = sorted({c["author"] for d in deploys for c in d["commits"]})
            if len(authors) < 2:
                pool = AFFINITY.get(service) or {h: 1 for h in self.engineers[self.owner[service]]}
                regular = [c for d in deploys if not d["scripted"] for c in d["commits"]]
                regular[-1]["author"] = next(h for h in pool if h not in authors)

    def random_config_changes(self) -> None:
        scripted = {(c["service"], c["key"]) for c in self.changes}
        candidates = [
            (svc, key)
            for svc in self.services
            for key, value in self.config[svc].items()
            if (svc, key) not in scripted
            and (svc, key) not in NEVER_CHANGED
            and (isinstance(value, int | float) or key in ALTERNATIVES)
        ]
        picks = self.rng.sample(candidates * 2, CONFIG_CHANGES - len(self.changes))
        for svc, key in picks:
            by = self.rng.choice(self.engineers[self.owner[svc]])
            c = self.change(svc, key, None, self.work_ts(by), by)
            c["random"] = True

        by_key: dict[tuple[str, str], list[dict]] = {}
        for c in sorted(self.changes, key=lambda c: c["ts"]):
            by_key.setdefault((c["service"], c["key"]), []).append(c)
        for (svc, key), chain in by_key.items():
            final = self.config[svc][key]
            if chain[0].get("random"):
                # Walk back from today's value so the history ends at config.yaml.
                value = final
                for c in reversed(chain):
                    c["new"], value = value, self.previous(key, value)
                    c["old"] = value
            else:
                value = INITIAL.get((svc, key), final)
                for c in chain:
                    c["old"], value = value, c["new"]
                if fmt(value) != fmt(final):
                    raise ValueError(f"{svc}.{key} history ends at {value}, config says {final}")

    def previous(self, key: str, value: Any) -> Any:
        if isinstance(value, bool):
            return not value
        if isinstance(value, int):
            options = {max(1, round(value * f)) for f in (0.5, 0.75, 1.5, 2)} - {value}
        elif isinstance(value, float):
            options = {round(value * f, 2) for f in (0.8, 0.9, 1.1)} - {value}
            options = {o for o in options if value >= 1 or 0 < o < 1}
        else:
            options = set(ALTERNATIVES[key]) - {value}
        return self.rng.choice(sorted(options))

    def finalize(self) -> None:
        """Ids in time order, and versions that only go up."""
        self.deploys.sort(key=lambda d: (d["ts"], d["service"]))
        versions = {
            s: [self.rng.randint(1, 4), self.rng.randint(0, 30), self.rng.randint(0, 9)]
            for s in self.services
        }
        for i, d in enumerate(self.deploys, start=1):
            v = versions[d["service"]]
            d["prev_version"] = "v{}.{}.{}".format(*v)
            if self.rng.random() < 0.25:
                v[1], v[2] = v[1] + 1, 0
            else:
                v[2] += 1
            d["version"] = "v{}.{}.{}".format(*v)
            d["id"] = f"dep-{i:04d}"
        self.changes.sort(key=lambda c: (c["ts"], c["service"], c["key"]))
        for i, c in enumerate(self.changes, start=1):
            c["id"] = f"cfg-{i:04d}"
        if len(self.deploys) > 9999 or len(self.changes) > 9999:
            raise ValueError("ids would overflow 4 digits")

    def render(self, draft: dict) -> dict:
        spec: Spec = draft["spec"]
        n, v, opened = draft["n"], draft["variant"], draft["opened"]
        iid = f"INC-{FIRST_INCIDENT + n:03d}"
        earlier = [(f"INC-{FIRST_INCIDENT + k:03d}", s.kind) for k, s in enumerate(INCIDENTS[:n])]
        same = [i for i, kind in earlier if kind == spec.kind]
        ctx: dict[str, Any] = {
            "id": iid,
            "duration": draft["duration"],
            "lag": draft["lag"],
            "resolver": self.name(draft["resolver"]),
            "resolver_first": self.name(draft["resolver"]).split()[0],
            "last_same": same[-1] if same else "",
            "prev_same": _join(same) if same else "",
            "last": {kind: i for i, kind in earlier},
        }
        ctx |= {f"a{k}": fmt_alert(a) for k, a in enumerate(spec.alerts)}
        cause = draft["cause"]
        if cause is not None:
            by = cause.get("made_by") or cause["commits"][-1]["author"]
            ctx |= {"cause_author": self.name(by), "cause_first": self.name(by).split()[0]}
        if isinstance(spec.cause, Cfg):
            ctx |= {"key": cause["key"], "old": fmt(cause["old"]), "new": fmt(cause["new"])}
            ctx["cfg"] = cause["id"]
        elif isinstance(spec.cause, Dep):
            ctx |= {"deploy": cause["id"], "version": cause["version"]}
            ctx |= {"prev_version": cause["prev_version"], "sha": cause["commits"][-1]["sha"][:7]}
        if decoy := draft["decoy"]:
            ctx |= {"decoy_deploy": decoy["id"], "decoy_version": decoy["version"]}
            ctx |= {"decoy_author": self.name(decoy["deployed_by"])}
            ctx["decoy_lag"] = draft["decoy_lag"]
        fill = lambda s: s.format_map(ctx)  # noqa: E731

        resolved = opened + draft["duration"] * 60
        alerts = [
            {
                "service": a.service,
                "signal": a.signal,
                "value": a.value,
                "threshold": a.threshold,
                "severity": a.severity,
                "ts": opened + a.at * 60,
            }
            for a in spec.alerts
        ]
        pm_ts = min(resolved + self.rng.randint(20, 60) * 3600, END_TS - 600)
        return {
            "id": iid,
            "title": fill(v["title"]),
            "severity": spec.severity,
            "status": "resolved",
            "opened_at": opened,
            "resolved_at": resolved,
            "summary": fill(v["summary"]),
            "affected": list(spec.affected),
            "caused_by": [{"change": cause["id"], "confidence": 1.0}] if cause else [],
            "alerts": alerts,
            "timeline": [
                {"ts": opened + m * 60, "kind": kind, "text": fill(text)}
                for m, kind, text in v["timeline"]
            ],
            "runbooks": [
                {"runbook": slug, "worked": worked, "ts": opened + m * 60}
                for slug, worked, m in spec.runbooks
            ],
            "resolved_by": draft["resolver"],
            "postmortem": {
                "title": fill(v["postmortem"]["title"]),
                "body": fill(v["postmortem"]["body"]).rstrip("\n"),
                "ts": pm_ts,
                "author": draft["resolver"],
            },
        }

    def export(self) -> dict[str, list[dict]]:
        alert_n = 0
        for inc in self.incidents:
            numbered = []
            for a in inc["alerts"]:
                alert_n += 1
                numbered.append({"id": f"alt-{alert_n:05d}", **a})
            inc["alerts"] = numbered
        commits = sorted(self.commits, key=lambda c: (c["ts"], c["sha"]))
        return {
            "deploys": [
                {
                    "id": d["id"],
                    "service": d["service"],
                    "version": d["version"],
                    "ts": d["ts"],
                    "status": d["status"],
                    "env": "prod",
                    "deployed_by": d["deployed_by"],
                    "commits": [c["sha"] for c in d["commits"]],
                }
                for d in self.deploys
            ],
            "commits": commits,
            "config_changes": [
                {
                    "id": c["id"],
                    "service": c["service"],
                    "key": c["key"],
                    "old": fmt(c["old"]),
                    "new": fmt(c["new"]),
                    "ts": c["ts"],
                    "made_by": c["made_by"],
                }
                for c in self.changes
            ],
            "incidents": self.incidents,
        }


def generate(seed: int = DEFAULT_SEED) -> dict[str, list[dict]]:
    """The whole history as plain dicts, keyed by export file stem."""
    return _Generator(seed).run()


def render(seed: int = DEFAULT_SEED) -> dict[str, str]:
    """Export file name -> exact file content."""
    return {
        f"{name}.jsonl": "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
        for name, rows in generate(seed).items()
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Generate Kestrel Pay's history export.")
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED)
    ap.add_argument("--out", type=Path, default=EXPORT)
    args = ap.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)
    for name, text in render(args.seed).items():
        (args.out / name).write_text(text, encoding="utf-8", newline="\n")
        print(f"{name}: {text.count(chr(10))} rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
