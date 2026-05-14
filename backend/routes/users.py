from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.dependencies import get_current_user
from backend.model import BusinessStrategy, User
from backend.schemas import UserProfile, UserUpdate

router = APIRouter(prefix="/users", tags=["users"])


def _with_strategy_flag(user: User, db: Session) -> dict:
    has_strategy = (
        db.query(BusinessStrategy)
        .filter(BusinessStrategy.user_id == user.id)
        .count()
        > 0
    )
    base = UserProfile.model_validate(user).model_dump()
    base["has_strategy"] = has_strategy
    return base


@router.get("/me", response_model=UserProfile)
def get_profile(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _with_strategy_flag(current_user, db)


@router.patch("/me", response_model=UserProfile)
def update_profile(
    body: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(current_user, field, value)
    db.commit()
    db.refresh(current_user)
    return _with_strategy_flag(current_user, db)
