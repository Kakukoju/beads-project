"""
製程分析 API Blueprint
跨 3 個 SQLite DB 合併同一 bead 的製程紀錄並做差異分析
分析結果存入 RDS (SQLite fallback)
"""
import sqlite3, json, math, os, re
import numpy as np
from datetime import datetime
from flask import Blueprint, request, jsonify

process_analysis_bp = Blueprint("process_analysis", __name__)

DB_PATHS = {
    "ipqc": "/opt/beadsops/data/P01_Beads_IPQC.db",
    "wo": "/opt/beadsops/data/work_orders.db",
    "schedule": "/opt/beadsops/data/P01_formualte_schedule.db",
}
ANALYSIS_DB = "/opt/beadsops/data/process_analysis_history.db"

ANOMALY_FLAGS = ["外觀不良", "CVNG", "訊號異常", "凍乾異常", "配置異常", "分藥異常"]

# ── helpers ──

def _conn(key):
    return sqlite3.connect(DB_PATHS[key])

def _dict_rows(cursor):
    cols = [d[0] for d in cursor.description]
    return [dict(zip(cols, row)) for row in cursor.fetchall()]

def _norm_lyoph(v):
    if not v: return v
    s = str(v).strip()
    if "小台" in s: return "小台"
    m = re.search(r"(\d+)", s)
    if m:
        n = int(m.group(1))
        if 3 <= n <= 12:
            return f"Freezer-{n:02d}"
    return s

def _norm_row(row):
    for k in list(row.keys()):
        if any(x in k for x in ["凍乾機", "lyophilizer", "dD凍乾機", "U凍乾機"]):
            row[k] = _norm_lyoph(row[k])
    return row

def _normalize_date(raw):
    """Normalize date strings to ISO YYYY-MM-DD from multiple formats."""
    if not raw or not isinstance(raw, str): return None
    s = raw.strip()
    if not s: return None
    if re.match(r"^\d{4}-\d{2}-\d{2}", s): return s[:10]
    m = re.match(r"^(\d{4})/(\d{1,2})/(\d{1,2})$", s)
    if m: return f"{m[1]}-{m[2].zfill(2)}-{m[3].zfill(2)}"
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", s)
    if m and 1 <= int(m[1]) <= 12: return f"{m[3]}-{m[1].zfill(2)}-{m[2].zfill(2)}"
    m = re.search(r"(\d{4})年(\d{1,2})月(\d{1,2})日", s)
    if m and 1 <= int(m[3]) <= 31: return f"{m[1]}-{m[2].zfill(2)}-{m[3].zfill(2)}"
    return None

_DATE_FIELDS = {
    "work_orders": ["日期"],
    "ipqc": ["U生產日", "dD生產日", "檢驗日期"],
    "dropletRecord": ["record_date"],
    "formulation": ["試劑配製日期"],
}

def _norm_dates(row, table_type):
    for f in _DATE_FIELDS.get(table_type, []):
        if row.get(f):
            d = _normalize_date(row[f])
            if d: row[f] = d
    return row

def _ipqc_marker(marker):
    """Strip -U/-D/-AD/-AU suffix for IPQC lookup"""
    return re.sub(r"[-_]?(U|D|AD|AU)$", "", marker, flags=re.IGNORECASE)

def _ipqc_tables(conn):
    cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%_IPQC'")
    return [r[0] for r in cur.fetchall()]

def _marker_col(table_name):
    """2024_IPQC uses 'Maker', 2025/2026 use 'Marker'"""
    return "Maker" if table_name.startswith("2024") else "Marker"

def _formulation_tables(conn):
    skip = {"DropletSchedule", "dropletRecord", "FormulationData", "column_dictionary",
            "sync_status", "sqlite_sequence", "sqlite_stat1", "sqlite_stat4",
            "滴定條件", "滴定針頭號數表", "freezer_rules", "pump No.", "Liquid form QC"}
    cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    return [r[0] for r in cur.fetchall() if r[0] not in skip]

def _norm_marker(m):
    return re.sub(r"[-_ ]", "", (m or "")).lower()

def _safe_float(v):
    try: return float(v)
    except: return None

def _stats(vals):
    vals = [v for v in vals if v is not None and not math.isnan(v)]
    if len(vals) < 2: return None
    mn, mx = min(vals), max(vals)
    mean = sum(vals) / len(vals)
    std = math.sqrt(sum((v - mean) ** 2 for v in vals) / len(vals))
    cv = (std / abs(mean) * 100) if mean != 0 else None
    return {"count": len(vals), "min": round(mn, 6), "max": round(mx, 6),
            "range": round(mx - mn, 6), "mean": round(mean, 6), "std": round(std, 6),
            "cv_percent": round(cv, 2) if cv else None}

def _pick_wo(r):
    """Return first non-empty, non-'0' work order number from IPQC row."""
    for k in ["U工單號碼", "D工單號碼_2", "d工單號碼"]:
        v = (r.get(k) or "").strip()
        if v and v != "0": return v
    return ""

def _pick_lot(r):
    """Return first non-empty, non-'0' lot number from IPQC row."""
    for k in ["U批號", "D批號_2", "d批號"]:
        v = (r.get(k) or "").strip()
        if v and v != "0": return v
    return ""

def _pearson(xs, ys):
    """Pearson correlation coefficient; requires >=3 valid pairs."""
    pairs = [(x, y) for x, y in zip(xs, ys)
             if x is not None and y is not None and not math.isnan(x) and not math.isnan(y)]
    n = len(pairs)
    if n < 3: return None
    mx = sum(p[0] for p in pairs) / n
    my = sum(p[1] for p in pairs) / n
    sxy = sxx = syy = 0.0
    for x, y in pairs:
        sxy += (x - mx) * (y - my)
        sxx += (x - mx) ** 2
        syy += (y - my) ** 2
    denom = math.sqrt(sxx * syy)
    if denom == 0: return None
    return {"r": round(sxy / denom, 4), "n": n}

def _parse_ts(s):
    if not s or not isinstance(s, str): return None
    try:
        return datetime.fromisoformat(s.replace(" ", "T"))
    except Exception:
        return None

def _diff_hours(a, b):
    da, db = _parse_ts(a), _parse_ts(b)
    if da and db:
        return (db - da).total_seconds() / 3600
    return None

def _stat_summary(arr):
    arr = [v for v in arr if v is not None]
    if not arr: return None
    mn, mx = min(arr), max(arr)
    avg = sum(arr) / len(arr)
    return {"count": len(arr), "min": round(mn, 2), "max": round(mx, 2), "mean": round(avg, 2)}

# ── init analysis history DB ──

def _init_history_db():
    db = sqlite3.connect(ANALYSIS_DB)
    db.execute("""CREATE TABLE IF NOT EXISTS analysis_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        created_at TEXT DEFAULT (datetime('now','localtime')),
        marker TEXT, work_order TEXT, date_from TEXT, date_to TEXT,
        user_question TEXT, analysis_result TEXT, ai_summary TEXT,
        user_name TEXT, tags TEXT
    )""")
    db.commit(); db.close()

_init_history_db()


def _generate_ai_summary(marker, summary, analysis, user_question=""):
    """Generate a structured AI analysis summary report"""
    lines = []
    lines.append(f"# 📊 {marker} 製程差異分析報告")
    lines.append(f"")
    lines.append(f"分析時間：{datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"")

    if user_question:
        lines.append(f"## 📝 使用者問題")
        lines.append(f"{user_question}")
        lines.append(f"")

    # Data coverage
    lines.append(f"## 📦 資料涵蓋範圍")
    lines.append(f"- 工單數：{summary['total_work_orders']}")
    lines.append(f"- IPQC 記錄：{summary['total_ipqc_records']}")
    lines.append(f"- 滴定紀錄：{summary['total_droplet_records']}")
    lines.append(f"- 配藥紀錄：{summary['total_formulation_records']}")
    lines.append(f"- 配藥表：{', '.join(summary.get('formulation_tables_matched', []))}")
    lines.append(f"- 異常批次數：{summary.get('anomaly_batches', 0)}")
    if summary.get("main_ingredient"):
        lines.append(f"- 主要配藥成分：{summary['main_ingredient']}")
    lines.append(f"")

    # Key findings - variation
    var_rank = analysis.get("variation_ranking", [])
    high_cv = [v for v in var_rank if (v.get("cv_percent") or 0) > 25]
    if var_rank:
        lines.append(f"## ⚠️ 關鍵發現：參數變異")
        if high_cv:
            lines.append(f"")
            lines.append(f"❗ **高變異參數** (CV > 25%)：")
            for v in high_cv:
                level = "🔴" if v["cv_percent"] > 35 else "🟡"
                lines.append(f"  {level} **{v['parameter']}**: CV = {v['cv_percent']}%, Range = {v['range']}")
        else:
            lines.append(f"✅ 所有參數 CV 均在 25% 以下，變異度可接受")
        lines.append(f"")

    # Anomaly batches
    anomalies = analysis.get("anomaly_ranking", [])
    critical = [a for a in anomalies if a.get("anomaly_score", 0) >= 10]
    warning = [a for a in anomalies if 5 <= a.get("anomaly_score", 0) < 10]
    if critical or warning:
        lines.append(f"## 🚨 異常批次")
        if critical:
            lines.append(f"")
            lines.append(f"🔴 **重大異常** ({len(critical)} 批)：")
            for a in critical[:5]:
                flags_str = " | ".join(f"{k}={v}" for k, v in a.get("anomaly_flags", {}).items())
                lines.append(f"  - 工單 {a.get('工單號碼', '?')} | 批號 {a.get('批號', '?')} | 判定: {a.get('最終判定', '?')} | 分數: {a['anomaly_score']}" + (f" | {flags_str}" if flags_str else ""))
        if warning:
            lines.append(f"")
            lines.append(f"🟡 **警告** ({len(warning)} 批)：")
            for a in warning[:5]:
                lines.append(f"  - 工單 {a.get('工單號碼', '?')} | 批號 {a.get('批號', '?')} | 分數: {a['anomaly_score']}")
        lines.append(f"")
    else:
        lines.append(f"## ✅ 無重大異常批次")
        lines.append(f"")

    # Process time analysis
    pt = analysis.get("process_time", {})
    tit = pt.get("titration_hours")
    lyo = pt.get("lyophilization_hours")
    if tit or lyo:
        lines.append(f"## ⏱️ 製程時間分析")
        if tit:
            lines.append(f"- 滴定時間：平均 {tit['mean']}h，範圍 {tit['min']}~{tit['max']}h（n={tit['count']}）")
        if lyo:
            lines.append(f"- 凍乾時間：平均 {lyo['mean']}h，範圍 {lyo['min']}~{lyo['max']}h（n={lyo['count']}）")
        corrs = pt.get("correlations", {})
        sig_corrs = []
        for time_label, metrics in corrs.items():
            for metric, val in metrics.items():
                if val and abs(val.get("r", 0)) >= 0.5:
                    sig_corrs.append(f"{time_label} vs {metric}: r={val['r']} (n={val['n']})")
        if sig_corrs:
            lines.append(f"- **顯著相關** (|r|≥0.5)：")
            for s in sig_corrs:
                lines.append(f"  - {s}")
        lines.append(f"")

    # Formulation analysis
    fa = analysis.get("formulation_analysis", {})
    var_by_ingred = fa.get("variation_by_ingredient", [])
    high_ingred_cv = [x for x in var_by_ingred if (x.get("cv_percent") or 0) > 10]
    if fa.get("ingredient_summary"):
        lines.append(f"## 🧪 配藥成分分析")
        if fa.get("main_ingredient"):
            lines.append(f"- 主成分（與 OD 變化最相關）：{fa['main_ingredient']}")
        if high_ingred_cv:
            lines.append(f"- ⚠️ 高變異成分 (CV>10%)：{', '.join(x['化學品名'] for x in high_ingred_cv[:5])}")
        pca = fa.get("pca")
        if pca:
            lines.append(f"- PCA 分析（{pca['n_work_orders']} 工單 × {pca['n_ingredients']} 成分，排除 H2O）：")
            for pc in pca.get("principal_components", [])[:2]:
                top = pc["top_loadings"][:3]
                top_str = ", ".join(f"{t['化學品名']}({t['loading']:+.3f})" for t in top)
                lines.append(f"  - PC{pc['pc']}（解釋 {pc['explained_var_pct']}%）：{top_str}")
            od_corrs = pca.get("ingredient_od_correlation", [])[:3]
            if od_corrs:
                lines.append(f"- 成分 vs OD 變化相關性 Top 3：")
                for c in od_corrs:
                    lines.append(f"  - {c['化學品名']} vs {c['vs']}: r={c['r']} (n={c['n']})")
        lines.append(f"")

    # Recommendations
    lines.append(f"## 💡 建議")
    lines.append(f"")
    rec_idx = 1

    if high_cv:
        params = ", ".join([v["parameter"] for v in high_cv])
        lines.append(f"{rec_idx}. **檢查高變異參數**：{params} 的 CV 偏高，建議檢查配藥流程一致性、化學品批號是否變更")
        rec_idx += 1

    if critical:
        wo_list = ", ".join([a.get("工單號碼", "?") for a in critical[:3]])
        lines.append(f"{rec_idx}. **追查異常批次**：{wo_list} 判定非 Accept 或有異常旗標，建議比對配藥紀錄、滴定條件、凍乾參數")
        rec_idx += 1

    if high_ingred_cv:
        chems = ", ".join(x["化學品名"] for x in high_ingred_cv[:3])
        lines.append(f"{rec_idx}. **配藥一致性**：{chems} 重量變異偏高，建議確認秤量精度與化學品批號一致性")
        rec_idx += 1

    if rec_idx == 1:
        lines.append(f"✅ 目前製程參數穩定，無特別建議")

    return "\n".join(lines)

# ── API routes ──

@process_analysis_bp.route("/api/process-analysis/marker-list", methods=["GET"])
def pa_marker_list():
    """回傳所有 bead_name (from work_orders)"""
    conn = _conn("wo")
    cur = conn.execute("SELECT DISTINCT bead_name FROM work_orders WHERE bead_name IS NOT NULL ORDER BY bead_name")
    names = [r[0] for r in cur.fetchall()]
    conn.close()
    return jsonify({"ok": True, "markers": names})


@process_analysis_bp.route("/api/process-analysis/analyze", methods=["POST"])
def pa_analyze():
    """核心：跨 DB 合併 + 差異分析"""
    body = request.json or {}
    marker = body.get("marker", "")
    work_order = body.get("work_order", "")
    date_from = body.get("date_from", "")
    date_to = body.get("date_to", "")
    user_question = body.get("user_question", "")

    if not marker:
        return jsonify({"ok": False, "error": "請選擇 Marker"}), 400

    _wo = []; _ipqc = []; _droplet = []; _formulations = []

    # 1) work_orders
    wo_conn = _conn("wo")
    sql = "SELECT * FROM work_orders WHERE bead_name LIKE ?"
    params = [f"%{marker}%"]
    if work_order:
        sql += " AND 工單號 LIKE ?"; params.append(f"%{work_order}%")
    if date_from:
        sql += " AND 日期 >= ?"; params.append(date_from)
    if date_to:
        sql += " AND 日期 <= ?"; params.append(date_to)
    sql += " ORDER BY 日期 DESC"
    wo_conn.row_factory = sqlite3.Row
    _wo = [_norm_dates(_norm_row(dict(r)), "work_orders") for r in wo_conn.execute(sql, params).fetchall()]
    wo_nums = [r["工單號"] for r in _wo if r.get("工單號")]
    wo_conn.close()

    # 2) IPQC — strip -U/-D suffix; detect Maker vs Marker per table
    ipqc_conn = _conn("ipqc")
    ipqc_conn.row_factory = sqlite3.Row
    ipqc_mk = _ipqc_marker(marker)
    for t in _ipqc_tables(ipqc_conn):
        mc = _marker_col(t)
        try:
            if wo_nums:
                ph = ",".join(["?"] * len(wo_nums))
                sql = (f'SELECT *, \'{t}\' as _source FROM "{t}" WHERE '
                       f'("{mc}" LIKE ? OR "U工單號碼" IN ({ph}) OR "d工單號碼" IN ({ph}) OR "D工單號碼_2" IN ({ph}))')
                p = [f"%{ipqc_mk}%"] + wo_nums + wo_nums + wo_nums
            else:
                sql = f'SELECT *, \'{t}\' as _source FROM "{t}" WHERE "{mc}" LIKE ?'
                p = [f"%{ipqc_mk}%"]
            if date_from:
                sql += ' AND ("U生產日" >= ? OR "dD生產日" >= ?)'; p += [date_from, date_from]
            if date_to:
                sql += ' AND ("U生產日" <= ? OR "dD生產日" <= ?)'; p += [date_to, date_to]

            for r in ipqc_conn.execute(sql, p).fetchall():
                row = _norm_dates(_norm_row(dict(r)), "ipqc")
                # Unify Maker -> Marker
                if "Maker" in row and "Marker" not in row:
                    row["Marker"] = row.pop("Maker")
                _ipqc.append(row)
        except Exception:
            pass
    ipqc_conn.close()

    # 3) Schedule: dropletRecord
    sch_conn = _conn("schedule")
    sch_conn.row_factory = sqlite3.Row
    try:
        if wo_nums:
            ph = ",".join(["?"] * len(wo_nums))
            sql = f"SELECT * FROM dropletRecord WHERE (marker LIKE ? OR work_order IN ({ph}))"
            p = [f"%{marker}%"] + wo_nums
        else:
            sql = f"SELECT * FROM dropletRecord WHERE marker LIKE ?"
            p = [f"%{marker}%"]
        _droplet = [_norm_dates(_norm_row(dict(r)), "dropletRecord") for r in sch_conn.execute(sql, p).fetchall()]
    except Exception:
        pass

    # Formulation tables — fetch ALL rows (no LIMIT) because each TMRA work order
    # spans multiple rows (one per chemical ingredient); a row-level limit truncates records.
    norm = _norm_marker(marker)
    f_tables = [t for t in _formulation_tables(sch_conn) if _norm_marker(t).startswith(norm)]
    for t in f_tables:
        try:
            rows = sch_conn.execute(f'SELECT *, \'{t}\' as _table FROM "{t}"').fetchall()
            _formulations.extend([_norm_dates(dict(r), "formulation") for r in rows])
        except Exception:
            pass
    sch_conn.close()

    # 4) 差異分析
    analysis = {"numeric": {}, "anomaly_ranking": [], "variation_ranking": []}

    # --- 數值型分析 (IPQC) — L fields always, N1/N3 only if present and non-zero ---
    base_fields = ["L1ODCV", "L2ODCV", "L1ConcCV", "L2ConcCV",
                   "L1MeanOD", "L2MeanOD", "L1MeanConc", "L2MeanConc"]
    n13_fields = ["N1OD", "N3OD", "N1ODCV", "N3ODCV", "N1ConcCV", "N3ConcCV"]
    active_n13 = [f for f in n13_fields
                  if sum(1 for r in _ipqc
                         if (lambda v: v is not None and not math.isnan(v) and v != 0)(_safe_float(r.get(f)))) > 1]
    numeric_fields = base_fields + active_n13

    for f in numeric_fields:
        is_n = f.startswith("N")
        vals = [_safe_float(r.get(f)) for r in _ipqc]
        vals = [v for v in vals if v is not None and not math.isnan(v) and (not is_n or v != 0)]
        s = _stats(vals)
        if s:
            analysis["numeric"][f] = s

    # --- 製程時間分析：滴定/凍乾時間 vs OD/CV 相關性 (Pearson) ---
    ipqc_by_wo = {}
    for r in _ipqc:
        wo_key = _pick_wo(r)
        if wo_key and wo_key not in ipqc_by_wo:
            ipqc_by_wo[wo_key] = r

    time_records = []
    for wo in _wo:
        wo_num = wo.get("工單號")
        qty = int(wo.get("製令數量") or 0) or None
        tit_hrs = _diff_hours(wo.get("時間_滴定開始"), wo.get("時間_滴定結束"))
        lyo_hrs = _diff_hours(wo.get("時間_凍乾開始"), wo.get("時間_凍乾結束"))
        if tit_hrs is None and lyo_hrs is None:
            continue
        tit_per_k = round(tit_hrs / (qty / 1000), 4) if (tit_hrs and qty) else None
        ipqc_r = ipqc_by_wo.get(wo_num, {})
        l1odcv = _safe_float(ipqc_r.get("L1ODCV"))
        l2odcv = _safe_float(ipqc_r.get("L2ODCV"))
        l1conccv = _safe_float(ipqc_r.get("L1ConcCV"))
        l2conccv = _safe_float(ipqc_r.get("L2ConcCV"))
        l1od = _safe_float(wo.get("L1_反應_OD"))
        l2od = _safe_float(wo.get("L2_反應_OD"))
        time_records.append({
            "工單號": wo_num, "製令數量": qty,
            "滴定時間hrs": round(tit_hrs, 2) if tit_hrs is not None else None,
            "滴定時間_每千顆": tit_per_k,
            "凍乾時間hrs": round(lyo_hrs, 2) if lyo_hrs is not None else None,
            "L1_OD": l1od, "L2_OD": l2od,
            "L1ODCV": l1odcv, "L2ODCV": l2odcv,
            "L1ConcCV": l1conccv, "L2ConcCV": l2conccv,
        })

    tit_hrs_arr = [r["滴定時間hrs"] for r in time_records]
    tit_per_k_arr = [r["滴定時間_每千顆"] for r in time_records]
    lyo_hrs_arr = [r["凍乾時間hrs"] for r in time_records]
    correlations = {}
    for label, x_arr in [("滴定時間", tit_hrs_arr), ("滴定時間/千顆", tit_per_k_arr), ("凍乾時間", lyo_hrs_arr)]:
        corr = {}
        for y_key in ["L1ODCV", "L2ODCV", "L1ConcCV", "L2ConcCV", "L1_OD", "L2_OD"]:
            y_arr = [r[y_key] for r in time_records]
            p = _pearson(x_arr, y_arr)
            if p:
                corr[y_key] = p
        if corr:
            correlations[label] = corr

    analysis["process_time"] = {
        "titration_hours": _stat_summary(tit_hrs_arr),
        "titration_hours_per_1k": _stat_summary(tit_per_k_arr),
        "lyophilization_hours": _stat_summary(lyo_hrs_arr),
        "correlations": correlations,
        "records": time_records,
    }

    # --- 異常批次排名：case-insensitive Accept, 6 anomaly flags, pickWO/pickLot ---
    scored = []
    for r in _ipqc:
        score = 0
        details = []
        judge = (r.get("最終判定") or "").strip()
        if judge and judge.upper() != "ACCEPT":
            score += 10; details.append(f"最終判定={judge}")
        anomaly_flags = {}
        for f in ANOMALY_FLAGS:
            v = str(r.get(f) or "").strip()
            if v:
                anomaly_flags[f] = v; score += 5; details.append(f"{f}={v}")
        for f in ["L1ODCV", "L2ODCV", "L1ConcCV", "L2ConcCV"]:
            v = _safe_float(r.get(f))
            ns = analysis["numeric"].get(f)
            if v is not None and ns and ns["std"] > 0:
                z = abs(v - ns["mean"]) / ns["std"]
                if z > 2:
                    score += z; details.append(f"{f} z={round(z, 2)}")
        scored.append({
            "工單號碼": _pick_wo(r),
            "批號": _pick_lot(r),
            "最終判定": judge,
            "anomaly_flags": anomaly_flags,
            "details": details,
            "L1ODCV": r.get("L1ODCV"), "L2ODCV": r.get("L2ODCV"),
            "L1ConcCV": r.get("L1ConcCV"), "L2ConcCV": r.get("L2ConcCV"),
            "anomaly_score": round(score, 2),
        })
    scored.sort(key=lambda x: x["anomaly_score"], reverse=True)
    analysis["anomaly_ranking"] = scored[:20]

    # --- variation ranking ---
    analysis["variation_ranking"] = sorted(
        [{"parameter": k, "cv_percent": v["cv_percent"], "range": v["range"]}
         for k, v in analysis["numeric"].items() if v.get("cv_percent")],
        key=lambda x: x["cv_percent"], reverse=True
    )

    # --- 配藥主成分分析 (PCA: 成分重量 vs OD 變化) ---
    SKIP_CHEMS = {"H2O", "h2o", "H20", "h20", "水", ""}
    by_wo = {}
    for r in _formulations:
        wo_key = (r.get("工單號碼") or "").strip()
        if wo_key:
            by_wo.setdefault(wo_key, []).append(r)
    ingred_weights = {}
    ingred_pcts = {}
    batch_comp = {}
    # Per-WO: collect ingredient weights + OD delta for PCA
    wo_vectors = {}  # wo_key -> {chem: weight, "_dL1OD": float, "_dL2OD": float}
    for wo_key, rows in by_wo.items():
        total_w = _safe_float(rows[0].get("總重量")) or 0
        l1od = _safe_float(rows[0].get("L1OD"))
        l2od = _safe_float(rows[0].get("L2OD"))
        l1od0 = _safe_float(rows[0].get("起始L1OD"))
        l2od0 = _safe_float(rows[0].get("起始L2OD"))
        dl1 = (l1od - l1od0) if (l1od is not None and l1od0 is not None) else None
        dl2 = (l2od - l2od0) if (l2od is not None and l2od0 is not None) else None
        vec = {"_dL1OD": dl1, "_dL2OD": dl2}
        batch_comp[wo_key] = []
        for r in rows:
            chem = (r.get("化學品名") or "").strip()
            w = _safe_float(r.get("重量紀錄"))
            if not chem or chem in SKIP_CHEMS or w is None:
                continue
            ingred_weights.setdefault(chem, []).append(w)
            pct = (w / total_w * 100) if total_w > 0 else None
            if pct is not None:
                ingred_pcts.setdefault(chem, []).append(pct)
            vec[chem] = w
            batch_comp[wo_key].append({
                "化學品名": chem, "重量": w,
                "佔比%": round(pct, 2) if pct is not None else None,
            })
        wo_vectors[wo_key] = vec

    ingred_summary = {}
    for chem, ws in ingred_weights.items():
        n = len(ws)
        m = sum(ws) / n
        s = math.sqrt(sum((w - m) ** 2 for w in ws) / (n - 1)) if n > 1 else 0
        pcts = ingred_pcts.get(chem, [])
        pm = sum(pcts) / len(pcts) if pcts else None
        ingred_summary[chem] = {
            "count": n, "mean_weight": round(m, 4), "std_weight": round(s, 4),
            "cv_percent": round(s / m * 100, 2) if (m > 0 and n > 1) else None,
            "weight_pct_mean": round(pm, 2) if pm is not None else None,
        }
    var_by_ingred = sorted(
        [{"化學品名": k, "cv_percent": v["cv_percent"]}
         for k, v in ingred_summary.items() if v.get("cv_percent") is not None],
        key=lambda x: x["cv_percent"], reverse=True,
    )

    # --- PCA: ingredient weights → OD delta correlation ---
    pca_result = None
    main_ingred = None
    all_chems = sorted(ingred_weights.keys())
    # Build matrix: rows=work orders, cols=ingredient weights
    valid_wos = [wo for wo, v in wo_vectors.items()
                 if v.get("_dL1OD") is not None or v.get("_dL2OD") is not None]
    if len(all_chems) >= 2 and len(valid_wos) >= 4:
        X = []  # (n_wo, n_chems)
        y_l1 = []
        y_l2 = []
        used_wos = []
        for wo in valid_wos:
            v = wo_vectors[wo]
            row = [v.get(c, 0.0) or 0.0 for c in all_chems]
            if all(x == 0 for x in row):
                continue
            X.append(row)
            y_l1.append(v.get("_dL1OD"))
            y_l2.append(v.get("_dL2OD"))
            used_wos.append(wo)

        if len(X) >= 4:
            X_arr = np.array(X, dtype=float)
            # Standardize
            mu = X_arr.mean(axis=0)
            sigma = X_arr.std(axis=0)
            sigma[sigma == 0] = 1.0
            X_std = (X_arr - mu) / sigma
            # PCA via SVD
            try:
                U, S, Vt = np.linalg.svd(X_std, full_matrices=False)
                n_comp = min(3, len(S))
                explained_var = (S ** 2) / (S ** 2).sum()
                # PC loadings: each row of Vt is a principal component
                pc_loadings = []
                for pc_i in range(n_comp):
                    loadings = [(all_chems[j], round(float(Vt[pc_i, j]), 4))
                                for j in range(len(all_chems))]
                    loadings.sort(key=lambda x: abs(x[1]), reverse=True)
                    pc_loadings.append({
                        "pc": pc_i + 1,
                        "explained_var_pct": round(float(explained_var[pc_i]) * 100, 2),
                        "top_loadings": [{"化學品名": c, "loading": l} for c, l in loadings[:5]],
                    })
                # Project to PC scores, correlate with OD delta
                scores = X_std @ Vt[:n_comp].T  # (n_wo, n_comp)
                pc_od_corr = []
                for pc_i in range(n_comp):
                    sc = scores[:, pc_i].tolist()
                    for od_label, od_arr in [("ΔL1OD", y_l1), ("ΔL2OD", y_l2)]:
                        p = _pearson(sc, od_arr)
                        if p and abs(p["r"]) >= 0.3:
                            pc_od_corr.append({"pc": pc_i + 1, "vs": od_label, **p})
                # Per-ingredient Pearson with OD delta
                ingred_od_corr = []
                for j, chem in enumerate(all_chems):
                    col = X_arr[:, j].tolist()
                    for od_label, od_arr in [("ΔL1OD", y_l1), ("ΔL2OD", y_l2)]:
                        p = _pearson(col, od_arr)
                        if p:
                            ingred_od_corr.append({"化學品名": chem, "vs": od_label, **p})
                ingred_od_corr.sort(key=lambda x: abs(x["r"]), reverse=True)
                # Main ingredient = highest |r| with OD delta (excluding H2O)
                if ingred_od_corr:
                    main_ingred = ingred_od_corr[0]["化學品名"]
                pca_result = {
                    "n_work_orders": len(used_wos),
                    "n_ingredients": len(all_chems),
                    "principal_components": pc_loadings,
                    "pc_vs_od_correlation": pc_od_corr,
                    "ingredient_od_correlation": ingred_od_corr[:10],
                    "method": "PCA (SVD) on standardized ingredient weights → OD delta correlation",
                }
            except Exception:
                pass

    analysis["formulation_analysis"] = {
        "ingredient_summary": ingred_summary,
        "batch_composition": batch_comp,
        "main_ingredient": main_ingred,
        "variation_by_ingredient": var_by_ingred,
        "pca": pca_result,
    }

    summary = {
        "total_work_orders": len(_wo),
        "total_ipqc_records": len(_ipqc),
        "total_droplet_records": len(_droplet),
        "total_formulation_records": len(by_wo),
        "formulation_tables_matched": f_tables,
        "anomaly_batches": sum(1 for s in scored if s["anomaly_score"] > 0),
        "main_ingredient": main_ingred,
    }

    # 5) AI Summary
    ai_summary = _generate_ai_summary(marker, summary, analysis, user_question)

    # 6) 存入歷史
    analysis_json = json.dumps({"analysis": analysis, "summary": summary}, ensure_ascii=False)
    history_id = None
    try:
        hdb = sqlite3.connect(ANALYSIS_DB)
        cur = hdb.execute(
            "INSERT INTO analysis_history (marker, work_order, date_from, date_to, user_question, analysis_result, ai_summary) VALUES (?,?,?,?,?,?,?)",
            (marker, work_order, date_from, date_to, user_question, analysis_json, ai_summary)
        )
        history_id = cur.lastrowid
        hdb.commit(); hdb.close()
    except Exception as e:
        print(f"Save history error: {e}")

    return jsonify({
        "ok": True, "summary": summary, "analysis": analysis,
        "ai_summary": ai_summary, "history_id": history_id,
        "work_orders": _wo,
        "ipqc": _ipqc,
        "droplet_records": _droplet,
        "formulations": _formulations,
    })


@process_analysis_bp.route("/api/process-analysis/history", methods=["GET"])
def pa_history():
    """查詢分析歷史"""
    marker = request.args.get("marker", "")
    limit = int(request.args.get("limit", 20))
    db = sqlite3.connect(ANALYSIS_DB)
    db.row_factory = sqlite3.Row
    if marker:
        rows = db.execute("SELECT * FROM analysis_history WHERE marker LIKE ? ORDER BY created_at DESC LIMIT ?",
                          (f"%{marker}%", limit)).fetchall()
    else:
        rows = db.execute("SELECT * FROM analysis_history ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    db.close()
    return jsonify({"ok": True, "history": [dict(r) for r in rows]})


@process_analysis_bp.route("/api/process-analysis/ask-ai", methods=["POST"])
def pa_ask_ai():
    """使用 Bedrock Claude 針對分析結果進行深入問答"""
    import boto3
    body = request.json or {}
    user_msg = body.get("question", "").strip()
    ai_summary = body.get("ai_summary", "")
    marker = body.get("marker", "")
    history_id = body.get("history_id")

    if not user_msg:
        return jsonify({"ok": False, "error": "請輸入問題"}), 400

    # Build context from analysis history if available
    extra_context = ""
    if history_id:
        try:
            hdb = sqlite3.connect(ANALYSIS_DB)
            hdb.row_factory = sqlite3.Row
            row = hdb.execute("SELECT analysis_result FROM analysis_history WHERE id=?", (history_id,)).fetchone()
            if row:
                extra_context = row["analysis_result"][:8000]
            hdb.close()
        except Exception:
            pass

    system_prompt = (
        "你是一位化學品生產製程分析專家，專門分析 Beads 試劑的 IPQC 品質數據、配藥紀錄、滴定條件和凍乾參數。"
        "請用繁體中文回答，回答要具體、有數據支撐，並給出可執行的建議。"
        "使用 Markdown 格式（## 標題、- 列表、**粗體**）讓回答結構清晰。"
    )

    context_block = f"## 目前分析的 Marker: {marker}\n\n"
    if ai_summary:
        context_block += f"## AI 分析報告摘要:\n{ai_summary[:6000]}\n\n"
    if extra_context:
        context_block += f"## 詳細分析數據 (JSON):\n{extra_context[:4000]}\n\n"

    messages = [
        {"role": "user", "content": f"{context_block}\n---\n使用者問題：{user_msg}"}
    ]

    try:
        client = boto3.client("bedrock-runtime", region_name="us-west-2")
        resp = client.invoke_model(
            modelId="anthropic.claude-3-haiku-20240307-v1:0",
            body=json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 4096,
                "system": system_prompt,
                "messages": messages,
            })
        )
        result = json.loads(resp["body"].read())
        answer = result["content"][0]["text"]
    except Exception as e:
        return jsonify({"ok": False, "error": f"Bedrock 呼叫失敗: {str(e)}"}), 500

    # Save Q&A to history
    try:
        hdb = sqlite3.connect(ANALYSIS_DB)
        hdb.execute(
            """CREATE TABLE IF NOT EXISTS ai_qa_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT DEFAULT (datetime('now','localtime')),
                marker TEXT, history_id INTEGER,
                question TEXT, answer TEXT
            )"""
        )
        hdb.execute(
            "INSERT INTO ai_qa_history (marker, history_id, question, answer) VALUES (?,?,?,?)",
            (marker, history_id, user_msg, answer)
        )
        hdb.commit()
        hdb.close()
    except Exception:
        pass

    return jsonify({"ok": True, "answer": answer})


@process_analysis_bp.route("/api/process-analysis/save-note", methods=["POST"])
def pa_save_note():
    """對某筆分析加上 AI 摘要 / 使用者備註"""
    body = request.json or {}
    aid = body.get("id")
    ai_summary = body.get("ai_summary", "")
    tags = body.get("tags", "")
    if not aid:
        return jsonify({"ok": False, "error": "缺少 id"}), 400
    db = sqlite3.connect(ANALYSIS_DB)
    db.execute("UPDATE analysis_history SET ai_summary=?, tags=? WHERE id=?", (ai_summary, tags, aid))
    db.commit(); db.close()
    return jsonify({"ok": True})
