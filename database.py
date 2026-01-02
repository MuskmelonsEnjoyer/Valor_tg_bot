import sqlite3

def init_db():
    with sqlite3.connect("bot_data.db") as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                t_token TEXT
            )
        """)

def save_user_token(user_id: int, token: str):
    with sqlite3.connect("bot_data.db") as conn:
        conn.execute(
            "INSERT OR REPLACE INTO users (user_id, t_token) VALUES (?, ?)",
            (user_id, token)
        )

def delete_user_token(user_id: int):
    with sqlite3.connect("bot_data.db") as conn:
        conn.execute(
            "DELETE FROM users WHERE user_id = ?",
            (user_id,)
        )

def get_user_token(user_id: int) -> str:
    with sqlite3.connect("bot_data.db") as conn:
        res = conn.execute("SELECT t_token FROM users WHERE user_id = ?", (user_id,)).fetchone()
        if res:
            return res[0]
        return None