from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
import bcrypt
from pydantic import BaseModel, ConfigDict
from app.auth.jwt import create_access_token, create_refresh_token, verify_refresh_token
from app.auth.dependencies import get_current_user
from app.auth.rate_limiter import login_rate_limiter
from app.database import get_db
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMembership
from app.models.refresh_token import RefreshToken

router = APIRouter(prefix="/auth", tags=["auth"])

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except Exception:
        return False


class RegisterRequest(BaseModel):
    email: str
    password: str
    full_name: str


class LoginRequest(BaseModel):
    email: str
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class UserResponse(BaseModel):
    id: str
    email: str
    full_name: str

    model_config = ConfigDict(from_attributes=True)


class AuthResponse(BaseModel):
    access_token: str
    refresh_token: Optional[str] = None
    token_type: str = "bearer"
    user: UserResponse


@router.post("/register", response_model=AuthResponse)
async def register(req: RegisterRequest, db: AsyncSession = Depends(get_db)):
    email_clean = req.email.lower().strip()
    result = await db.execute(select(User).where(User.email == email_clean))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(
        email=email_clean,
        hashed_password=hash_password(req.password),
        full_name=req.full_name.strip(),
    )
    db.add(user)
    await db.flush()

    workspace = Workspace(name=f"{req.full_name.strip()}'s Business", owner_id=user.id)
    db.add(workspace)
    await db.flush()

    membership = WorkspaceMembership(
        workspace_id=workspace.id, user_id=user.id, role="owner"
    )
    db.add(membership)

    access_token = create_access_token(data={"sub": user.id})
    refresh_tok = create_refresh_token(user_id=user.id)

    db_rt = RefreshToken(
        user_id=user.id,
        token=refresh_tok,
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    db.add(db_rt)
    await db.commit()

    return AuthResponse(
        access_token=access_token,
        refresh_token=refresh_tok,
        user=UserResponse(id=user.id, email=user.email, full_name=user.full_name),
    )


@router.post("/login", response_model=AuthResponse)
async def login(req: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)):
    client_ip = request.client.host if request.client else "unknown"
    rate_key = f"{client_ip}:{req.email.lower().strip()}"

    login_rate_limiter.check_rate_limit(rate_key)

    email_clean = req.email.lower().strip()
    result = await db.execute(select(User).where(User.email == email_clean))
    user = result.scalar_one_or_none()

    if not user or not verify_password(req.password, user.hashed_password):
        login_rate_limiter.record_failure(rate_key)
        raise HTTPException(status_code=401, detail="Invalid email or password")

    login_rate_limiter.record_success(rate_key)

    access_token = create_access_token(data={"sub": user.id})
    refresh_tok = create_refresh_token(user_id=user.id)

    db_rt = RefreshToken(
        user_id=user.id,
        token=refresh_tok,
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    db.add(db_rt)
    await db.commit()

    return AuthResponse(
        access_token=access_token,
        refresh_token=refresh_tok,
        user=UserResponse(id=user.id, email=user.email, full_name=user.full_name),
    )


@router.post("/refresh", response_model=AuthResponse)
async def refresh_tokens(req: RefreshRequest, db: AsyncSession = Depends(get_db)):
    payload = verify_refresh_token(req.refresh_token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    user_id = payload.get("sub")
    # Verify in DB that token has not been revoked
    rt_res = await db.execute(
        select(RefreshToken).where(
            RefreshToken.token == req.refresh_token,
            RefreshToken.user_id == user_id,
            RefreshToken.revoked == False,
        )
    )
    db_token = rt_res.scalar_one_or_none()
    if not db_token:
        raise HTTPException(status_code=401, detail="Refresh token has been revoked or is invalid")

    # Revoke old refresh token (rotation)
    db_token.revoked = True

    # Check user active
    u_res = await db.execute(select(User).where(User.id == user_id, User.is_active == True))
    user = u_res.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="User not found or inactive")

    # Issue new pair
    new_access_token = create_access_token(data={"sub": user.id})
    new_refresh_token = create_refresh_token(user_id=user.id)

    new_db_rt = RefreshToken(
        user_id=user.id,
        token=new_refresh_token,
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    db.add(new_db_rt)
    await db.commit()

    return AuthResponse(
        access_token=new_access_token,
        refresh_token=new_refresh_token,
        user=UserResponse(id=user.id, email=user.email, full_name=user.full_name),
    )


@router.post("/logout")
async def logout(req: Optional[RefreshRequest] = None, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if req and req.refresh_token:
        await db.execute(
            update(RefreshToken)
            .where(RefreshToken.token == req.refresh_token, RefreshToken.user_id == current_user.id)
            .values(revoked=True)
        )
        await db.commit()
    return {"message": "Successfully logged out"}


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        full_name=current_user.full_name,
    )
