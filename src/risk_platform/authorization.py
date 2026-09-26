"""Local role policy. Role claims come from server configuration, never request headers."""

from typing import Annotated

from fastapi import Depends, HTTPException, Request

PERMISSIONS = {
    "investigator": frozenset(
        {"cases:read", "cases:create", "audit:read", "models:read", "models:score", "controls:read"}
    ),
    "reviewer": frozenset({"cases:read", "audit:read", "models:read", "controls:read"}),
    "auditor": frozenset({"cases:read", "audit:read", "models:read", "controls:read"}),
}


def require_permission(permission: str, authentication):
    async def check(request: Request, identity: Annotated[str, Depends(authentication)]) -> str:
        settings = request.app.state.settings
        if permission not in PERMISSIONS.get(settings.operator_role, frozenset()):
            raise HTTPException(403, "Permission denied")
        if permission == "cases:create" and not settings.writes_enabled:
            raise HTTPException(503, "Case writes are disabled")
        if permission == "models:score" and not settings.scoring_enabled:
            raise HTTPException(503, "Model scoring is disabled")
        return identity

    return check
