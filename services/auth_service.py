import uuid
from passlib.context import CryptContext

from services.db import get_connection

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# --- Password helpers ---

def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    return pwd_context.verify(password, hashed)


# --- Register ---

def register_user(email: str, password: str) -> dict:
    conn = get_connection()

    # Prevent duplicate accounts
    if conn.execute("SELECT user_id FROM rpa_users WHERE email = ?", (email,)).fetchone():
        conn.close()
        return {"success": False, "message": "Email already registered"}

    user_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO rpa_users (user_id, email, password_hash) VALUES (?, ?, ?)",
        (user_id, email, hash_password(password))
    )
    conn.commit()
    conn.close()
    return {"success": True, "user_id": user_id}


# --- Login ---

def login_user(email: str, password: str) -> dict:
    conn = get_connection()
    row = conn.execute("SELECT user_id, password_hash FROM rpa_users WHERE email = ?", (email,)).fetchone()
    conn.close()

    # Same error message for wrong email or wrong password — don't leak which one
    if not row:
        return {"success": False, "message": "Invalid email or password"}

    user_id, stored_hash = row[0], row[1]

    if not verify_password(password, stored_hash):
        return {"success": False, "message": "Invalid email or password"}

    token = generate_token(user_id)
    return {"success": True, "token": token, "user_id": user_id}


# --- Token helpers ---

def generate_token(user_id: str) -> str:
    token = str(uuid.uuid4())
    conn = get_connection()
    conn.execute("INSERT INTO rpa_user_tokens (token, user_id) VALUES (?, ?)", (token, user_id))
    conn.commit()
    conn.close()
    return token


def validate_token(token: str) -> str | None:
    """Returns user_id if token is valid, None if not."""
    conn = get_connection()
    row = conn.execute("SELECT user_id FROM rpa_user_tokens WHERE token = ?", (token,)).fetchone()
    conn.close()
    return row[0] if row else None