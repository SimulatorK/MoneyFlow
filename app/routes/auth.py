from fastapi import APIRouter, Request, Form, status, Depends
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app.db import get_db
from app.models.user import User
from app.utils.auth import verify_password, hash_password
from app.logging_config import get_logger

# Module logger for authentication operations
logger = get_logger(__name__)

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

# Registration routes
def unique_username(db: Session, username: str):
    return db.query(User).filter(User.username == username).first() is None

@router.get("/register")
def register_get(request: Request):
    logger.debug("Registration page requested")
    return templates.TemplateResponse("register.html", {"request": request, "error": None})

@router.post("/register")
def register_post(request: Request, name: str = Form(...), username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    logger.info(f"Registration attempt for username: {username}")
    if not unique_username(db, username):
        logger.warning(f"Registration failed - username already taken: {username}")
        return templates.TemplateResponse("register.html", {"request": request, "error": "Username already taken."})
    user = User(name=name, username=username, password_hash=hash_password(password))
    db.add(user)
    db.commit()
    logger.info(f"New user registered successfully: {username}")
    return RedirectResponse("/login", status_code=status.HTTP_302_FOUND)

@router.get("/login")
def login_get(request: Request):
    logger.debug("Login page requested")
    return templates.TemplateResponse("login.html", {"request": request, "error": None})

@router.post("/login")
def login_post(request: Request, username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    logger.info(f"Login attempt for username: {username}")
    user = db.query(User).filter(User.username == username).first()
    if user and verify_password(password, user.password_hash):
        logger.info(f"Login successful for user: {username}")
        response = RedirectResponse("/home", status_code=status.HTTP_302_FOUND)
        response.set_cookie(key="auth", value="1", httponly=True)
        response.set_cookie(key="username", value=username, httponly=True)  # demo only
        return response
    logger.warning(f"Login failed for username: {username} - invalid credentials")
    return templates.TemplateResponse("login.html", {"request": request, "error": "Invalid credentials."})

@router.get("/logout")
def logout(request: Request):
    username = request.cookies.get("username", "unknown")
    logger.info(f"User logged out: {username}")
    response = RedirectResponse("/login", status_code=status.HTTP_302_FOUND)
    response.delete_cookie("auth")
    response.delete_cookie("username")
    return response
