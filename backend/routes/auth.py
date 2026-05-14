import secrets
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from backend.auth import (
    create_access_token, create_refresh_token, create_otp_token, decode_otp_token,
    decode_token, hash_password, verify_password,
)
from backend.database import get_db
from backend.email_utils import send_otp_email
from backend.model import EmailOTP, User
from backend.rate_limit import check_rate_limit
from backend.schemas import (
    CompleteSignupRequest, LoginRequest, RefreshRequest, SendOtpRequest,
    SignupRequest, TokenResponse, UserProfile, VerifyEmailRequest,
    VerifyOtpRequest, VerifyOtpResponse,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/signup", response_model=UserProfile, status_code=status.HTTP_201_CREATED)
def signup(body: SignupRequest, request: Request, db: Session = Depends(get_db)):
    check_rate_limit(f"signup:{request.client.host}", max_calls=5, window_seconds=600)

    if db.query(User).filter(User.email == body.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(
        email=body.email,
        hashed_password=hash_password(body.password),
        is_verified=False,
        company_name=body.company_name,
        employee_count=body.employee_count,
        notes=body.notes,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/send-otp")
def send_otp(body: SendOtpRequest, request: Request, db: Session = Depends(get_db)):
    check_rate_limit(f"otp:{body.email}", max_calls=5, window_seconds=600)
    if db.query(User).filter(User.email == body.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")

    code = f"{secrets.randbelow(1000000):06d}"
    expires = datetime.now(timezone.utc) + timedelta(minutes=10)

    otp = db.query(EmailOTP).filter(EmailOTP.email == body.email).first()
    if otp:
        otp.otp_code = code
        otp.expires_at = expires
        otp.used = False
    else:
        otp = EmailOTP(email=body.email, otp_code=code, expires_at=expires)
        db.add(otp)
    db.commit()

    send_otp_email(body.email, code)
    return {"detail": "Verification code sent", "otp_hint": code}


@router.post("/verify-otp", response_model=VerifyOtpResponse)
def verify_otp(body: VerifyOtpRequest, request: Request, db: Session = Depends(get_db)):
    check_rate_limit(f"verify-otp:{body.email}", max_calls=10, window_seconds=900)
    otp = db.query(EmailOTP).filter(
        EmailOTP.email == body.email,
        EmailOTP.used == False,  # noqa: E712
    ).first()

    if not otp or otp.otp_code != body.otp_code:
        raise HTTPException(status_code=400, detail="Invalid verification code")
    if otp.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Verification code expired")

    otp.used = True
    db.commit()

    return VerifyOtpResponse(verified_token=create_otp_token(body.email))


@router.post("/complete-signup", response_model=UserProfile, status_code=status.HTTP_201_CREATED)
def complete_signup(body: CompleteSignupRequest, db: Session = Depends(get_db)):
    try:
        email = decode_otp_token(body.verified_token)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid or expired verification token")

    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(
        email=email,
        hashed_password=hash_password(body.password),
        is_verified=True,
        company_name=body.company_name,
        employee_count=body.employee_count,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.get("/verify-email")
def verify_email(token: str, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.verification_token == token).first()
    if not user:
        raise HTTPException(status_code=400, detail="Invalid or expired token")
    user.is_verified = True
    user.verification_token = None
    db.commit()
    return {"detail": "Email verified successfully"}


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, request: Request, db: Session = Depends(get_db)):
    check_rate_limit(f"login:{request.client.host}", max_calls=10, window_seconds=300)
    user = db.query(User).filter(User.email == body.email).first()
    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if not user.is_verified:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Email not verified")

    return TokenResponse(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
    )


@router.post("/refresh", response_model=TokenResponse)
def refresh(body: RefreshRequest, db: Session = Depends(get_db)):
    try:
        user_id = decode_token(body.refresh_token, "refresh")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))

    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    return TokenResponse(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
    )
