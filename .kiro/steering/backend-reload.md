---
inclusion: auto
---

# 修改後重啟驗證規則

每次 coding 修改驗證完畢後，**必須重新啟動修改的部分**，確認能正常啟動。不能只驗證語法通過就結束。

## 後端 (Python / Flask)

修改 `ai_schedule/`、`mrpFlask_5.py`、`scheduler_api.py` 等 Python 後端代碼後，必須：

1. **重啟 gunicorn** — 執行 `kill -HUP $(pgrep -f "gunicorn.*mrpFlask_5" | head -1)`
2. **等待 worker 啟動** — `sleep 3`
3. **驗證啟動成功** — 用 `curl` 呼叫相關的 API endpoint，確認回應正確（`"ok": true`）
4. **報告結果** — 將驗證結果回報給使用者

若驗證失敗，立即修正並重試，不要等使用者回報。

### 快速指令模板

```bash
kill -HUP $(pgrep -f "gunicorn.*mrpFlask_5" | head -1) && sleep 3 && curl -s "http://127.0.0.1:3001/api/ai-schedule/demands?week_code=2026-W23" | python3 -c "import sys,json;d=json.load(sys.stdin);print('ok:', d.get('ok'), '| error:', d.get('error','none'))"
```

## 前端 (React / TypeScript)

修改 `frontend/` 中的 `.tsx`、`.ts`、`.css` 文件後，必須：

1. **確認 TypeScript 編譯通過** — 檢查 diagnostics 無 error
2. **確認 Vite dev server 無錯誤** — 若 dev server 正在運行，檢查 terminal 輸出是否有編譯錯誤
3. **若為 production 環境** — 執行 `npm run build`（在 `frontend/` 目錄），確認 build 成功

## 通用規則

- **修改完 = 驗證完 + 重啟成功**，缺一不可
- 若重啟或 build 失敗，必須當下修正，不能留到下一輪
- 每次 task 結束前的 checkpoint，都要包含重啟驗證步驟
