from fastapi import APIRouter, Request, Form, Depends, UploadFile, File
from fastapi.responses import RedirectResponse, Response, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app.db import get_db
from app.models.user import User
from app.utils.auth import verify_password, hash_password
from app.logging_config import get_logger
import base64

# Module logger for profile operations
logger = get_logger(__name__)

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
ALLOWED_TYPES = ["image/jpeg", "image/png", "image/gif", "image/webp"]


def get_current_user(request: Request, db: Session):
    """Get the logged-in user from cookies."""
    username = request.cookies.get("username")
    if not username:
        logger.debug("No username cookie found for profile access")
        return None
    user = db.query(User).filter(User.username == username).first()
    if user:
        logger.debug(f"Profile access by user: {username}")
    return user


@router.get("/profile")
def profile_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login")
    
    # Convert profile picture to base64 for display
    profile_pic_data = None
    if user.profile_picture:
        profile_pic_data = base64.b64encode(user.profile_picture).decode('utf-8')
    
    return templates.TemplateResponse("profile.html", {
        "request": request,
        "title": "Profile Settings",
        "user": user,
        "profile_pic_data": profile_pic_data,
        "success": request.query_params.get("success"),
        "error": request.query_params.get("error"),
        "dark_mode": user.dark_mode
    })


@router.post("/profile/update-info")
def update_profile_info(
    request: Request,
    db: Session = Depends(get_db),
    name: str = Form(...),
    username: str = Form(...)
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login")
    
    # Check if username is already taken by another user
    if username != user.username:
        existing = db.query(User).filter(User.username == username).first()
        if existing:
            return RedirectResponse("/profile?error=Username+already+taken", status_code=303)
    
    user.name = name.strip()
    old_username = user.username
    user.username = username.strip()
    db.commit()
    
    # Update the cookie if username changed
    response = RedirectResponse("/profile?success=Profile+updated", status_code=303)
    if old_username != username:
        response.set_cookie(key="username", value=username, httponly=True)
    
    return response


@router.post("/profile/update-password")
def update_password(
    request: Request,
    db: Session = Depends(get_db),
    current_password: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...)
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login")
    
    # Verify current password
    if not verify_password(current_password, user.password_hash):
        return RedirectResponse("/profile?error=Current+password+is+incorrect", status_code=303)
    
    # Check new passwords match
    if new_password != confirm_password:
        return RedirectResponse("/profile?error=New+passwords+do+not+match", status_code=303)
    
    # Check minimum length
    if len(new_password) < 6:
        return RedirectResponse("/profile?error=Password+must+be+at+least+6+characters", status_code=303)
    
    user.password_hash = hash_password(new_password)
    db.commit()
    
    return RedirectResponse("/profile?success=Password+updated+successfully", status_code=303)


@router.post("/profile/upload-picture")
async def upload_profile_picture(
    request: Request,
    db: Session = Depends(get_db),
    picture: UploadFile = File(...)
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login")
    
    # Check file type
    if picture.content_type not in ALLOWED_TYPES:
        return RedirectResponse("/profile?error=Invalid+file+type.+Use+JPEG,+PNG,+GIF,+or+WebP", status_code=303)
    
    # Read file content
    content = await picture.read()
    
    # Check file size
    if len(content) > MAX_FILE_SIZE:
        return RedirectResponse("/profile?error=File+too+large.+Max+10MB", status_code=303)
    
    user.profile_picture = content
    user.profile_picture_type = picture.content_type
    db.commit()
    
    return RedirectResponse("/profile?success=Profile+picture+updated", status_code=303)


@router.post("/profile/remove-picture")
def remove_profile_picture(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login")
    
    user.profile_picture = None
    user.profile_picture_type = None
    db.commit()
    
    return RedirectResponse("/profile?success=Profile+picture+removed", status_code=303)


@router.get("/api/profile-picture/{user_id}")
def get_profile_picture(user_id: int, db: Session = Depends(get_db)):
    """Serve profile picture as image."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.profile_picture:
        # Return a default placeholder
        return Response(status_code=404)
    
    return Response(
        content=user.profile_picture,
        media_type=user.profile_picture_type or "image/jpeg"
    )


@router.post("/profile/toggle-dark-mode")
def toggle_dark_mode(request: Request, db: Session = Depends(get_db)):
    """Toggle dark mode preference."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    
    user.dark_mode = not user.dark_mode
    db.commit()
    
    return JSONResponse({"dark_mode": user.dark_mode})


@router.post("/profile/delete-all-data")
def delete_all_data(
    request: Request,
    db: Session = Depends(get_db),
    confirmation1: str = Form(...),
    confirmation2: str = Form(...),
    password: str = Form(...)
):
    """Delete all user data with multiple confirmations."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login")
    
    # Check confirmations
    if confirmation1 != "DELETE" or confirmation2 != user.username:
        return RedirectResponse("/profile?error=Confirmation+failed.+Please+follow+instructions+exactly", status_code=303)
    
    # Verify password
    if not verify_password(password, user.password_hash):
        return RedirectResponse("/profile?error=Password+verification+failed", status_code=303)
    
    # Import models to delete user data
    from app.models.income_taxes import IncomeTaxes
    from app.models.expense import Category, SubCategory, Expense
    from app.models.budget import BudgetCategory, FixedCost, BudgetItem
    
    # Delete all user data in order (respect foreign keys)
    db.query(Expense).filter(Expense.user_id == user.id).delete()
    db.query(SubCategory).filter(SubCategory.category_id.in_(
        db.query(Category.id).filter(Category.user_id == user.id)
    )).delete(synchronize_session='fetch')
    db.query(Category).filter(Category.user_id == user.id).delete()
    db.query(BudgetItem).filter(BudgetItem.user_id == user.id).delete()
    db.query(FixedCost).filter(FixedCost.user_id == user.id).delete()
    db.query(BudgetCategory).filter(BudgetCategory.user_id == user.id).delete()
    db.query(IncomeTaxes).filter(IncomeTaxes.user_id == user.id).delete()
    db.query(User).filter(User.id == user.id).delete()
    
    db.commit()
    
    # Clear cookie and redirect to login
    response = RedirectResponse("/login?message=Account+deleted+successfully", status_code=303)
    response.delete_cookie("username")
    return response

