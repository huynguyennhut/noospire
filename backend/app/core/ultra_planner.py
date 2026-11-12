"""Ultra Scan Inventory Planner & Accounting Engine.
Implements complete inventory accounting, alias resolution, exclusion reasoning,
and exact engine execution matrix planning for the Empire Educational Ecosystem.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple


class InventoryRowClassification(str, Enum):
    EXECUTION_TARGET = "EXECUTION_TARGET"
    ALIAS = "ALIAS"
    EXCLUDED = "EXCLUDED"
    # Milestone 7: rows that are accounted for but cannot run, each with an explicit reason.
    INVALID_ALIAS = "INVALID_ALIAS"          # alias_of points to no execution target in this inventory
    NO_APPLICABLE_ENGINE = "NO_APPLICABLE_ENGINE"  # requested engines/profile cover none of this asset type


class ExecutionStatus(str, Enum):
    PLANNED = "PLANNED"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    TIMED_OUT = "TIMED_OUT"
    CANCELLED = "CANCELLED"
    UNAVAILABLE = "UNAVAILABLE"
    SKIPPED = "SKIPPED"


@dataclass
class ChildEngineExecution:
    execution_id: str
    target_id: str
    target_locator: str
    engine: str
    profile: str
    status: ExecutionStatus = ExecutionStatus.PLANNED
    attempt: int = 1
    engine_version: Optional[str] = "2.0.0"
    rule_digest: Optional[str] = None
    worker_id: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    coverage_reason: Optional[str] = None
    report_link: Optional[str] = None
    findings_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "execution_id": self.execution_id,
            "target_id": self.target_id,
            "target_locator": self.target_locator,
            "engine": self.engine,
            "profile": self.profile,
            "status": self.status.value if hasattr(self.status, "value") else str(self.status),
            "attempt": self.attempt,
            "engine_version": self.engine_version,
            "rule_digest": self.rule_digest,
            "worker_id": self.worker_id,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "coverage_reason": self.coverage_reason,
            "report_link": self.report_link,
            "findings_count": self.findings_count,
        }


@dataclass
class AccountedInventoryRow:
    inventory_id: str
    target_locator: str
    asset_type: str
    classification: InventoryRowClassification
    alias_of_target_id: Optional[str] = None
    exclusion_reason: Optional[str] = None
    planned_engines: List[str] = field(default_factory=list)
    child_executions: List[ChildEngineExecution] = field(default_factory=list)
    environment: str = "PRODUCTION"
    policy_revision: str = "2026.11-R2"
    tenant: str = "empire_edu"
    identity: str = "synthetic_scanner"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "inventory_id": self.inventory_id,
            "target_locator": self.target_locator,
            "asset_type": self.asset_type,
            "classification": self.classification.value if hasattr(self.classification, "value") else str(self.classification),
            "alias_of_target_id": self.alias_of_target_id,
            "exclusion_reason": self.exclusion_reason,
            "planned_engines": self.planned_engines,
            "executions_count": len(self.child_executions),
            "environment": self.environment,
            "policy_revision": self.policy_revision,
            "tenant": self.tenant,
            "identity": self.identity,
        }


@dataclass
class UltraScanPlan:
    batch_id: str
    snapshot_time: datetime
    policy_revision: str
    accounted_inventory_rows: int
    independent_execution_targets: int
    engine_executions_count: int
    shared_alias_count: int
    excluded_count: int
    inventory_entries: List[AccountedInventoryRow] = field(default_factory=list)
    all_executions: List[ChildEngineExecution] = field(default_factory=list)
    shared_result_links: List[Dict[str, str]] = field(default_factory=list)
    explained_exclusions: List[Dict[str, str]] = field(default_factory=list)

    def to_summary_dict(self) -> Dict[str, Any]:
        return {
            "batch_id": self.batch_id,
            "snapshot_time": self.snapshot_time.isoformat(),
            "policy_revision": self.policy_revision,
            "accounted_inventory_rows": self.accounted_inventory_rows,
            "independent_execution_targets": self.independent_execution_targets,
            "engine_executions_count": self.engine_executions_count,
            "shared_alias_count": self.shared_alias_count,
            "excluded_count": self.excluded_count,
            "shared_result_links_count": len(self.shared_result_links),
            "explained_exclusions_count": len(self.explained_exclusions),
            "invalid_alias_count": sum(1 for r in self.inventory_entries
                                       if r.classification == InventoryRowClassification.INVALID_ALIAS),
            "no_applicable_engine_count": sum(1 for r in self.inventory_entries
                                              if r.classification == InventoryRowClassification.NO_APPLICABLE_ENGINE),
        }


class UltraScanPlanner:
    """Plans and snapshots the entire project inventory into discrete execution targets,
    alias associations, and out-of-scope exclusions.
    """

    SUPPORTED_ENGINES = {"nuclei", "zap", "empire", "trivy"}

    def plan_inventory(
        self,
        inventory_items: List[Dict[str, Any]],
        requested_engines: Optional[List[str]] = None,
        profile: str = "STANDARD",
        batch_id: Optional[str] = None,
        policy_revision: str = "2026.11-R2",
    ) -> UltraScanPlan:
        plan_batch_id = batch_id or str(uuid.uuid4())
        snapshot_time = datetime.now(timezone.utc)

        # Normalize requested engines
        active_engines: Optional[Set[str]] = None
        if requested_engines:
            norm_engines = {e.lower().strip() for e in requested_engines}
            if "all" not in norm_engines and "*" not in norm_engines:
                active_engines = norm_engines

        accounted_rows: List[AccountedInventoryRow] = []
        all_executions: List[ChildEngineExecution] = []
        shared_links: List[Dict[str, str]] = []
        explained_exclusions: List[Dict[str, str]] = []

        # Index execution targets by semantics: (locator, environment, tenant, identity)
        execution_target_map: Dict[str, str] = {}
        # IDs an alias may legitimately point to: in-scope, non-alias rows of this same inventory.
        primary_ids = {
            str(i.get("id") or i.get("inventory_id"))
            for i in inventory_items
            if not (i.get("is_out_of_scope") or i.get("out_of_scope"))
            and not (i.get("is_alias") or i.get("alias_of"))
        }

        for item in inventory_items:
            inv_id = str(item.get("id") or item.get("inventory_id") or uuid.uuid4())
            locator = str(item.get("target_locator") or item.get("locator") or "").strip()
            asset_type = str(item.get("asset_type") or "WEB_APP").upper()
            is_out_of_scope = bool(item.get("is_out_of_scope", False) or item.get("out_of_scope", False))
            is_alias = bool(item.get("is_alias", False) or item.get("alias_of"))
            alias_target = str(item.get("alias_of") or "") if is_alias else None
            env = str(item.get("environment") or "PRODUCTION")
            tenant = str(item.get("tenant") or "empire_edu")
            identity = str(item.get("identity") or "synthetic_scanner")

            # 1. Out-of-scope exclusion
            if is_out_of_scope:
                reason = str(item.get("exclusion_reason") or "Target out of authorized pilot assessment scope")
                row = AccountedInventoryRow(
                    inventory_id=inv_id,
                    target_locator=locator,
                    asset_type=asset_type,
                    classification=InventoryRowClassification.EXCLUDED,
                    exclusion_reason=reason,
                    environment=env,
                    policy_revision=policy_revision,
                    tenant=tenant,
                    identity=identity,
                )
                accounted_rows.append(row)
                explained_exclusions.append({
                    "inventory_id": inv_id,
                    "target_locator": locator,
                    "reason": reason,
                })
                continue

            # 2. Alias resolution (an alias without a valid primary is reported, never silently shared)
            if is_alias and (not alias_target or alias_target not in primary_ids):
                accounted_rows.append(AccountedInventoryRow(
                    inventory_id=inv_id, target_locator=locator, asset_type=asset_type,
                    classification=InventoryRowClassification.INVALID_ALIAS, alias_of_target_id=alias_target,
                    exclusion_reason=(f"alias_of '{alias_target}' is not an in-scope execution target of this inventory"
                                      if alias_target else "alias without alias_of"),
                    environment=env, policy_revision=policy_revision, tenant=tenant, identity=identity))
                continue
            if is_alias and alias_target:
                row = AccountedInventoryRow(
                    inventory_id=inv_id,
                    target_locator=locator,
                    asset_type=asset_type,
                    classification=InventoryRowClassification.ALIAS,
                    alias_of_target_id=alias_target,
                    environment=env,
                    policy_revision=policy_revision,
                    tenant=tenant,
                    identity=identity,
                )
                accounted_rows.append(row)
                shared_links.append({
                    "alias_inventory_id": inv_id,
                    "alias_locator": locator,
                    "target_id": alias_target,
                    "shared_result_link": f"/reports/batch/{plan_batch_id}/target/{alias_target}",
                })
                continue

            # 3. Independent Execution Target
            # Determine applicable engines based on asset_type
            applicable_engines: List[str] = []
            if asset_type in ("PROJECT_ARCHIVE", "CONTAINER_IMAGE", "ARTIFACT", "SBOM", "FILE_SYSTEM"):
                applicable_engines = ["trivy"]
            elif asset_type in ("API_ENDPOINT", "API_SERVICES", "MICROSERVICE"):
                applicable_engines = ["nuclei", "empire"]
            else:  # Web targets: DOMAIN, WEB_APP, etc.
                applicable_engines = ["nuclei", "zap"]

            # Filter by requested engines subset if specified
            if active_engines is not None:
                planned_engines = [e for e in applicable_engines if e in active_engines]
            else:
                planned_engines = applicable_engines

            if not planned_engines:
                accounted_rows.append(AccountedInventoryRow(
                    inventory_id=inv_id, target_locator=locator, asset_type=asset_type,
                    classification=InventoryRowClassification.NO_APPLICABLE_ENGINE,
                    exclusion_reason=(f"requested engines {sorted(active_engines or [])} cover none of "
                                      f"{applicable_engines} for asset type {asset_type}"),
                    environment=env, policy_revision=policy_revision, tenant=tenant, identity=identity))
                continue

            child_execs: List[ChildEngineExecution] = []
            for eng in planned_engines:
                exec_id = str(uuid.uuid4())
                child = ChildEngineExecution(
                    execution_id=exec_id,
                    target_id=inv_id,
                    target_locator=locator,
                    engine=eng,
                    profile=profile,
                    status=ExecutionStatus.PLANNED,
                    report_link=f"/reports/batch/{plan_batch_id}/engine/{eng}/{exec_id}",
                )
                child_execs.append(child)
                all_executions.append(child)

            row = AccountedInventoryRow(
                inventory_id=inv_id,
                target_locator=locator,
                asset_type=asset_type,
                classification=InventoryRowClassification.EXECUTION_TARGET,
                planned_engines=planned_engines,
                child_executions=child_execs,
                environment=env,
                policy_revision=policy_revision,
                tenant=tenant,
                identity=identity,
            )
            accounted_rows.append(row)
            execution_target_map[inv_id] = locator

        indep_count = sum(1 for r in accounted_rows if r.classification == InventoryRowClassification.EXECUTION_TARGET)
        alias_count = sum(1 for r in accounted_rows if r.classification == InventoryRowClassification.ALIAS)
        excl_count = sum(1 for r in accounted_rows if r.classification == InventoryRowClassification.EXCLUDED)

        return UltraScanPlan(
            batch_id=plan_batch_id,
            snapshot_time=snapshot_time,
            policy_revision=policy_revision,
            accounted_inventory_rows=len(accounted_rows),
            independent_execution_targets=indep_count,
            engine_executions_count=len(all_executions),
            shared_alias_count=alias_count,
            excluded_count=excl_count,
            inventory_entries=accounted_rows,
            all_executions=all_executions,
            shared_result_links=shared_links,
            explained_exclusions=explained_exclusions,
        )

    def generate_acceptance_fixture_379(self) -> List[Dict[str, Any]]:
        """Generates exactly the 379 synthetic inventory items specified in the product contract:
        - 350 web targets (Nuclei + ZAP)
        - 10 API targets (Nuclei + Empire)
        - 8 artifact targets (Trivy)
        - 6 equivalent aliases (linking to 6 web targets)
        - 5 out-of-scope entries (explained exclusions)
        Total: 379 items
        """
        items: List[Dict[str, Any]] = []

        # 1. 350 Web Targets -> Nuclei + ZAP
        for i in range(1, 351):
            target_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"web-target-{i:04d}.empire.edu.vn"))
            items.append({
                "id": target_id,
                "target_locator": f"https://service-{i:04d}.empire.edu.vn",
                "asset_type": "WEB_APP",
                "is_out_of_scope": False,
                "is_alias": False,
                "environment": "PRODUCTION",
            })

        # 2. 10 API Targets -> Nuclei + Empire
        for i in range(1, 11):
            items.append({
                "id": str(uuid.uuid5(uuid.NAMESPACE_DNS, f"api-target-{i:04d}.empire.edu.vn")),
                "target_locator": f"https://api-gateway.empire.edu.vn/v2/module-{i}",
                "asset_type": "API_ENDPOINT",
                "is_out_of_scope": False,
                "is_alias": False,
                "environment": "PRODUCTION",
            })

        # 3. 8 Artifact Targets -> Trivy
        for i in range(1, 9):
            items.append({
                "id": str(uuid.uuid5(uuid.NAMESPACE_DNS, f"artifact-target-{i:04d}.empire.edu.vn")),
                "target_locator": f"registry.empire.edu.vn/build/empire-core:v2.{i}",
                "asset_type": "CONTAINER_IMAGE",
                "is_out_of_scope": False,
                "is_alias": False,
                "environment": "STAGING",
            })

        # 4. 6 Equivalent Aliases referencing targets 1 to 6
        for i in range(1, 7):
            primary_target_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"web-target-{i:04d}.empire.edu.vn"))
            items.append({
                "id": str(uuid.uuid5(uuid.NAMESPACE_DNS, f"alias-target-{i:04d}.empire.edu.vn")),
                "target_locator": f"https://cname-alias-{i:04d}.empire.edu.vn",
                "asset_type": "WEB_APP",
                "is_out_of_scope": False,
                "is_alias": True,
                "alias_of": primary_target_id,
                "environment": "PRODUCTION",
            })

        # 5. 5 Out-of-Scope Entries
        for i in range(1, 6):
            items.append({
                "id": str(uuid.uuid5(uuid.NAMESPACE_DNS, f"excluded-target-{i:04d}.external-vendor.com")),
                "target_locator": f"https://third-party-partner-{i}.external-vendor.com",
                "asset_type": "WEB_APP",
                "is_out_of_scope": True,
                "is_alias": False,
                "exclusion_reason": f"Third-party external vendor #{i} outside authorized Empire scope boundary",
                "environment": "EXTERNAL",
            })

        return items


ultra_planner = UltraScanPlanner()
