"""FastAPI Router for YAML Detection Rules, Schema Validation, Test Runners, and Lifecycle Governance.

Endpoints:
- GET /api/v1/rules
- POST /api/v1/rules
- GET /api/v1/rules/{id}
- PUT /api/v1/rules/{id}
- DELETE /api/v1/rules/{id}
- POST /api/v1/rules/validate
- POST /api/v1/rules/test
- POST /api/v1/rules/{id}/test
- POST /api/v1/rules/{id}/lifecycle
Conforms to Noosforge Sentinel R4 specifications.
"""

from __future__ import annotations

import os
from typing import AsyncGenerator, Dict, List, Optional
import yaml
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.app.api.deps import require_admin, require_operator, require_viewer
from backend.app.models.user import User
from backend.app.models.rule import DetectionRule, RuleAuditLog, RuleStatus
from backend.app.rules.lifecycle import RuleLifecycleManager
from backend.app.rules.test_runner import RuleTestRunner
from backend.app.rules.validator import RuleValidator
from backend.app.schemas.rule import (
    DetectionRuleCreate,
    DetectionRuleResponse,
    DetectionRuleUpdate,
    RuleLifecycleTransitionRequest,
    RuleLifecycleTransitionResponse,
    RuleStatusEnum,
    RuleTestFixtureRunnerRequest,
    RuleTestFixtureRunnerResponse,
    RuleValidateRequest,
    RuleValidationResponse,
)

# Database Session Dependency with Fallback
try:
    from backend.app.core.database import get_db
except ImportError:
    DATABASE_URL = os.getenv("SENTINEL_DATABASE_URL", "sqlite+aiosqlite:///./sentinel.db")
    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async def get_db() -> AsyncGenerator[AsyncSession, None]:
        async with async_session() as session:
            try:
                yield session
            finally:
                await session.close()

router = APIRouter(prefix="/rules", tags=["Detection Rules"])


@router.post("/validate", response_model=RuleValidationResponse)
async def validate_rule_syntax(
    payload: RuleValidateRequest,
    current_user: User = Depends(require_viewer),
) -> RuleValidationResponse:
    """Validate a detection rule's syntax, structure, and regular expressions."""
    if payload.raw_yaml:
        return RuleValidator.validate_yaml_string(payload.raw_yaml)
    if payload.rule_dict:
        return RuleValidator.validate_dict(payload.rule_dict)
    return RuleValidationResponse(valid=False, errors=["Must provide 'raw_yaml' or 'rule_dict'."])


@router.get("", response_model=List[DetectionRuleResponse])
async def list_rules(
    status: Optional[RuleStatusEnum] = None,
    severity: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_viewer),
) -> List[DetectionRuleResponse]:
    """List detection rules with status, severity, and text search filtering."""
    stmt = select(DetectionRule)

    if status:
        stmt = stmt.where(DetectionRule.status == status.value)
    if severity:
        stmt = stmt.where(DetectionRule.severity == severity.lower())
    if search:
        search_filter = f"%{search.strip()}%"
        stmt = stmt.where(
            or_(
                DetectionRule.id.ilike(search_filter),
                DetectionRule.name.ilike(search_filter),
                DetectionRule.description.ilike(search_filter),
            )
        )

    stmt = stmt.order_by(DetectionRule.updated_at.desc()).offset(offset).limit(limit)
    result = await session.execute(stmt)
    rules = result.scalars().all()

    return [DetectionRuleResponse.model_validate(r.to_dict()) for r in rules]


@router.post("", response_model=DetectionRuleResponse, status_code=status.HTTP_201_CREATED)
async def create_rule(
    payload: DetectionRuleCreate,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> DetectionRuleResponse:
    """Create and persist a new detection rule."""
    if payload.raw_yaml:
        val_res = RuleValidator.validate_yaml_string(payload.raw_yaml)
        if not val_res.valid:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Rule validation failed: {'; '.join(val_res.errors)}",
            )
        parsed = yaml.safe_load(payload.raw_yaml)
        raw_yaml_str = payload.raw_yaml
    elif payload.rule_data:
        parsed = payload.rule_data.model_dump()
        raw_yaml_str = yaml.dump(parsed, sort_keys=False)
        val_res = RuleValidator.validate_dict(parsed)
        if not val_res.valid:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Rule validation failed: {'; '.join(val_res.errors)}",
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Must provide either 'raw_yaml' or 'rule_data'.",
        )

    rule_id = parsed["id"]

    # Check for duplicate ID
    stmt = select(DetectionRule).where(DetectionRule.id == rule_id)
    existing = (await session.execute(stmt)).scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Rule with ID '{rule_id}' already exists.",
        )

    actor_username = current_user.username if current_user and current_user.username else "system"
    new_rule = DetectionRule(
        id=rule_id,
        name=parsed.get("name", "Unnamed Rule"),
        description=parsed.get("description"),
        version=parsed.get("version", "1.0.0"),
        author=parsed.get("author", actor_username),
        severity=parsed.get("severity", "medium").lower(),
        status=RuleStatus.DRAFT.value,
        target_types=parsed.get("target_types", ["web_application"]),
        metadata_json=parsed.get("metadata", {}),
        detection_json=parsed.get("detection", {}),
        remediation_json=parsed.get("remediation", {}),
        raw_yaml=raw_yaml_str,
        created_by=actor_username,
    )
    session.add(new_rule)

    # Initial audit log
    audit_entry = RuleAuditLog(
        rule_id=rule_id,
        actor=actor_username,
        action="created",
        from_status=None,
        to_status=RuleStatus.DRAFT.value,
        notes="Initial rule creation.",
    )
    session.add(audit_entry)
    await session.commit()

    # Re-query with eager relationships
    stmt = select(DetectionRule).where(DetectionRule.id == rule_id)
    saved_rule = (await session.execute(stmt)).scalar_one()
    return DetectionRuleResponse.model_validate(saved_rule.to_dict())


@router.get("/{id}", response_model=DetectionRuleResponse)
async def get_rule(
    id: str,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_viewer),
) -> DetectionRuleResponse:
    """Retrieve full details, test fixtures, and audit logs for a single rule."""
    stmt = select(DetectionRule).where(DetectionRule.id == id)
    result = await session.execute(stmt)
    rule = result.scalar_one_or_none()

    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Rule '{id}' not found.",
        )

    return DetectionRuleResponse.model_validate(rule.to_dict())


@router.put("/{id}", response_model=DetectionRuleResponse)
async def update_rule(
    id: str,
    payload: DetectionRuleUpdate,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> DetectionRuleResponse:
    """Update a detection rule's definition."""
    stmt = select(DetectionRule).where(DetectionRule.id == id)
    result = await session.execute(stmt)
    rule = result.scalar_one_or_none()

    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Rule '{id}' not found.",
        )

    if payload.raw_yaml:
        val_res = RuleValidator.validate_yaml_string(payload.raw_yaml)
        if not val_res.valid:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Rule validation failed: {'; '.join(val_res.errors)}",
            )
        parsed = yaml.safe_load(payload.raw_yaml)
        rule.name = parsed.get("name", rule.name)
        rule.description = parsed.get("description", rule.description)
        rule.version = parsed.get("version", rule.version)
        rule.severity = parsed.get("severity", rule.severity).lower()
        rule.target_types = parsed.get("target_types", rule.target_types)
        rule.metadata_json = parsed.get("metadata", rule.metadata_json)
        rule.detection_json = parsed.get("detection", rule.detection_json)
        rule.remediation_json = parsed.get("remediation", rule.remediation_json)
        rule.raw_yaml = payload.raw_yaml

    if payload.name:
        rule.name = payload.name
    if payload.description is not None:
        rule.description = payload.description
    if payload.severity:
        rule.severity = payload.severity.value

    actor_username = current_user.username if current_user and current_user.username else "admin"
    audit_entry = RuleAuditLog(
        rule_id=rule.id,
        actor=actor_username,
        action="updated",
        from_status=rule.status,
        to_status=rule.status,
        notes="Updated rule definition.",
    )
    session.add(audit_entry)
    await session.commit()

    return DetectionRuleResponse.model_validate(rule.to_dict())


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rule(
    id: str,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> None:
    """Delete a detection rule."""
    stmt = select(DetectionRule).where(DetectionRule.id == id)
    result = await session.execute(stmt)
    rule = result.scalar_one_or_none()

    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Rule '{id}' not found.",
        )

    await session.delete(rule)
    await session.commit()


@router.post("/test", response_model=RuleTestFixtureRunnerResponse)
async def test_adhoc_rule(
    payload: RuleTestFixtureRunnerRequest,
    current_user: User = Depends(require_viewer),
) -> RuleTestFixtureRunnerResponse:
    """Execute test fixtures against an ad-hoc or raw YAML rule payload."""
    if payload.raw_yaml:
        try:
            rule_dict = yaml.safe_load(payload.raw_yaml)
        except yaml.YAMLError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid YAML: {e}",
            )
    elif payload.rule_id:
        # Load rule from disk if available
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
        rule_path = os.path.join(base_dir, "fixtures", "rules", f"{payload.rule_id}.yaml")
        if os.path.exists(rule_path):
            with open(rule_path, "r", encoding="utf-8") as f:
                rule_dict = yaml.safe_load(f)
        else:
            raise HTTPException(status_code=404, detail=f"Rule file for '{payload.rule_id}' not found.")
    else:
        raise HTTPException(status_code=400, detail="Must provide 'raw_yaml' or 'rule_id'.")

    cases = [c.model_dump() for c in payload.test_cases] if payload.test_cases else None
    return RuleTestRunner.run_tests(rule_dict, test_cases=cases)


@router.post("/{id}/test", response_model=RuleTestFixtureRunnerResponse)
async def test_saved_rule(
    id: str,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_viewer),
) -> RuleTestFixtureRunnerResponse:
    """Run test fixtures for a saved database rule."""
    stmt = select(DetectionRule).where(DetectionRule.id == id)
    result = await session.execute(stmt)
    rule = result.scalar_one_or_none()

    if not rule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Rule '{id}' not found.")

    rule_dict = {
        "id": rule.id,
        "name": rule.name,
        "severity": rule.severity,
        "detection": rule.detection_json,
    }
    return RuleTestRunner.run_tests(rule_dict)


@router.post("/{id}/lifecycle", response_model=RuleLifecycleTransitionResponse)
async def transition_rule_lifecycle(
    id: str,
    payload: RuleLifecycleTransitionRequest,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> RuleLifecycleTransitionResponse:
    """Transition rule through its review-gated governance lifecycle (enforcing separation of duties)."""
    try:
        actor_username = current_user.username if current_user and current_user.username else "admin"
        return await RuleLifecycleManager.transition_rule(
            session=session,
            rule_id=id,
            target_status=payload.target_status,
            actor=actor_username,
            notes=payload.notes,
        )
    except PermissionError as pe:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(pe),
        )
    except ValueError as ve:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(ve),
        )
