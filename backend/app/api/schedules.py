"""Retired DailySchedule API; monitor-schedules owns durable defensive scheduling.

Keep the legacy URLs explicit so stale clients receive a migration response instead
of silently launching unfenced, estate-wide legacy scanner jobs. No database or
dispatcher is consulted, including for authenticated clients.
"""

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/schedules", tags=["Retired daily schedules"])


@router.get("")
@router.post("")
@router.get("/{id}")
@router.get("/{id}/status")
@router.post("/{id}/trigger")
@router.put("/{id}/toggle")
@router.delete("/{id}")
async def retired_schedule_api(request: Request) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_410_GONE,
        content={
            "detail": "The DailySchedule API was replaced by /api/v1/monitor-schedules. Legacy schedules cannot launch defensive executions.",
            "replacement": "/api/v1/monitor-schedules",
            "code": "GONE",
            "request_id": getattr(request.state, "request_id", None),
        },
    )
