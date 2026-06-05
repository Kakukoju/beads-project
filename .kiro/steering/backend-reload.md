---
inclusion: auto
---

# 後端修改自動重啟規則

每次修改 `ai_schedule/` 或 `mrpFlask_5.py` 中的 Python 後端代碼後，必須：

1. **重啟 gunicorn** — 執行 `kill -HUP 119495`（或找到 gunicorn master PID）
2. **等待 worker 啟動** — `sleep 3`
3. **驗證 endpoint** — 用 `curl` 呼叫相關的 API endpoint，確認回應正確（`"ok": true`）
4. **報告結果** — 將驗證結果回報給使用者

若驗證失敗，立即修正並重試，不要等使用者回報。

## 快速指令模板

```bash
kill -HUP $(pgrep -f "gunicorn.*mrpFlask_5" | head -1) && sleep 3 && curl -s "http://127.0.0.1:3001/api/ai-schedule/demands?week_code=2026-W23" | python3 -c "import sys,json;d=json.load(sys.stdin);print('ok:', d.get('ok'), '| error:', d.get('error','none'))"
```
