from flask import Flask, send_from_directory, request, jsonify
from pathlib import Path
import subprocess, sys, os, json

# === 路徑設定 ===
BACKEND_DIR = Path(__file__).parent  # 這支 app.py 所在目錄（D:）
DIST = Path(r"C:\Users\harryhrguo\beads-ui\dist")  # 直接指向 C 槽的 Vite build 結果


print("DIST ->", DIST)
print("index exists?", (DIST / "index.html").exists())


# === Flask ===
app = Flask(__name__, static_folder=str(DIST), static_url_path="/")


# 固定你的需求計算程式路徑
SCRIPT= Path(r"D:\OneDrive - 天亮醫療器材股份有限公司\.vscode\Bead_auto_update_schedule\plan_to_bead_requirements_1.py")

# ---- API：Beads 需求統計 ----

# ---- 健康檢查 ----
@app.get("/api/health")
def health():
    return jsonify(ok=True, dist=str(DIST), index_exists=(DIST / "index.html").exists(), script_exists=SCRIPT.exists())

# ---- API：Beads 需求統計 ----
@app.post("/api/run/beads-demand")
def run_beads_demand():
    global CURRENT_PROC
    data = request.get_json(force=True) or {}

    # 1) 取參數
    year = str(data.get("year", "2025"))
    date_mmdd = data.get("dateMMDD", "")                 # 需為 "MM/DD"
    out_path = data.get("writeBackPath", "") or r"\\fls341\MBBU_FAB\MB_PD\生管自動化\滴定\beads 需求模組.xlsx"
    is_dry = bool(data.get("dryRun", False))
    dry = "1" if is_dry else "0"

    # 2) 準備環境：強制子程序用 UTF-8，避免 cp950 亂碼
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"

    # 3) 指令
    cmd = [
        sys.executable, str(SCRIPT),
        "--year", year,
        "--date", date_mmdd,
        "--out", out_path,
        "--dry", dry,
    ]

    try:
        # 用 Popen 便於取消
        CURRENT_PROC = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                        text=True, encoding="utf-8", env=env)
        stdout, stderr = CURRENT_PROC.communicate()
        code = CURRENT_PROC.returncode
        CURRENT_PROC = None

        if code != 0:
            return jsonify(ok=False, code=code, stdout=stdout, stderr=stderr), 500

        if is_dry:
            # 讓 UI Output 欄位清空：outPath 回空字串
            try:
                payload = json.loads(stdout)
                return jsonify(ok=bool(payload.get("ok", True)),
                               data=payload.get("data") or payload.get("rows") or [],
                               outPath="")
            except json.JSONDecodeError as e:
                return jsonify(ok=False, error=f"DryRun JSON parse failed: {e}",
                               stdout=stdout[:2000], stderr=stderr[:2000]), 500
        else:
            # 非 dry：把腳本回傳的 out_path 帶回 UI
            try:
                payload = json.loads(stdout)
                return jsonify(ok=True, msg=payload.get("msg","✅ 已寫入 Excel"),
                               outPath=payload.get("out_path",""))
            except Exception:
                # 老版本腳本只印純文字也兼容
                return jsonify(ok=True, msg="✅ 已寫入 Excel", outPath=out_path, stdout=stdout)

    except Exception as e:
        # 保底錯誤
        return jsonify(ok=False, error=str(e)), 500

@app.post("/api/cancel/beads-demand")
def cancel_beads_demand():
    global CURRENT_PROC
    if CURRENT_PROC and CURRENT_PROC.poll() is None:
        try:
            CURRENT_PROC.terminate()
            # 等 2 秒，殺不掉就強殺
            for _ in range(20):
                if CURRENT_PROC.poll() is not None:
                    break
                time.sleep(0.1)
            if CURRENT_PROC.poll() is None:
                CURRENT_PROC.kill()
            CURRENT_PROC = None
            return jsonify(ok=True, msg="已取消")
        except Exception as e:
            return jsonify(ok=False, error=str(e)), 500
    return jsonify(ok=True, msg="沒有執行中的任務")

# 前端靜態檔
@app.get("/")
def index():
    return send_from_directory(str(DIST), "index.html")

@app.route("/<path:path>")
def static_proxy(path):
    target = DIST / path
    if target.exists():
        return send_from_directory(str(DIST), path)
    return send_from_directory(str(DIST), "index.html")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8505)