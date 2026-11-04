from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import get_db
from .errors import APIError
from .models import Profile
from .runtime import Runtime, get_runtime

DB = Annotated[Session, Depends(get_db)]


def runtime_dep() -> Runtime:
    return get_runtime()


RT = Annotated[Runtime, Depends(runtime_dep)]


def current_profile(db: DB, x_profile_id: Annotated[str | None, Header()] = None) -> Profile:
    """Personal mode: the oldest profile unless a specific one is requested.

    The data model never assumes a single hard-coded id; a future multi-user
    version replaces this dependency with real authentication.
    """
    if x_profile_id:
        profile = db.get(Profile, x_profile_id)
    else:
        profile = db.scalars(select(Profile).order_by(Profile.created_at)).first()
    if profile is None:
        raise APIError(409, "profile_required", "create a profile first")
    return profile


CurrentProfile = Annotated[Profile, Depends(current_profile)]
