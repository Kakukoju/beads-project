# RDS PostgreSQL 連線資訊

| 欄位 | 值 |
|------|-----|
| Host | database-1.cfutwrwyrxts.ap-northeast-1.rds.amazonaws.com |
| Port | 5432 |
| Database | beadsdb |
| User | harryguo |
| Password | skyla168 |

## Schema 規則

- SQLite DB `P01_formualte_schedule.db` 同步到 RDS 時，schema 名稱為 `P01_formualte_schedule`
- 所有 table 保持 SQLite 原始 table name
- 使用 inotify 監聽檔案變更，自動 push 全部 table 到 RDS

## 同步服務

| 用途 | 路徑 |
|------|------|
| 同步腳本 | `/opt/beadsops/scripts/sync_sqlite_to_rds.py` |
| systemd service | `sqlite-rds-sync.service` |
