#!/usr/bin/env python3
"""
JIS ChatSQL SQL Gateway (Day 1).

Safe SQL execution API for Flowise:
- Health check
- Schema discovery helpers
- Query endpoint with strict readonly guardrails
- JSONL audit logging
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import mysql.connector
import sqlparse
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

APP_VERSION = "0.1.0"

DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = int(os.getenv("DB_PORT", "3306"))
DB_NAME = os.getenv("DB_NAME", "jisparking")
DB_USER = os.getenv("DB_USER", "reader_user")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")

SQL_MAX_ROWS = int(os.getenv("SQL_MAX_ROWS", "200"))
SQL_TIMEOUT_MS = int(os.getenv("SQL_TIMEOUT_MS", "15000"))
SQL_AUDIT_FILE = os.getenv("SQL_AUDIT_FILE", "/tmp/jis_chatsql_audit.jsonl")

ALLOWED_TABLES = {t.strip().lower() for t in os.getenv("ALLOWED_TABLES", "").split(",") if t.strip()}
ALLOWED_VIEWS = {v.strip().lower() for v in os.getenv("ALLOWED_VIEWS", "").split(",") if v.strip()}
SQL_REQUIRE_ALLOWLIST = os.getenv("SQL_REQUIRE_ALLOWLIST", "false").lower() == "true"

# Block any non-readonly keywords.
BLOCKED_KEYWORDS = {
    "insert",
    "update",
    "delete",
    "replace",
    "truncate",
    "drop",
    "alter",
    "create",
    "rename",
    "grant",
    "revoke",
    "set",
    "call",
    "load",
    "outfile",
    "infile",
    "lock",
    "unlock",
    "analyze",
    "optimize",
}

TABLE_REF_RE = re.compile(
    r"(?:from|join)\s+`?([a-zA-Z0-9_]+)`?(?:\.`?([a-zA-Z0-9_]+)`?)?",
    re.IGNORECASE,
)

app = FastAPI(title="JIS ChatSQL SQL Gateway", version=APP_VERSION)


class QueryRequest(BaseModel):
    sql: str = Field(min_length=1, max_length=12000)
    request_id: Optional[str] = Field(default=None, max_length=80)
    caller: Optional[str] = Field(default="flowise", max_length=80)


class QueryResponse(BaseModel):
    request_id: Optional[str]
    row_count: int
    truncated: bool
    columns: List[str]
    rows: List[Dict[str, Any]]
    elapsed_ms: int


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def db_connection() -> mysql.connector.MySQLConnection:
    return mysql.connector.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
        connection_timeout=8,
        autocommit=True,
    )


def normalize_sql(sql: str) -> str:
    return sql.strip().rstrip(";").strip()


def parse_single_statement(sql: str) -> str:
    statements = [s for s in sqlparse.parse(sql) if s.value.strip()]
    if len(statements) != 1:
        raise HTTPException(status_code=400, detail="Only one SQL statement is allowed")
    return statements[0].value.strip()


def ensure_select_only(sql: str) -> None:
    lowered = sql.lower()
    if not lowered.startswith("select"):
        raise HTTPException(status_code=400, detail="Only SELECT queries are allowed")

    words = set(re.findall(r"[a-zA-Z_]+", lowered))
    blocked_found = sorted(w for w in words if w in BLOCKED_KEYWORDS)
    if blocked_found:
        raise HTTPException(status_code=400, detail=f"Blocked keyword(s): {', '.join(blocked_found)}")


def extract_referenced_objects(sql: str) -> Set[str]:
    refs: Set[str] = set()
    for m in TABLE_REF_RE.finditer(sql):
        left = (m.group(1) or "").lower()
        right = (m.group(2) or "").lower()
        if right:
            refs.add(right)
        elif left and left not in {"select"}:
            refs.add(left)
    return refs


def enforce_allowlist(sql: str) -> None:
    if not SQL_REQUIRE_ALLOWLIST:
        return

    allow = ALLOWED_TABLES | ALLOWED_VIEWS
    if not allow:
        raise HTTPException(status_code=500, detail="Allowlist required but empty")

    refs = extract_referenced_objects(sql)
    disallowed = sorted(r for r in refs if r not in allow)
    if disallowed:
        raise HTTPException(status_code=400, detail=f"Disallowed object(s): {', '.join(disallowed)}")


def audit_log(payload: Dict[str, Any]) -> None:
    try:
        path = Path(SQL_AUDIT_FILE)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=True, default=str) + "\n")
    except Exception:
        # Never block query flow by audit write errors.
        pass


@app.get("/health")
def health() -> Dict[str, Any]:
    try:
        conn = db_connection()
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT NOW() AS now_ts, DATABASE() AS db_name, USER() AS db_user")
        row = cur.fetchone() or {}
        cur.close()
        conn.close()

        return {
            "status": "ok",
            "service": "jis-chatsql-sql-gateway",
            "version": APP_VERSION,
            "time": now_iso(),
            "db": row,
            "guardrails": {
                "max_rows": SQL_MAX_ROWS,
                "timeout_ms": SQL_TIMEOUT_MS,
                "require_allowlist": SQL_REQUIRE_ALLOWLIST,
            },
        }
    except Exception as e:
        return {
            "status": "error",
            "service": "jis-chatsql-sql-gateway",
            "version": APP_VERSION,
            "time": now_iso(),
            "error": str(e),
        }


@app.get("/schema/tables")
def schema_tables(limit: int = 200) -> Dict[str, Any]:
    if limit < 1 or limit > 1000:
        raise HTTPException(status_code=400, detail="limit must be between 1 and 1000")

    conn = db_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute(
        """
        SELECT table_name, table_rows, table_type,
               ROUND((data_length + index_length) / 1024 / 1024, 2) AS size_mb
        FROM information_schema.tables
        WHERE table_schema = %s
        ORDER BY (data_length + index_length) DESC
        LIMIT %s
        """,
        (DB_NAME, limit),
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()

    return {"database": DB_NAME, "count": len(rows), "rows": rows}


@app.post("/query", response_model=QueryResponse)
def query(req: QueryRequest) -> QueryResponse:
    sql = normalize_sql(req.sql)
    sql = parse_single_statement(sql)
    ensure_select_only(sql)
    enforce_allowlist(sql)

    start = datetime.now(timezone.utc)
    conn = db_connection()
    cur = conn.cursor(dictionary=True)

    # Enforce server-side timeout for this session/query.
    cur.execute(f"SET SESSION MAX_EXECUTION_TIME = {SQL_TIMEOUT_MS}")

    limited_sql = f"SELECT * FROM ({sql}) AS q LIMIT {SQL_MAX_ROWS + 1}"
    try:
        cur.execute(limited_sql)
        fetched = cur.fetchall()
    except mysql.connector.Error as e:
        audit_log(
            {
                "time": now_iso(),
                "request_id": req.request_id,
                "caller": req.caller,
                "status": "error",
                "sql": sql,
                "error": str(e),
            }
        )
        cur.close()
        conn.close()
        raise HTTPException(status_code=400, detail=f"SQL error: {str(e)}")

    columns = list(fetched[0].keys()) if fetched else []
    truncated = len(fetched) > SQL_MAX_ROWS
    if truncated:
        fetched = fetched[:SQL_MAX_ROWS]

    elapsed_ms = int((datetime.now(timezone.utc) - start).total_seconds() * 1000)

    audit_log(
        {
            "time": now_iso(),
            "request_id": req.request_id,
            "caller": req.caller,
            "status": "ok",
            "row_count": len(fetched),
            "truncated": truncated,
            "elapsed_ms": elapsed_ms,
            "sql": sql,
            "columns": columns,
        }
    )

    cur.close()
    conn.close()

    return QueryResponse(
        request_id=req.request_id,
        row_count=len(fetched),
        truncated=truncated,
        columns=columns,
        rows=fetched,
        elapsed_ms=elapsed_ms,
    )
