"""Bad: dynamic SQL via concatenation, %, .format(), and f-strings."""
import sqlite3


def find_user_by_name(conn: sqlite3.Connection, name: str):
    cur = conn.cursor()
    # 1) string concatenation
    cur.execute("SELECT id, email FROM users WHERE name = '" + name + "'")
    return cur.fetchone()


def update_user_email(conn: sqlite3.Connection, user_id: int, email: str):
    cur = conn.cursor()
    # 2) %-formatting
    cur.execute("UPDATE users SET email = '%s' WHERE id = %d" % (email, user_id))


def delete_orders(conn: sqlite3.Connection, status: str):
    cur = conn.cursor()
    # 3) .format()
    cur.execute("DELETE FROM orders WHERE status = '{}'".format(status))


def list_products(conn: sqlite3.Connection, category: str, limit: int):
    cur = conn.cursor()
    # 4) f-string
    cur.execute(f"SELECT * FROM products WHERE category = '{category}' LIMIT {limit}")
    return cur.fetchall()


def bulk_insert(conn: sqlite3.Connection, table: str, rows):
    cur = conn.cursor()
    # 5) executemany with f-string SQL
    cur.executemany(f"INSERT INTO {table} (a, b) VALUES (?, ?)", rows)
