"""FastAPI dependencies shared by the route modules.

Each route module used to declare these aliases itself. They are plain `Annotated` type aliases over
the existing providers, so a handler asks for `session: SessionDep` or `settings: SettingsDep` and
FastAPI supplies them. Tests override `get_session` (from `app.db.session`) as before.
"""

from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.config import Settings
from app.db.session import get_session

SessionDep = Annotated[Session, Depends(get_session)]
"""A database session for the request, closed afterwards (`app.db.session.get_session`)."""


def get_app_settings(request: Request) -> Settings:
    """The settings the app was created with (`create_app` stores them on `app.state`)."""
    settings: Settings = request.app.state.settings
    return settings


SettingsDep = Annotated[Settings, Depends(get_app_settings)]
