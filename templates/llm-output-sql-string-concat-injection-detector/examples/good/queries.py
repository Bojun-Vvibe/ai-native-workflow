"""Good: parameterized queries — placeholders only, no dynamic SQL strings."""
import sqlite3


def find_user_by_name(conn: sqlite3.Connection, name: str):
    cur = conn.cursor()
    cur.execute("SELECT id, email FROM users WHERE name = ?", (name,))
    return cur.fetchone()


def update_user_email(conn: sqlite3.Connection, user_id: int, email: str):
    cur = conn.cursor()
    cur.execute("UPDATE users SET email = ? WHERE id = ?", (email, user_id))


def delete_orders(conn: sqlite3.Connection, status: str):
    cur = conn.cursor()
    cur.execute("DELETE FROM orders WHERE status = ?", (status,))


def list_products(conn: sqlite3.Connection, category: str, limit: int):
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM products WHERE category = ? LIMIT ?",
        (category, limit),
    )
    return cur.fetchall()


def bulk_insert_users(conn: sqlite3.Connection, rows):
    cur = conn.cursor()
    # Table name is a literal — safe; values are placeholders.
    cur.executemany("INSERT INTO users (name, email) VALUES (?, ?)", rows)
