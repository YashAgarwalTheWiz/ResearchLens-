from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from services.auth_service import register_user, login_user

router = APIRouter()


class AuthRequest(BaseModel):
    email: str
    password: str


@router.post("/register")
def register(req: AuthRequest):
    result = register_user(req.email, req.password)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return {"message": "Registered successfully"}


@router.post("/login")
def login(req: AuthRequest):
    result = login_user(req.email, req.password)
    if not result["success"]:
        raise HTTPException(status_code=401, detail=result["message"])
    return {"token": result["token"], "user_id": result["user_id"]}