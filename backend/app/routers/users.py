"""User endpoints."""

from fastapi import APIRouter, HTTPException

from backend.app.schemas import UserLogin
from backend.database import authenticate_user, touch_user_last_login

router = APIRouter()


@router.post("/users/login", tags=["Users"])
async def login_user(payload: UserLogin):
    if not payload.password:
        raise HTTPException(status_code=400, detail="Password is required")
    user = authenticate_user(payload.username, payload.password)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    touch_user_last_login(user["id"])
    return {"success": True, "user": user}
