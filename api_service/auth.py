import base64
import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone

import jwt
import psycopg
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from psycopg import sql
from psycopg.rows import dict_row


ALGORITHM = "HS256"
API_V1_PREFIX = "/api/v1"
oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{API_V1_PREFIX}/auth/token")


def _env(name: str, default: str) -> str:
    return os.getenv(name, default)


def get_secret_key() -> str:
    return _env("API_SECRET_KEY", "change-this-local-api-secret")


def get_access_token_expire_minutes() -> int:
    return int(_env("API_ACCESS_TOKEN_EXPIRE_MINUTES", "30"))


def get_postgres_db() -> str:
    return _env("POSTGRES_DB", "dsassignment")


def get_postgres_user() -> str:
    return _env("POSTGRES_USER", "ds_user")


def get_postgres_password() -> str:
    return _env("POSTGRES_PASSWORD", "ds_password")


def get_postgres_host() -> str:
    return _env("POSTGRES_HOST", "postgres")


def get_postgres_port() -> int:
    return int(_env("POSTGRES_PORT", "5432"))


def get_user_account_table() -> str:
    return _env("POSTGRES_USER_ACCOUNT_TABLE", "user_account")


def hash_password(password: str, salt: bytes, iterations: int = 600_000) -> str:
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    encoded_salt = base64.urlsafe_b64encode(salt).decode("utf-8")
    encoded_digest = base64.urlsafe_b64encode(digest).decode("utf-8")
    return f"pbkdf2_sha256:{iterations}:{encoded_salt}:{encoded_digest}"


def verify_password(password: str, stored_hash: str) -> bool:
    if len(stored_hash) == 64 and all(character in "0123456789abcdefABCDEF" for character in stored_hash):
        candidate_hash = hashlib.sha256(password.encode("utf-8")).hexdigest()
        return hmac.compare_digest(candidate_hash, stored_hash.lower())

    try:
        scheme, raw_iterations, encoded_salt, encoded_digest = stored_hash.split(":", 3)
    except ValueError:
        return False

    if scheme != "pbkdf2_sha256":
        return False

    salt = base64.urlsafe_b64decode(encoded_salt.encode("utf-8"))
    expected_hash = hash_password(password, salt=salt, iterations=int(raw_iterations))
    return hmac.compare_digest(expected_hash, stored_hash)


def get_user_account_by_username(username: str) -> dict | None:
    query = sql.SQL(
        """
        SELECT user_id, username, password
        FROM {}
        WHERE username = %s
        LIMIT 1
        """
    ).format(sql.Identifier(get_user_account_table()))
    with psycopg.connect(
        dbname=get_postgres_db(),
        user=get_postgres_user(),
        password=get_postgres_password(),
        host=get_postgres_host(),
        port=get_postgres_port(),
        row_factory=dict_row,
    ) as connection:
        with connection.cursor() as cursor:
            cursor.execute(query, (username,))
            return cursor.fetchone()


def create_user_account(username: str, password: str) -> dict:
    existing_account = get_user_account_by_username(username)
    if existing_account is not None:
        raise ValueError(f"Username '{username}' already exists.")

    password_hash = hash_password(password, salt=secrets.token_bytes(16))
    with psycopg.connect(
        dbname=get_postgres_db(),
        user=get_postgres_user(),
        password=get_postgres_password(),
        host=get_postgres_host(),
        port=get_postgres_port(),
        row_factory=dict_row,
    ) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                sql.SQL(
                    """
                    INSERT INTO {} (user_id, username, password)
                    VALUES (
                        COALESCE((SELECT MAX(user_id) + 1 FROM {}), 1),
                        %s,
                        %s
                    )
                    RETURNING user_id, username
                    """
                ).format(
                    sql.Identifier(get_user_account_table()),
                    sql.Identifier(get_user_account_table()),
                ),
                (username, password_hash),
            )
            created_user = cursor.fetchone()
        connection.commit()
    return created_user


def authenticate_user(username: str, password: str) -> bool:
    try:
        account = get_user_account_by_username(username)
    except psycopg.Error:
        return False

    if account is None:
        return False
    return verify_password(password, account["password"])


def create_access_token(subject: str) -> tuple[str, datetime]:
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=get_access_token_expire_minutes())
    payload = {"sub": subject, "exp": expires_at}
    token = jwt.encode(payload, get_secret_key(), algorithm=ALGORITHM)
    return token, expires_at


def decode_access_token(token: str) -> dict:
    try:
        return jwt.decode(token, get_secret_key(), algorithms=[ALGORITHM])
    except jwt.InvalidTokenError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from error


def get_current_username(token: str = Depends(oauth2_scheme)) -> str:
    payload = decode_access_token(token)
    username = payload.get("sub")
    if not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token subject",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return username
