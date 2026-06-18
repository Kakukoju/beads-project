from flask import Flask, send_from_directory, request, jsonify, send_file, abort, url_for
from pathlib import Path
import subprocess, sys, os, json, mimetypes, urllib.parse, time

# ===== 路徑設定 =====
DIST = Path(r"C:\Users\harryhrguo\beads-ui\dist")  # 前端 Vite build 結果
SCRIPT = Path(r"D:\OneDrive - 天亮醫療器材股份有限公司\.vscode\Bead_auto_update_schedule\plan_to_bead_requirements_1.py")

# ===== Beads 排程預設路徑 =====
DEFAULT_TEMPLATE = r"\\fls341\MBBU_FAB\MB_PD\生管自動化\滴定\空白排程.xlsm"
DEFAULT_OUTDIR   = r"\\fls341\MBBU_FAB\MB_PD\生管自動化\滴定\beadsSchedule"

# 排程子程序（供取消用）
CURRENT_SCHED_PROC = None

print("DIST ->", DIST)
print("index exists?", (DIST / "index.html").exists())

app = Flask(__name__, static_folder=str(DIST), static_url_path="/")

# ===== 允許讀檔的白名單根目錄（避免任意讀取本機）=====
ALLOWED_ROOTS = [
    r"\\fls341\MBBU_FAB\MB_PD\生管自動化\滴定",
]

def _is_allowed_path(path: str) -> bool:
    if not path:
        return False
    p_norm = path.lower().replace("/", "\\")
    return any(p_norm.startswith(root.lower().replace("/", "\\")) for root in ALLOWED_ROOTS)

# ===== 健康檢查 =====
@app.get("/api/health")
def health():
    return jsonify(
        ok=True,
        dist=str(DIST),
        index_exists=(DIST / "index.html").exists(),
        script_exists=SCRIPT.exists(),
    )

# ===== 需求統計：呼叫 Python 腳本 =====
CURRENT_PROC = None

@app.post("/api/run/beads-demand")
def run_beads_demand():
    global CURRENT_PROC
    data = request.get_json(force=True) or {}

    year = str(data.get("year", "2025"))
    date_mmdd = data.get("dateMMDD", "")
    out_path = data.get("writeBackPath", "") or r"\\fls341\MBBU_FAB\MB_PD\生管自動化\滴定\beads 需求模組.xlsx"
    is_dry = bool(data.get("dryRun", False))
    dry = "1" if is_dry else "0"

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"

    cmd = [
        sys.executable, str(SCRIPT),
        "--year", year,
        "--date", date_mmdd,
        "--out", out_path,
        "--dry", dry,
    ]

    try:
        CURRENT_PROC = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", env=env
        )
        stdout, stderr = CURRENT_PROC.communicate()
        code = CURRENT_PROC.returncode
        CURRENT_PROC = None

        if code != 0:
            return jsonify(ok=False, code=code, stdout=stdout, stderr=stderr), 500

        # 腳本 stdout 優先解析 JSON
        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError:
            payload = {}

        if is_dry:
            return jsonify(
                ok=bool(payload.get("ok", True)),
                data=payload.get("data") or payload.get("rows") or [],
                outPath=""  # DryRun 不寫回
            )
        else:
            # 優先回傳腳本實際輸出路徑（可能是 -OUTPUT- 時戳檔）
            real_out = payload.get("out_path") or out_path
            return jsonify(ok=True, msg=payload.get("msg", "✅ 已寫入 Excel"), outPath=real_out)

    except Exception as e:
        return jsonify(ok=False, error=str(e)), 500

@app.post("/api/cancel/beads-demand")
def cancel_beads_demand():
    global CURRENT_PROC
    if CURRENT_PROC and CURRENT_PROC.poll() is None:
        try:
            CURRENT_PROC.terminate()
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

# ===== 檔案串流（HTTP，不快取）=====
@app.get("/api/open-file")
def api_open_file():
    raw = request.args.get("path", "")
    path = urllib.parse.unquote(raw)

    if not _is_allowed_path(path):
        return abort(403, "path not allowed")

    if not os.path.exists(path):
        return abort(404, "file not found")

    mime, _ = mimetypes.guess_type(path)
    try:
        resp = send_file(
            path,
            mimetype=mime or "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=False,                 # 不強制下載
            download_name=os.path.basename(path),
            conditional=True,
        )
        # 禁止快取，避免 304 拿到舊檔
        resp.headers["Cache-Control"] = "no-store"
        resp.headers["Pragma"] = "no-cache"
        resp.headers["Expires"] = "0"
        resp.headers["X-Content-Type-Options"] = "nosniff"
        return resp
    except PermissionError:
        return abort(423, "file locked (in use)")

# ===== 產出 Excel Deeplink，讓桌面版 Excel 直接開啟 =====
@app.get("/api/excel-deeplink")
def api_excel_deeplink():
    raw = request.args.get("path", "")
    path = urllib.parse.unquote(raw)

    if not _is_allowed_path(path):
        return abort(403, "path not allowed")
    if not os.path.exists(path):
        return abort(404, "file not found")

    # 拼 /api/open-file 的絕對 URL，給 Excel 自己去抓
    open_url = request.url_root.rstrip("/") + url_for("api_open_file") + "?path=" + urllib.parse.quote(path)
    deeplink = f"ms-excel:ofe|u|{open_url}"
    return jsonify(ok=True, deeplink=deeplink)

# ===== 前端靜態檔 =====
@app.get("/")
def index():
    return send_from_directory(str(DIST), "index.html")

@app.route("/<path:path>")
def static_proxy(path):
    target = DIST / path
    if target.exists():
        return send_from_directory(str(DIST), path)
    return send_from_directory(str(DIST), "index.html")

@app.post("/api/pick-file")
def pick_file():
    import traceback
    t = request.args.get("type", "need")   # need | limit | template | outdir
    base = ALLOWED_ROOTS[0] if ALLOWED_ROOTS else r"C:\\"

    # 1) 先試 tkinter（強制置頂）
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)  # 關鍵：確保視窗浮到最上層
        root.update()

        if t == "outdir":
            path = filedialog.askdirectory(initialdir=base, title="選擇輸出資料夾") or ""
        else:
            path = filedialog.askopenfilename(
                initialdir=base,
                title="選擇檔案",
                filetypes=[("Excel", "*.xlsx;*.xlsm"), ("All files", "*.*")]
            ) or ""
        root.destroy()
        if path:
            return jsonify(ok=True, path=path)
        return jsonify(ok=False, message="使用者取消")
    except Exception as e:
        print("[pick-file] tkinter failed:", e)
        print(traceback.format_exc())

    # 2) 再試 PowerShell WinForms（需要互動桌面）
    try:
        if os.name == "nt":
            if t == "outdir":
                ps_cmd = rf"""
[void][System.Reflection.Assembly]::LoadWithPartialName('System.Windows.Forms')
$dlg = New-Object System.Windows.Forms.FolderBrowserDialog
$dlg.SelectedPath = '{base}'
if ($dlg.ShowDialog() -eq 'OK') {{ Write-Output $dlg.SelectedPath }}
"""
            else:
                ps_cmd = rf"""
[void][System.Reflection.Assembly]::LoadWithPartialName('System.Windows.Forms')
$dlg = New-Object System.Windows.Forms.OpenFileDialog
$dlg.InitialDirectory = '{base}'
$dlg.Filter = 'Excel (*.xlsx;*.xlsm)|*.xlsx;*.xlsm|All files (*.*)|*.*'
if ($dlg.ShowDialog() -eq 'OK') {{ Write-Output $dlg.FileName }}
"""
            res = subprocess.run(
                ["powershell", "-NoProfile", "-Sta", "-Command", ps_cmd],
                capture_output=True, text=True, encoding="utf-8"
            )
            path = res.stdout.strip()
            if path:
                return jsonify(ok=True, path=path)
    except Exception as e2:
        print("[pick-file] powershell failed:", e2)
        print(traceback.format_exc())

    # 3) 最後才回預設（避免前端卡住）
    defaults = {
        "need":     os.path.join(base, "需求檔.xlsx"),
        "limit":    os.path.join(base, "滴定限制.xlsx"),
        "template": DEFAULT_TEMPLATE,
        "outdir":   DEFAULT_OUTDIR,
    }
    return jsonify(ok=True, path=defaults.get(t, DEFAULT_TEMPLATE), message="fallback-default")

    
@app.post("/api/run/beads-schedule")
def run_beads_schedule():
    data = request.get_json(force=True) or {}

    date_mmdd   = data.get("dateMMDD", "")
    need_path   = data.get("needPath", "")
    limit_path  = data.get("limitPath", "")
    template    = data.get("templatePath") or DEFAULT_TEMPLATE
    out_dir     = data.get("outDir") or DEFAULT_OUTDIR
    is_dry      = bool(data.get("dryRun", False))
    script_name = data.get("scriptName") or "plan_to_beads_schedule_1.py"

    # 若只給檔名，就放在 SCRIPT 同資料夾；也可改成你的實際位置
    script_path = Path(SCRIPT).parent / script_name if os.path.basename(script_name) == script_name else Path(script_name)

    cmd = [
        sys.executable, str(script_path),
        "--date", date_mmdd,
        "--need", need_path,
        "--limit", limit_path,
        "--template", template,
        "--outdir", out_dir,
    ]
    if is_dry:
        cmd.append("--dry-run")

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", env=env)
        if proc.returncode != 0:
            return jsonify(ok=False, message=proc.stderr or proc.stdout), 500

        # 優先解析腳本 stdout 的 JSON
        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError:
            payload = {}

        if is_dry:
            preview = payload.get("preview") or payload.get("data") or payload.get("rows") or []
            return jsonify(ok=True, preview=preview)

        # 正式輸出
        out_paths = payload.get("outPaths") or payload.get("out_paths")
        out_path  = payload.get("outPath")  or payload.get("out_path")
        return jsonify(ok=True, outPaths=out_paths, outPath=out_path)
    except Exception as e:
        return jsonify(ok=False, message=str(e)), 500
    
@app.post("/api/cancel/beads-schedule")
def cancel_beads_schedule():
    global CURRENT_SCHED_PROC
    if CURRENT_SCHED_PROC and CURRENT_SCHED_PROC.poll() is None:
        try:
            CURRENT_SCHED_PROC.terminate()
            for _ in range(20):  # 最多等 2 秒
                if CURRENT_SCHED_PROC.poll() is not None:
                    break
                time.sleep(0.1)
            if CURRENT_SCHED_PROC.poll() is None:
                CURRENT_SCHED_PROC.kill()
            CURRENT_SCHED_PROC = None
            return jsonify(ok=True, msg="已取消")
        except Exception as e:
            return jsonify(ok=False, error=str(e)), 500
    return jsonify(ok=True, msg="沒有執行中的排程作業")



if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8505)
