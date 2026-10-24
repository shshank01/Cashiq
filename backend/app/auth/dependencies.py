from fastapi import Depends, HTTPException, status, Header, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.auth.jwt import verify_token
from app.database import get_db
from app.models.user import User
from app.models.workspace import WorkspaceMembership
from typing import Optional

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    user_id = verify_token(token)
    if user_id is None:
        raise credentials_exception

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise credentials_exception
    return user


async def get_current_workspace_user(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    x_workspace_id: Optional[str] = Header(None, alias="x-workspace-id"),
) -> dict:
    """
    Verifies user has access to the workspace.
    Resolves workspace_id from path parameters (workspace_id or wid) or X-Workspace-Id header.
    """
    wid = request.path_params.get("workspace_id") or request.path_params.get("wid") or x_workspace_id
    if not wid:
        raise HTTPException(status_code=400, detail="Workspace ID is required in URL path or X-Workspace-Id header")

    result = await db.execute(
        select(WorkspaceMembership).where(
            WorkspaceMembership.workspace_id == wid,
            WorkspaceMembership.user_id == current_user.id,
        )
    )
    membership = result.scalar_one_or_none()
    if membership is None:
        raise HTTPException(status_code=403, detail="Not a member of this workspace")
    return {"user": current_user, "workspace_id": wid, "role": membership.role}


verify_workspace_access = get_current_workspace_user
