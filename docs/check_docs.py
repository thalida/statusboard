#!/usr/bin/env python3
"""Cross-check the API schema against the data model.

Every field an endpoint returns must come from a ModelSerializer. It is a
column on the mapped model, or a declared derivation. Anything else is a
field that cannot be built.
"""

import pathlib
import re
import sys

import yaml

ROOT = pathlib.Path(__file__).parent
spec = (ROOT / "specs/2026-08-23-statusboard-design.md").read_text()
api = yaml.safe_load((ROOT / "api/openapi.yaml").read_text())

# ── columns, from the field-level ER diagram in the spec ────────────────────
detail = re.findall(r"```mermaid\n(.*?)```", spec, re.DOTALL)[1]
columns = {}
for m in re.finditer(r"^\s{4}(\w+) \{\n((?:\s{8}.*\n)+)\s{4}\}", detail, re.MULTILINE):
    names = {l.split()[1] for l in m.group(2).strip().splitlines()}
    # a FK column is written owner_id; the serializer field is owner
    columns[m.group(1)] = names | {n[:-3] for n in names if n.endswith("_id")}

# ── which schema is backed by which model ──────────────────────────────────
BACKED = {
    "Service": "Service",
    "ServiceRef": "Service",
    "StatusPage": "StatusPage",
    "Poller": "Poller",
    "Component": "ServiceComponent",
    "PathNode": "ServiceComponent",
    "Status": "ComponentStatus",
    "ServiceEvent": "ServiceEvent",
    "ServiceEventDetail": "ServiceEvent",
    "EventRef": "ServiceEvent",
    "EventUpdate": "EventUpdate",
    "Me": "User",
}
PLAIN = {
    "Meta",
    "Envelope",
    "Aggregates",
    "StatusAggregates",
    "EventAggregates",
    "TokenPair",
    "Error",
}

# ── fields that are computed, annotated or traversed, with how ─────────────
DERIVED = {
    "Service.component_count": "Count of ServiceComponent, excluding is_overall",
    "Service.tracked_component_count": "per-user annotation over DashboardItem",
    "Service.overall_component": "ServiceComponent where is_overall",
    "Service.status_page": "OneToOneField",
    "Component.status": "ComponentStatus where ended_at is null",
    "Status.ended_at": "always null on the open row; a closed row carries it",
    "Status.last_refreshed_at": "component.service.poller.last_success_at",
    "Poller.interval_seconds": "own override or /meta/ default, scaled by backoff",
    "Poller.cooldown_seconds": "own override or /meta/ default",
    "Service.poller": "OneToOneField",
    "Component.path": "walk of parent",
    "Component.descendant_count": "recursive walk down parent, archived rows left out",
    "Component.is_tracked": "per-user annotation over DashboardItem",
    "Component.upcoming_maintenance": "soonest unfinished maintenance event across that M2M",
    "Component.upcoming_maintenance_count": "Count of unfinished maintenance across that M2M",
    "Component.active_incident": "newest unresolved ServiceEvent kind=incident across that M2M",
    "Component.active_incident_count": "Count of unresolved across that M2M",
    "Me.default_dashboard_id": "Dashboard where is_default",
    "Service.in_catalog_since": "BaseModel.created_at",
    "Component.service": "ForeignKey",
    "ServiceEventDetail.update_count": "Count of EventUpdate for this event",
    "ServiceEventDetail.affected_count": "Count of affected_components for this event",
    "ServiceEventDetail.last_update_at": "newest EventUpdate.posted_at for this event",
}
INHERITED = {"id", "created_at", "updated_at", "created_by", "updated_by"}


def props(name, seen=()):
    o = api["components"]["schemas"][name]
    out = {}
    for part in o.get("allOf", []):
        if "$ref" in part:
            out.update(props(part["$ref"].split("/")[-1]))
        out.update(part.get("properties", {}))
    out.update(o.get("properties", {}))
    return out


fail = []
for schema, model in BACKED.items():
    if model not in columns:
        fail.append(f"{schema} maps to {model}, which is not in the ER diagram")
        continue
    for field in props(schema):
        if field in INHERITED:
            continue
        if f"{schema}.{field}" in DERIVED:
            continue
        base = BACKED.get(schema)
        if any(f"{s}.{field}" in DERIVED for s, m in BACKED.items() if m == base):
            continue
        if field not in columns[model]:
            fail.append(
                f"{schema}.{field} has no {model}.{field} column and no declared derivation"
            )

for schema in api["components"]["schemas"]:
    if schema not in BACKED and schema not in PLAIN:
        fail.append(f"{schema} is neither model-backed nor declared plain")

# Every declared derivation is still in use. One left behind after its
# field is renamed is a claim the API no longer makes. Nothing else here
# would notice it.
used = {
    f"{schema}.{f}" for schema in api["components"]["schemas"] for f in props(schema)
}
for o in sorted(set(DERIVED) - used):
    fail.append(f"derivation declared for a field that no longer exists: {o}")

# ── naming conventions ──────────────────────────────────────────────────────
# Counts are singular: active_incident_count, never active_incidents_count.
for owner, names in [
    *columns.items(),
    *((sch, props(sch)) for sch in api["components"]["schemas"]),
]:
    for f in names:
        if f.endswith("s_count"):
            fail.append(f"{owner}.{f} — count fields are singular: {f[:-7]}_count")

print(
    f"{len(BACKED)} model-backed schemas, {len(columns)} tables, {len(DERIVED)} declared derivations"
)
print(
    "\n".join("  FAIL " + f for f in fail)
    if fail
    else "  every API field maps to a column or a declared derivation"
)
sys.exit(1 if fail else 0)
