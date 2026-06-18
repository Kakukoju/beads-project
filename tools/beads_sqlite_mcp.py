#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
beads_sqlite_mcp.py

Amazon Q Developer / MCP server (STDIO)
for cross-database SQLite querying and bead process comparison.

Databases:
- /opt/beadsops/data/P01_Beads_IPQC.db
- /opt/beadsops/data/P01_formualte_schedule.db
- /opt/beadsops/data/work_orders.db

Tools:
- inspect_sqlite_catalog
- query_bead_records
- compare_bead_runs

Notes:
- This v1 uses heuristic column matching because actual schemas may differ.
- If your real column names are known, edit COLUMN_CANDIDATES for better accuracy.
"""

from __future__ import annotations

import io as _io
import json
import math
import os
import re
import sqlite3
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# MCP SDK
from mcp.server.fastmcp import FastMCP


# =========================
# Config
# =========================
DB_PATHS = {
    "ipqc": "/opt/beadsops/data/P01_Beads_IPQC.db",
    "schedule": "/opt/beadsops/data/P01_formualte_schedule.db",
    "work_orders": "/opt/beadsops/data/work_orders.db",
}

MAX_PREVIEW_ROWS = 200
SQL_TIMEOUT_SEC = 20

# Heuristic column aliases. Add your real field names here if needed.
COLUMN_CANDIDATES = {
    "work_order": [
        "work_order", "workorder", "wo", "工單", "工單號", "工單編號",
        "en 編號", "en編號", "en_number", "order_no", "order_number"
    ],
    "date": [
        "date", "日期", "生產日期", "製造日期", "production_date",
        "created_at", "updated_at", "time", "datetime", "rd給藥時間"
    ],
    "marker": [
        "marker", "bead", "bead_name", "beadname", "品名", "名稱",
        "測項", "項目", "marker_name"
    ],
    "lot": [
        "lot", "lot_no", "lotno", "批號", "批次", "batch", "batch_no"
    ],
    "value_like": [
        "value", "result", "測值", "數值", "平均", "avg", "mean",
        "cv", "sd", "yield", "良率", "size", "diameter", "濃度",
        "ph", "temperature", "temp", "humidity", "壓力", "時間"
    ],
}

TEXT_MATCH_KEYS = {"work_order", "marker", "lot"}


# =========================
# Utilities
# =========================
def normalize_name(name: str) -> str:
    s = str(name or "").strip().lower()
    s = s.replace(" ", "").replace("_", "").replace("-", "")
    return s


def safe_float(v: Any) -> Optional[float]:
    if v is None:
        return None
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        if math.isnan(v) or math.isinf(v):
            return None
        return float(v)
    s = str(v).strip()
    if not s:
        return None
    s = s.replace(",", "")
    try:
        return float(s)
    except Exception:
        return None


def parse_date_like(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value

    s = str(value).strip()
    if not s:
        return None

    patterns = [
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%Y-%m-%d %H:%M:%S",
        "%Y/%m/%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y/%m/%d %H:%M",
        "%m/%d/%Y",
        "%m-%d-%Y",
    ]
    for fmt in patterns:
        try:
            return datetime.strptime(s, fmt)
        except Exception:
            pass

    # Handle "3月10日" style loosely by giving current year if needed
    m = re.match(r"^\s*(\d{1,2})月(\d{1,2})日\s*$", s)
    if m:
        now = datetime.now()
        try:
            return datetime(now.year, int(m.group(1)), int(m.group(2)))
        except Exception:
            return None

    return None


def date_in_range(value: Any, start_date: Optional[str], end_date: Optional[str]) -> bool:
    if not start_date and not end_date:
        return True

    dt = parse_date_like(value)
    if dt is None:
        return False

    start_dt = parse_date_like(start_date) if start_date else None
    end_dt = parse_date_like(end_date) if end_date else None

    if start_dt and dt < start_dt:
        return False
    if end_dt and dt > end_dt:
        return False
    return True


def text_match(value: Any, query: Optional[str]) -> bool:
    if not query:
        return True
    if value is None:
        return False
    return str(query).strip().lower() in str(value).strip().lower()


@dataclass
class TableInfo:
    db_key: str
    db_path: str
    table: str
    columns: List[str]
    matched_fields: Dict[str, Optional[str]]


# =========================
# SQLite introspection
# =========================
class SQLiteCatalog:
    def __init__(self, db_paths: Dict[str, str]) -> None:
        self.db_paths = db_paths
        self._table_cache: Dict[str, List[TableInfo]] = {}

    def _connect(self, db_path: str) -> sqlite3.Connection:
        conn = sqlite3.connect(db_path, timeout=SQL_TIMEOUT_SEC)
        conn.row_factory = sqlite3.Row
        return conn

    def _get_tables(self, db_key: str, db_path: str) -> List[TableInfo]:
        if db_key in self._table_cache:
            return self._table_cache[db_key]

        if not os.path.exists(db_path):
            self._table_cache[db_key] = []
            return []

        tables: List[TableInfo] = []
        with self._connect(db_path) as conn:
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            ).fetchall()

            for r in rows:
                table = r["name"]
                pragma_rows = conn.execute(f'PRAGMA table_info("{table}")').fetchall()
                cols = [x["name"] for x in pragma_rows]
                matched = self._match_columns(cols)
                tables.append(
                    TableInfo(
                        db_key=db_key,
                        db_path=db_path,
                        table=table,
                        columns=cols,
                        matched_fields=matched,
                    )
                )

        self._table_cache[db_key] = tables
        return tables

    def all_tables(self) -> List[TableInfo]:
        result: List[TableInfo] = []
        for db_key, db_path in self.db_paths.items():
            result.extend(self._get_tables(db_key, db_path))
        return result

    def _match_columns(self, columns: List[str]) -> Dict[str, Optional[str]]:
        normalized = {normalize_name(c): c for c in columns}
        out: Dict[str, Optional[str]] = {}

        for field, aliases in COLUMN_CANDIDATES.items():
            hit = None
            for alias in aliases:
                n = normalize_name(alias)
                if n in normalized:
                    hit = normalized[n]
                    break

            if hit is None:
                # fuzzy contains
                for c in columns:
                    nc = normalize_name(c)
                    if any(normalize_name(alias) in nc or nc in normalize_name(alias) for alias in aliases):
                        hit = c
                        break

            out[field] = hit
        return out


CATALOG = SQLiteCatalog(DB_PATHS)


# =========================
# Query and analysis engine
# =========================
class BeadAnalyzer:
    def __init__(self, catalog: SQLiteCatalog) -> None:
        self.catalog = catalog

    def inspect_catalog(self) -> Dict[str, Any]:
        result = []
        for t in self.catalog.all_tables():
            result.append({
                "db_key": t.db_key,
                "db_path": t.db_path,
                "table": t.table,
                "columns": t.columns,
                "matched_fields": t.matched_fields,
            })
        return {"databases": result}

    def query_records(
        self,
        work_order: Optional[str] = None,
        marker: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = MAX_PREVIEW_ROWS,
    ) -> Dict[str, Any]:
        matched_rows: List[Dict[str, Any]] = []
        scanned_tables = 0

        for t in self.catalog.all_tables():
            scanned_tables += 1
            try:
                rows = self._query_single_table(
                    t=t,
                    work_order=work_order,
                    marker=marker,
                    start_date=start_date,
                    end_date=end_date,
                    limit=limit,
                )
                matched_rows.extend(rows)
            except Exception as e:
                matched_rows.append({
                    "_db_key": t.db_key,
                    "_table": t.table,
                    "_error": str(e),
                })

        matched_rows = matched_rows[:limit]
        return {
            "filters": {
                "work_order": work_order,
                "marker": marker,
                "start_date": start_date,
                "end_date": end_date,
                "limit": limit,
            },
            "scanned_tables": scanned_tables,
            "matched_count": len(matched_rows),
            "rows": matched_rows,
        }

    def _query_single_table(
        self,
        t: TableInfo,
        work_order: Optional[str],
        marker: Optional[str],
        start_date: Optional[str],
        end_date: Optional[str],
        limit: int,
    ) -> List[Dict[str, Any]]:
        if not os.path.exists(t.db_path):
            return []

        with sqlite3.connect(t.db_path, timeout=SQL_TIMEOUT_SEC) as conn:
            conn.row_factory = sqlite3.Row
            sql = f'SELECT * FROM "{t.table}" LIMIT 1000'
            raw_rows = conn.execute(sql).fetchall()

        out: List[Dict[str, Any]] = []
        wo_col = t.matched_fields.get("work_order")
        marker_col = t.matched_fields.get("marker")
        date_col = t.matched_fields.get("date")
        lot_col = t.matched_fields.get("lot")

        for rr in raw_rows:
            row = dict(rr)

            if work_order and wo_col and not text_match(row.get(wo_col), work_order):
                continue
            if marker and marker_col and not text_match(row.get(marker_col), marker):
                continue
            if (start_date or end_date) and date_col and not date_in_range(row.get(date_col), start_date, end_date):
                continue

            # If field doesn't exist, allow broad pass but require at least one useful match
            broad_ok = True
            if work_order and not wo_col:
                broad_ok = any(text_match(v, work_order) for v in row.values())
            if broad_ok and marker and not marker_col:
                broad_ok = any(text_match(v, marker) for v in row.values())
            if not broad_ok:
                continue

            normalized_record = {
                "_db_key": t.db_key,
                "_db_path": t.db_path,
                "_table": t.table,
                "_matched_work_order_col": wo_col,
                "_matched_marker_col": marker_col,
                "_matched_date_col": date_col,
                "_matched_lot_col": lot_col,
                **row,
            }
            out.append(normalized_record)

            if len(out) >= limit:
                break

        return out

    def compare_runs(
        self,
        work_order: Optional[str] = None,
        marker: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        group_key: str = "marker",
        limit: int = MAX_PREVIEW_ROWS,
    ) -> Dict[str, Any]:
        queried = self.query_records(
            work_order=work_order,
            marker=marker,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
        )
        rows = queried["rows"]

        grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for row in rows:
            key = self._derive_group_key(row, group_key)
            grouped[key].append(row)

        comparisons = []
        for gk, items in grouped.items():
            comparisons.append(self._compare_group(gk, items))

        comparisons.sort(key=lambda x: x["difference_score"], reverse=True)

        return {
            "filters": queried["filters"],
            "group_key": group_key,
            "group_count": len(grouped),
            "comparisons": comparisons,
        }

    def _derive_group_key(self, row: Dict[str, Any], group_key: str) -> str:
        preferred_cols = {
            "marker": ["marker", "bead", "bead_name", "marker_name", "名稱", "品名", "測項"],
            "work_order": ["work_order", "workorder", "wo", "工單", "工單號", "工單編號"],
            "lot": ["lot", "lot_no", "batch", "批號", "批次"],
        }

        candidates = preferred_cols.get(group_key, preferred_cols["marker"])
        for c in candidates:
            for k, v in row.items():
                if normalize_name(k) == normalize_name(c) and v not in (None, ""):
                    return str(v)

        # fallback
        for k, v in row.items():
            if k.startswith("_"):
                continue
            if v not in (None, ""):
                return f"{group_key}:{v}"
        return "UNKNOWN"

    def _compare_group(self, group_value: str, items: List[Dict[str, Any]]) -> Dict[str, Any]:
        numeric_stats: Dict[str, List[Tuple[str, float]]] = defaultdict(list)
        text_stats: Dict[str, List[Tuple[str, str]]] = defaultdict(list)

        for row in items:
            source = f"{row.get('_db_key')}::{row.get('_table')}"
            for k, v in row.items():
                if k.startswith("_"):
                    continue
                fv = safe_float(v)
                if fv is not None:
                    numeric_stats[k].append((source, fv))
                elif v not in (None, ""):
                    text_stats[k].append((source, str(v)))

        numeric_diffs = []
        for col, vals in numeric_stats.items():
            uniq = sorted({v for _, v in vals})
            if len(uniq) >= 2:
                mn = min(uniq)
                mx = max(uniq)
                numeric_diffs.append({
                    "column": col,
                    "min": mn,
                    "max": mx,
                    "range": mx - mn,
                    "samples": vals[:20],
                })

        text_diffs = []
        for col, vals in text_stats.items():
            uniq = sorted({v for _, v in vals})
            if len(uniq) >= 2:
                text_diffs.append({
                    "column": col,
                    "distinct_values": uniq[:20],
                    "samples": vals[:20],
                })

        # crude score
        diff_score = len(numeric_diffs) * 2 + len(text_diffs)

        # sort biggest numeric differences first
        numeric_diffs.sort(key=lambda x: x["range"], reverse=True)
        text_diffs.sort(key=lambda x: len(x["distinct_values"]), reverse=True)

        return {
            "group_value": group_value,
            "row_count": len(items),
            "sources": sorted({f"{x.get('_db_key')}::{x.get('_table')}" for x in items}),
            "difference_score": diff_score,
            "numeric_differences": numeric_diffs[:30],
            "text_differences": text_diffs[:30],
            "preview_rows": items[:20],
        }


ANALYZER = BeadAnalyzer(CATALOG)


# =========================
# MCP server
# =========================
mcp = FastMCP("beads-sqlite-analysis")


@mcp.tool()
def inspect_sqlite_catalog() -> str:
    """
    Inspect the 3 SQLite databases, list tables, columns, and heuristic field matches.
    Use this first if schema is unclear.
    """
    result = ANALYZER.inspect_catalog()
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
def query_bead_records(
    work_order: str = "",
    marker: str = "",
    start_date: str = "",
    end_date: str = "",
    limit: int = 120,
) -> str:
    """
    Query records across the 3 SQLite databases by work order / marker / date range.
    Dates support formats like YYYY-MM-DD or YYYY/MM/DD.
    """
    result = ANALYZER.query_records(
        work_order=work_order or None,
        marker=marker or None,
        start_date=start_date or None,
        end_date=end_date or None,
        limit=max(1, min(limit, MAX_PREVIEW_ROWS)),
    )
    return json.dumps(result, ensure_ascii=False, indent=2, default=str)


@mcp.tool()
def compare_bead_runs(
    work_order: str = "",
    marker: str = "",
    start_date: str = "",
    end_date: str = "",
    group_key: str = "marker",
    limit: int = 150,
) -> str:
    """
    Compare same-bead process records across databases and identify parameter differences.

    group_key:
    - marker
    - work_order
    - lot
    """
    result = ANALYZER.compare_runs(
        work_order=work_order or None,
        marker=marker or None,
        start_date=start_date or None,
        end_date=end_date or None,
        group_key=group_key or "marker",
        limit=max(1, min(limit, MAX_PREVIEW_ROWS)),
    )
    return json.dumps(result, ensure_ascii=False, indent=2, default=str)


def main() -> None:
    for name, path in DB_PATHS.items():
        if not Path(path).exists():
            print(f"[WARN] DB not found: {name} -> {path}", file=sys.stderr, flush=True)

    # Patch MCP SDK 1.27 stdio_server to skip blank stdin lines.
    # The SDK does `async for line in stdin` then `model_validate_json(line)`
    # on every line. Blank lines cause "EOF while parsing a value".
    # Fix: replace stdio_server with a version that filters blanks.
    import mcp.server.stdio as _mcp_stdio
    import mcp.server.fastmcp as _mcp_fast
    import anyio
    from contextlib import asynccontextmanager
    from io import TextIOWrapper
    from mcp.types import JSONRPCMessage
    from mcp.shared.message import SessionMessage

    @asynccontextmanager
    async def _patched_stdio(stdin=None, stdout=None):
        if not stdin:
            stdin = anyio.wrap_file(
                TextIOWrapper(sys.stdin.buffer, encoding="utf-8", errors="replace")
            )
        if not stdout:
            stdout = anyio.wrap_file(
                TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
            )

        read_w, read_r = anyio.create_memory_object_stream(0)
        write_s, write_r = anyio.create_memory_object_stream(0)

        async def _reader():
            try:
                async with read_w:
                    async for line in stdin:
                        if not line.strip():
                            continue
                        try:
                            msg = JSONRPCMessage.model_validate_json(line)
                        except Exception as exc:
                            await read_w.send(exc)
                            continue
                        await read_w.send(SessionMessage(msg))
            except anyio.ClosedResourceError:
                pass

        async def _writer():
            try:
                async with write_r:
                    async for session_msg in write_r:
                        j = session_msg.message.model_dump_json(
                            by_alias=True, exclude_none=True
                        )
                        await stdout.write(j + "\n")
                        await stdout.flush()
            except anyio.ClosedResourceError:
                pass

        async with anyio.create_task_group() as tg:
            tg.start_soon(_reader)
            tg.start_soon(_writer)
            yield read_r, write_s

    _mcp_stdio.stdio_server = _patched_stdio
    # Also patch the local reference in fastmcp.server module
    import mcp.server.fastmcp.server as _fmcp_srv
    _fmcp_srv.stdio_server = _patched_stdio

    try:
        mcp.run()
    except Exception as e:
        print(f"[FATAL] {e}", file=sys.stderr, flush=True)
        raise


if __name__ == "__main__":
    main()