# -*- coding: utf-8 -*-
import sqlite3
import pandas as pd
from sqlalchemy import create_engine, text
from urllib.parse import quote_plus

# ========= 來源 SQLite =========
SQLITE_DB = "beads_sync.db"   # 改成你的實際路徑也可以

# ========= 目標 RDS PostgreSQL =========
RDS_USER = "harryguo"
RDS_PASS = "skyla168"
RDS_HOST = "database-1.cfutwrwyrxts.ap-northeast-1.rds.amazonaws.com"
RDS_PORT = "5432"
RDS_DB   = "beadsdb"

# ========= 目標 schema =========
TARGET_SCHEMA = "schedule"

# ========= 匯入模式 =========
# 第一次搬遷建議用 replace
# 若之後已存在正式表，不要再用 replace
IF_EXISTS = "replace"   # 可改 "append"

# ========= 建立 PostgreSQL engine =========
encoded_pass = quote_plus(RDS_PASS)
engine = create_engine(
    f"postgresql+psycopg2://{RDS_USER}:{encoded_pass}@{RDS_HOST}:{RDS_PORT}/{RDS_DB}"
)

def ensure_schema_exists():
    with engine.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{TARGET_SCHEMA}"'))
    print(f"✅ schema 已確認存在: {TARGET_SCHEMA}")

def get_sqlite_tables(sqlite_conn):
    cursor = sqlite_conn.cursor()
    cursor.execute("""
        SELECT name
        FROM sqlite_master
        WHERE type='table'
          AND name <> 'sqlite_sequence'
        ORDER BY name
    """)
    return [row[0] for row in cursor.fetchall()]

def get_sqlite_row_count(sqlite_conn, table_name):
    cursor = sqlite_conn.cursor()
    cursor.execute(f'SELECT COUNT(*) FROM "{table_name}"')
    return cursor.fetchone()[0]

def get_pg_row_count(table_name):
    with engine.begin() as conn:
        result = conn.execute(
            text(f'SELECT COUNT(*) FROM "{TARGET_SCHEMA}"."{table_name}"')
        )
        return result.scalar()

def migrate_one_table(sqlite_conn, table_name):
    print(f"\n--- 正在遷移資料表: {table_name} ---")

    src_count = get_sqlite_row_count(sqlite_conn, table_name)
    print(f"SQLite 筆數: {src_count}")

    if src_count == 0:
        print("⚠️ 空表，略過")
        return

    df = pd.read_sql_query(f'SELECT * FROM "{table_name}"', sqlite_conn)

    # ── 新增：去除重複欄位 ──────────────────────────
    cols = pd.Series(df.columns)
    for dup in cols[cols.duplicated()].unique():
        dup_idx = cols[cols == dup].index.tolist()
        for i, idx in enumerate(dup_idx[1:], 1):
            cols[idx] = f"{dup}.{i}"
    df.columns = cols
    # 防止全空欄位型別判斷怪掉，可先保留原樣
    df.to_sql(
        name=table_name,
        con=engine,
        schema=TARGET_SCHEMA,
        if_exists=IF_EXISTS,
        index=False,
        method="multi",
        chunksize=1000
    )

    pg_count = get_pg_row_count(table_name)
    print(f"PostgreSQL 筆數: {pg_count}")

    if src_count == pg_count:
        print(f"✅ 遷移成功: {TARGET_SCHEMA}.{table_name}")
    else:
        print(f"⚠️ 筆數不一致: SQLite={src_count}, PostgreSQL={pg_count}")

def show_target_tables():
    print("\n=== PostgreSQL schedule schema 內的資料表 ===")
    with engine.begin() as conn:
        result = conn.execute(text("""
            SELECT tablename
            FROM pg_tables
            WHERE schemaname = :schema
            ORDER BY tablename
        """), {"schema": TARGET_SCHEMA})

        rows = result.fetchall()
        if not rows:
            print("(沒有資料表)")
        else:
            for r in rows:
                print(f"- {r[0]}")

def migrate():
    print("=== SQLite -> PostgreSQL migration 開始 ===")
    print(f"來源 SQLite: {SQLITE_DB}")
    print(f"目標 RDS   : {RDS_DB}.{TARGET_SCHEMA}")

    ensure_schema_exists()

    src_conn = sqlite3.connect(SQLITE_DB)
    try:
        tables = get_sqlite_tables(src_conn)

        if not tables:
            print("❌ SQLite 沒有可遷移的資料表")
            return

        print("\nSQLite 內找到以下資料表：")
        for t in tables:
            print(f"- {t}")

        for table_name in tables:
            if table_name == 'production_Plan':   # ← 只跑這一張
                migrate_one_table(src_conn, table_name)

        show_target_tables()
        print("\n🎉 全部遷移完成")

    finally:
        src_conn.close()

if __name__ == "__main__":
    migrate()