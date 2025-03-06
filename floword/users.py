from __future__ import annotations

import json

from fastapi import HTTPException, Request, status
from fastapi.params import Depends
from jose import jws
from pydantic import BaseModel

from floword.config import Config, get_config


def verify_token(token: str, secret_key: str) -> dict:
    return json.loads(jws.verify(token, secret_key, algorithms="HS256").decode())


class User(BaseModel):
    user_id: str

    @classmethod
    def init_annonymous(cls) -> User:
        return User(user_id="_anonymous")

    @classmethod
    def from_jwt_token(cls, jwt_token: str, jwt_secret_token: str) -> User:
        return cls.model_validate(verify_token(jwt_token, jwt_secret_token))


def get_current_user(
    request: Request,
    config: Config = Depends(get_config),
) -> User:
    if not config.allow_anonymous and not config.jwt_secret_token:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="JWT secret token not set when anonymous access not allowed",
        )

    auth_header = request.headers.get("Authorization")
    if auth_header:
        t, jwt_token, *_ = auth_header.split(" ")
        if t != "Bearer":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Only Bearer authentication supported",
            )
        return User.from_jwt_token(jwt_token, config.jwt_secret_token)
    elif config.allow_anonymous:
        return User.init_annonymous()

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
    )
