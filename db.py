import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "library.db")


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def execute_query(sql, params=None):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(sql, params or ())
    return cursor, conn


def commit_and_close(conn):
    conn.commit()
    conn.close()


def rollback_and_close(conn):
    conn.rollback()
    conn.close()
