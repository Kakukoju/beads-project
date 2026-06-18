import streamlit as st
import pandas as pd
import sqlite3
from pathlib import Path
from streamlit_autorefresh import st_autorefresh
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
import matplotlib
import streamlit.components.v1 as components

# --- 1. 基本設定 ---
matplotlib.rcParams['font.family'] = 'Microsoft JhengHei'
plt.rcParams['axes.unicode_minus'] = False

# [路徑設定]
DB_PATH = r"\\fls341\MBBU_FAB\MB_PD\BeadRecord\work_orders.db"
PHOTO_DIR = Path(r"\\fls341\MBBU_FAB\MB_PD\BeadRecord\Photos")

STATIONS_CONFIG = [
    {"name": "收藥", "time_col": "時間_收藥", "photo_col": "收藥_照片", "uploader_col": "收藥_上傳者"},
    {"name": "滴定準備", "time_col": "時間_滴定準備", "photo_col": "滴定準備_照片", "uploader_col": "滴定準備_上傳者"},
    {"name": "滴定開始", "time_col": "時間_滴定開始", "photo_col": "滴定開始_照片", "uploader_col": "滴定開始_上傳者"},
    {"name": "滴定結束", "time_col": "時間_滴定結束", "photo_col": "滴定結束_照片", "uploader_col": "滴定結束_上傳者"},
    {"name": "凍乾準備", "time_col": "時間_凍乾準備", "photo_col": "凍乾準備_照片", "uploader_col": "凍乾準備_上傳者"},
    {"name": "凍乾開始", "time_col": "時間_凍乾開始", "photo_col": "凍乾開始_照片", "uploader_col": "凍乾開始_上傳者"},
    {"name": "凍乾結束", "time_col": "時間_凍乾結束", "photo_col": "凍乾結束_照片", "uploader_col": "凍乾結束_上傳者"},
]

TIME_COLS = [s["time_col"] for s in STATIONS_CONFIG]
STATION_NAMES = [s["name"] for s in STATIONS_CONFIG]
PHOTO_COLS = [s["photo_col"] for s in STATIONS_CONFIG]
UPLOADER_COLS = [s["uploader_col"] for s in STATIONS_CONFIG]

st.set_page_config(page_title="工單追蹤儀表板", layout="wide")

st.title("📦 工單 QR 掃描追蹤系統")
st_autorefresh(interval=60000, key="refresh")

# --- 2. CSS 美化 ---
st.markdown("""
<style>
/* 欄位微調 */
[data-testid="column"] { padding: 0px 4px !important; }
[data-testid="stHorizontalBlock"] { gap: 0px !important; }

/* 圖片樣式 */
div[data-testid="stImage"] { margin-bottom: -16px !important; }
div[data-testid="stImage"] img {
    aspect-ratio: 1 / 1 !important;
    object-fit: cover !important;
    width: 100% !important;
    border-top-left-radius: 8px !important;
    border-top-right-radius: 8px !important;
    border-bottom-left-radius: 0px !important;
    border-bottom-right-radius: 0px !important;
}

/* 按鈕樣式 (放大鏡) */
div[data-testid="stButton"] button[kind="secondary"] {
    border-top-left-radius: 0px !important;
    border-top-right-radius: 0px !important;
    border-bottom-left-radius: 8px !important;
    border-bottom-right-radius: 8px !important;
    border: 1px solid rgba(128, 128, 128, 0.2) !important;
    border-top: none !important;
    background-color: #262730 !important;
    color: #AAAAAA !important;
    width: 100% !important;
    padding: 0px !important;
    line-height: 1.2 !important;
    font-size: 12px !important;
    min-height: 24px !important;
}
div[data-testid="stButton"] button[kind="secondary"]:hover {
    background-color: #3E404D !important;
    color: #FFFFFF !important;
    border-color: rgba(255, 255, 255, 0.5) !important;
}
</style>
""", unsafe_allow_html=True)

# --- 3. 邏輯函式 ---

# [NEW] 彈出視窗函式 (解決捲動與換頁問題)
@st.dialog("📸 照片檢視", width="large")
def show_photo_modal(photo_path, caption):
    st.image(photo_path, caption=caption, use_container_width=True)

def format_timestamp(ts):
    if pd.isna(ts): return "無時間"
    try: return ts.strftime("%Y-%m-%d %H:%M:%S")
    except AttributeError: return str(ts)

@st.cache_data(ttl=5)
def load_data():
    try:
        conn = sqlite3.connect(DB_PATH)
        all_cols = ["工單號", "製令數量", "bead_name", "日期"] + TIME_COLS + PHOTO_COLS + UPLOADER_COLS
        query = f"SELECT {', '.join(all_cols)} FROM work_orders"
        df = pd.read_sql_query(query, conn)
        conn.close()
        return df
    except Exception as e:
        st.error(f"❌ DB Error: {str(e)}")
        return pd.DataFrame()

def get_progress_info(row, time_cols, station_names):
    if all(pd.isna(row[col]) for col in time_cols): return 0, "未開始"
    if all(pd.notna(row[col]) for col in time_cols): return len(time_cols), "已完成"
    for i in reversed(range(len(time_cols))):
        if pd.notna(row[time_cols[i]]): return i + 1, station_names[i]
    return 0, "狀態不明"

def safe_parse_datetime(val):
    if pd.isna(val): return None
    val_str = str(val).strip()
    if not val_str or val_str.upper() == "NULL": return None
    try: return pd.to_datetime(val_str)
    except: return None

def preprocess_data(df):
    if df.empty: return df
    df["時間_收藥_parsed"] = df["時間_收藥"].apply(safe_parse_datetime)
    df["日期_原始_parsed"] = df["日期"].apply(safe_parse_datetime)
    df["日期_parsed"] = df.apply(lambda r: r["日期_原始_parsed"] if pd.notna(r["日期_原始_parsed"]) else r["時間_收藥_parsed"], axis=1)
    df = df[df["日期_parsed"].notna()].copy()
    for col in TIME_COLS:
        if col in df.columns: df[col] = df[col].apply(safe_parse_datetime)
    df["製令數量"] = pd.to_numeric(df["製令數量"], errors="coerce")
    prog = df.apply(lambda r: pd.Series(get_progress_info(r, TIME_COLS, STATION_NAMES)), axis=1)
    df[["進度階段", "目前工站"]] = prog
    df["進度百分比"] = df["進度階段"].apply(lambda x: int(x / len(TIME_COLS) * 100))
    return df

def parse_photo_files(photo_str):
    if pd.isna(photo_str) or not str(photo_str).strip(): return []
    return [f.strip() for f in str(photo_str).split(';') if f.strip()]

def calculate_photo_layout(num_photos):
    if num_photos <= 1: return 1, 1
    elif num_photos == 2: return 1, 2
    elif num_photos <= 4: return 2, 2
    elif num_photos <= 6: return 2, 3
    else: return 3, 3

# --- 4. Sidebar ---
def setup_sidebar(df):
    st.sidebar.header("🔎 工單篩選")
    st.sidebar.info(f"📊 總筆數: {len(df)}")
    wo_input = st.sidebar.text_input("工單號")
    bn_input = st.sidebar.text_input("Bead Name")
    
    if df.empty or "日期_parsed" not in df.columns: return df
    d_min = df["日期_parsed"].min().date()
    d_max = df["日期_parsed"].max().date()
    d_start = max(d_min, d_max - timedelta(days=30))
    dates = st.sidebar.date_input("日期區間", [d_start, d_max], min_value=d_min, max_value=d_max)
    
    if len(dates) == 2:
        s, e = dates
        edt = pd.to_datetime(e) + timedelta(days=1) - timedelta(seconds=1)
        filtered = df[(df["日期_parsed"] >= pd.to_datetime(s)) & (df["日期_parsed"] <= edt)].copy()
    else:
        filtered = df.copy()
        
    if wo_input: filtered = filtered[filtered["工單號"].astype(str).str.contains(wo_input.strip(), case=False, na=False)]
    if bn_input: filtered = filtered[filtered["bead_name"].astype(str).str.contains(bn_input.strip(), case=False, na=False)]
    if st.sidebar.checkbox("只顯示未完成"): filtered = filtered[filtered["進度百分比"] < 100]
    return filtered.sort_values(by=["日期_parsed", "進度百分比"], ascending=[False, True])

# --- 5. 顯示邏輯 ---

def display_dashboard(filtered_df):
    # 開始渲染工單
    for _, row in filtered_df.iterrows():
        # 即使不需要 Scroll Script，加上 ID 也是好習慣，方便未來擴充錨點功能
        st.markdown(f"<div id='wo_{row['工單號']}'></div>", unsafe_allow_html=True)

        col_chk, col_info = st.columns([0.05, 0.95])
        with col_chk:
            show_photos = st.checkbox("圖", key=f"show_{row['工單號']}", label_visibility="collapsed")
        
        with col_info:
            st.markdown(f"#### 📦 {row['工單號']} <span style='font-size:0.8em; color:#888;'>| {row['目前工站']}</span>", unsafe_allow_html=True)
            st.progress(row["進度百分比"] / 100)
            
            auto_hide = False
            last_ts = row[TIME_COLS[-1]]
            if pd.notna(last_ts) and (datetime.now() - last_ts > timedelta(hours=1)):
                auto_hide = True
            
            if not auto_hide or show_photos:
                st_cols = st.columns(len(STATIONS_CONFIG))
                for station, col in zip(STATIONS_CONFIG, st_cols):
                    with col:
                        # Header
                        ts_raw = row[station["time_col"]]
                        uploader = row[station["uploader_col"]]
                        ts_str = format_timestamp(ts_raw)
                        time_short = ts_str.split(" ")[-1][:5] if " " in ts_str else "--:--"
                        user_name = str(uploader) if pd.notna(uploader) else "Unknown"
                        
                        if pd.notna(ts_raw):
                            header_html = f"""
                            <div style='text-align:center; margin-bottom:4px; line-height:1.2;'>
                                <div style='font-size:0.85rem; font-weight:bold; color:#E0E0E0;'>{station['name']}</div>
                                <div style='font-size:0.75rem; color:#888;'>{time_short}</div>
                                <div style='font-size:0.7rem; color:#666;'>{user_name}</div>
                            </div>
                            """
                        else:
                            header_html = f"""
                            <div style='text-align:center; margin-bottom:4px; opacity:0.3;'>
                                <div style='font-size:0.85rem;'>{station['name']}</div>
                                <div style='font-size:0.75rem;'>--:--</div>
                            </div>
                            """
                        st.markdown(header_html, unsafe_allow_html=True)
                        
                        # Insta-Grid
                        photo_files = parse_photo_files(row[station["photo_col"]])
                        
                        if photo_files:
                            num = len(photo_files)
                            rows, cols_per_row = calculate_photo_layout(num)
                            idx = 0
                            for _ in range(rows):
                                rem = num - idx
                                c_count = min(cols_per_row, rem)
                                if c_count > 0:
                                    sub_cols = st.columns(c_count)
                                    for sub_c in sub_cols:
                                        if idx < num:
                                            with sub_c:
                                                f_name = photo_files[idx]
                                                f_path = PHOTO_DIR / f_name
                                                if f_path.exists():
                                                    # 1. 顯示縮圖
                                                    st.image(str(f_path), use_container_width=True)
                                                    
                                                    # 2. 準備按鈕 Key 和 Caption
                                                    uniq_key = f"btn_{row['工單號']}_{station['name']}_{idx}"
                                                    caption_str = f"{station['name']} - {ts_str} ({user_name})"
                                                    
                                                    # 3. [修正重點] 使用 on_click=show_photo_modal 並透過 args 鎖定變數
                                                    st.button(
                                                        "🔍", 
                                                        key=uniq_key, 
                                                        type="secondary", 
                                                        use_container_width=True,
                                                        on_click=show_photo_modal,
                                                        args=(str(f_path), caption_str)
                                                    )
                                                else:
                                                    st.caption("Lost")
                                            idx += 1
                                    st.write("")
                        else:
                            st.write("") # 空白佔位

                st.write("---") # 工單分隔線

    if st.checkbox("📋 顯示原始資料", key="raw_table"):
        st.dataframe(filtered_df)

# --- 6. 執行 ---
def main():
    try:
        raw_df = load_data()
        if raw_df.empty:
            st.warning("⚠ 無資料")
            return
        df = preprocess_data(raw_df)
        final_df = setup_sidebar(df)
        if final_df.empty:
            st.info("ℹ️ 無符合工單")
        else:
            display_dashboard(final_df)
    except Exception as e:
        st.error(f"Error: {e}")

if __name__ == "__main__":
    main()