"""
Health service.

Deliberately does not check database connectivity. Decision (documented
here and in docs/ARCHITECTURE.md): /api/health answers "is the API process
alive and correctly configured," not "is the database reachable." This
matters because the whole point of Phase 1 is that the backend must start
and respond even when PostgreSQL (or any other optional dependency) is not
running. A separate readiness/DB-connectivity check can be added in
Phase 2 once there is an actual database to be ready or not-ready about.
"""

from app.core.config import Settings, get_settings
from app.schemas.health import HealthResponse


def get_health_status(settings: Settings | None = None) -> HealthResponse:
    settings = settings or get_settings()
    return HealthResponse(
        status="ok",
        service=settings.service_name,
        environment=settings.environment,
    )
