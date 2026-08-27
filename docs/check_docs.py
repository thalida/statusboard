#!/usr/bin/env python3
"""Cross-check the API schema against the data model.

Every field an endpoint returns must be produced by a ModelSerializer: either a
column on the mapped model, or a declared derivation. Anything else is a field
that cannot be built.
"""
import re, sys, yaml, pathlib

ROOT = pathlib.Path(__file__).parent
spec = (ROOT / "specs/2026-08-23-statusboard-design.md").read_text()
api  = yaml.safe_load((ROOT / "api/openapi.yaml").read_text())

# ── columns, from the field-level ER diagram in the spec ────────────────────
detail = re.findall(r"```mermaid\n(.*?)```", spec, re.S)[1]
columns = {}
for m in re.finditer(r"^\s{4}(\w+) \{\n((?:\s{8}.*\n)+)\s{4}\}", detail, re.M):
    names = {l.split()[1] for l in m.group(2).strip().splitlines()}
    # a FK column is written owner_id; the serializer field is owner
    columns[m.group(1)] = names | {n[:-3] for n in names if n.endswith("_id")}

# ── which schema is backed by which model ──────────────────────────────────
BACKED = {
    "Service": "Service", "ServiceDetail": "Service", "ServiceRef": "Service",
    "StatusPage": "StatusPage", "Poller": "Poller", "Component": "ServiceComponent",
    "OverallComponent": "ServiceComponent", "TrackedComponent": "ServiceComponent",
    "Status": "ComponentStatus", "ServiceEvent": "ServiceEvent", "EventRef": "ServiceEvent",
    "Dashboard": "Dashboard", "Me": "User",
}
PLAIN = {"Meta", "Envelope", "Aggregates", "StatusAggregates", "EventAggregates",
         "TokenPair", "Error"}

# ── fields that are computed, annotated or traversed, with how ─────────────
DERIVED = {
    "Service.component_count":            "Count of ServiceComponent, excluding is_overall",
    "Service.tracked_component_count":    "per-user annotation over DashboardItem",
    "Service.overall_component":          "ServiceComponent where is_overall",
    "Service.status_page":                "OneToOneField",
    "Component.status":                   "ComponentStatus where ended_at is null",
    "Status.ended_at":                    "always null on the open row; a closed row carries it",
    "Status.last_refreshed_at":           "component.service.poller.last_success_at",
    "Poller.interval_seconds":            "own override or /meta/ default, scaled by backoff",
    "Poller.cooldown_seconds":            "own override or /meta/ default",
    "Service.poller":                     "OneToOneField",
    "Component.path":                     "walk of parent",
    "Component.child_count":              "Count of reverse parent",
    "Component.is_tracked":               "per-user annotation over DashboardItem",
    "Component.maintenance_windows":      "ServiceEvent kind=maintenance across the reverse M2M",
    "Component.next_maintenance_window":  "soonest of maintenance_windows",
    "Component.maintenance_window_count": "Count of maintenance_windows",
    "Component.latest_incident":          "newest ServiceEvent kind=incident across the reverse M2M",
    "Component.active_incident_count":    "Count of unresolved across that M2M",
    "ServiceEvent.affected_component_ids": "M2M ids",
    "ServiceEvent.updates":               "reverse FK from EventUpdate",
    "Dashboard.aggregates":               "pagination aggregate block",
    "Me.default_dashboard_id":            "Dashboard where is_default",
    "ServiceDetail.in_catalog_since":     "BaseModel.created_at",
    "TrackedComponent.service":           "ForeignKey",
}
INHERITED = {"id", "created_at", "updated_at", "created_by", "updated_by"}

def props(name, seen=()):
    o = api["components"]["schemas"][name]; out = {}
    for part in o.get("allOf", []):
        if "$ref" in part: out.update(props(part["$ref"].split("/")[-1]))
        out.update(part.get("properties", {}))
    out.update(o.get("properties", {}))
    return out

fail = []
for schema, model in BACKED.items():
    if model not in columns:
        fail.append(f"{schema} maps to {model}, which is not in the ER diagram"); continue
    for field in props(schema):
        if field in INHERITED: continue
        if f"{schema}.{field}" in DERIVED: continue
        base = BACKED.get(schema)
        if any(f"{s}.{field}" in DERIVED for s, m in BACKED.items() if m == base): continue
        if field not in columns[model]:
            fail.append(f"{schema}.{field} has no {model}.{field} column and no declared derivation")

for schema in api["components"]["schemas"]:
    if schema not in BACKED and schema not in PLAIN:
        fail.append(f"{schema} is neither model-backed nor declared plain")

print(f"{len(BACKED)} model-backed schemas, {len(columns)} tables, {len(DERIVED)} declared derivations")
print("\n".join("  FAIL " + f for f in fail) if fail else "  every API field maps to a column or a declared derivation")
sys.exit(1 if fail else 0)

# ── naming conventions ──────────────────────────────────────────────────────
convention = []
for table, names in columns.items():
    for f in names:
        if f.endswith("s_count"):
            convention.append(f"{table}.{f} — count fields are singular: {f[:-7]}_count")
        if f.endswith("_at") and not re.search(r"(_at)$", f):
            pass
for schema in api["components"]["schemas"]:
    for f in props(schema):
        if f.endswith("s_count"):
            convention.append(f"{schema}.{f} — count fields are singular")
if convention:
    print("\n".join("  FAIL " + c for c in convention)); sys.exit(1)
