"""
api/routers/auth.py

POST /api/v1/auth/token   — get JWT access token
GET  /api/v1/auth/me      — current user info
"""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from middleware.auth import authenticate_user, create_access_token, get_current_user
from schemas import TokenResponse

router = APIRouter(prefix="/api/v1/auth", tags=["Auth"])


@router.post("/token", response_model=TokenResponse, summary="Obtain JWT access token")
async def login(form: OAuth2PasswordRequestForm = Depends()):
    user = authenticate_user(form.username, form.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token, expires_in = create_access_token({"sub": user["username"], "role": user["role"]})
    return TokenResponse(access_token=token, expires_in=expires_in)


@router.get("/me", summary="Current authenticated user")
async def me(user: dict = Depends(get_current_user)):
    return {"username": user["username"], "role": user["role"]}
