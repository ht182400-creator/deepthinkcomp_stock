# -*- coding: utf-8 -*-
"""
SQLite 数据库：market.db
- kline_cache：K线缓存（结构化，预留切换）
- analysis_log：复盘/分析记录（Sprint 3 复盘使用）
线程安全（每次连接独立）。
"""
import json
import sqlite3
import threading
import time

import config

_db_lock = threading.Lock()


def _connect():
    conn = sqlite3.connect(config.SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    # WAL：读写并发互不阻塞，避免批量写/分析日志时阻塞查询
    try:
        conn.execute("PRAGMA journal_mode=WAL")
    except sqlite3.OperationalError:
        pass
    return conn


def init_db():
    """建表（幂等）。应用启动时调用。"""
    with _db_lock, _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS kline_cache (
                code TEXT NOT NULL,
                period TEXT NOT NULL,
                ts INTEGER NOT NULL,
                data TEXT NOT NULL,
                PRIMARY KEY (code, period)
            )""")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS analysis_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts INTEGER NOT NULL,
                code TEXT NOT NULL,
                data TEXT NOT NULL
            )""")
        conn.commit()


# ---------- kline_cache ----------
def kline_cache_get(code: str, period: str, max_age_s: int = 3600 * 24):
    with _db_lock, _connect() as conn:
        row = conn.execute(
            "SELECT ts, data FROM kline_cache WHERE code=? AND period=?",
            (code, period)).fetchone()
        if row and time.time() - row["ts"] < max_age_s:
            try:
                return json.loads(row["data"])
            except Exception:
                return None
    return None


def kline_cache_set(code: str, period: str, rows: list):
    with _db_lock, _connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO kline_cache (code, period, ts, data) VALUES (?,?,?,?)",
            (code, period, int(time.time()), json.dumps(rows, ensure_ascii=False)))
        conn.commit()


# ---------- analysis_log ----------
def log_analysis(code: str, data: dict):
    with _db_lock, _connect() as conn:
        conn.execute(
            "INSERT INTO analysis_log (ts, code, data) VALUES (?,?,?)",
            (int(time.time()), code, json.dumps(data, ensure_ascii=False)))
        conn.commit()


def get_analysis_log(code: str = None, limit: int = 50):
    with _db_lock, _connect() as conn:
        if code:
            rows = conn.execute(
                "SELECT * FROM analysis_log WHERE code=? ORDER BY id DESC LIMIT ?",
                (code, limit)).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM analysis_log ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]
