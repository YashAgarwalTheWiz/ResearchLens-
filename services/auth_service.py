import uuid
import psycopg2
from passlib.context import CryptContext
from config import DATABASE_URL

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def get_connection():
    return psycopg2.connect(DATABASE_URL)


# --- Password helpers ---

def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    return pwd_context.verify(password, hashed)


# --- Register ---

def register_user(email: str, password: str) -> dict:
    conn = get_connection()
    cur = conn.cursor()

    # Prevent duplicate accounts
    cur.execute("SELECT user_id FROM rpa_users WHERE email = %s", (email,))
    if cur.fetchone():
        cur.close()
        conn.close()
        return {"success": False, "message": "Email already registered"}

    hashed = hash_password(password)
    cur.execute(
        "INSERT INTO rpa_users (email, password_hash) VALUES (%s, %s) RETURNING user_id",
        (email, hashed)
    )
    user_id = str(cur.fetchone()[0])
    conn.commit()
    cur.close()
    conn.close()
    return {"success": True, "user_id": user_id}


# --- Login ---

def login_user(email: str, password: str) -> dict:
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT user_id, password_hash FROM rpa_users WHERE email = %s", (email,))
    row = cur.fetchone()
    cur.close()
    conn.close()

    # Same error message for wrong email or wrong password — don't leak which one
    if not row:
        return {"success": False, "message": "Invalid email or password"}

    user_id, stored_hash = str(row[0]), row[1]

    if not verify_password(password, stored_hash):
        return {"success": False, "message": "Invalid email or password"}

    token = generate_token(user_id)
    return {"success": True, "token": token, "user_id": user_id}


# --- Token helpers ---

def generate_token(user_id: str) -> str:
    token = str(uuid.uuid4())
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO rpa_user_tokens (token, user_id) VALUES (%s, %s)",
        (token, user_id)
    )
    conn.commit()
    cur.close()
    conn.close()
    return token


def validate_token(token: str) -> str | None:
    """Returns user_id if token is valid, None if not."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT user_id FROM rpa_user_tokens WHERE token = %s",
        (token,)
    )
    row = cur.fetchone()
    cur.close()
    conn.close()
    return str(row[0]) if row else None