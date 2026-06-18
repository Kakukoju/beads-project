import streamlit as st
import pandas as pd
import sqlite3
from pathlib import Path
from streamlit_autorefresh import st_autorefresh
from PIL import Image
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
import matplotlib
import streamlit.components.v1 as components # 匯入 components



# --- 1. 基本設定 ---
# (此處程式碼不變)
matplotlib.rcParams['font.family'] = 'Microsoft JhengHei'
plt.rcParams['axes.unicode_minus'] = False
DB_PATH = r"\\fls341\MBBU_FAB\MB_PD\BeadRecord\work_orders_test.db"
PHOTO_DIR = Path(r"\\fls341\MBBU_FAB\MB_PD\BeadRecord\Photos_test")
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
st.title("📦 工單 QR 掃描追蹤系統 + 照片")

st_autorefresh(interval=60000, key="refresh")

# --- 2. 輔助函式 ---
# (此處程式碼不變)
def format_timestamp(ts):
    if pd.isna(ts): return "無時間"
    try: return ts.strftime("%Y-%m-%d %H:%M:%S")
    except AttributeError: return str(ts)

@st.cache_data(ttl=5)
def load_data():
    conn = sqlite3.connect(DB_PATH)
    all_cols_to_select = ["工單號", "製令數量", "bead_name", "日期"] + TIME_COLS + PHOTO_COLS + UPLOADER_COLS
    query = f"SELECT {', '.join(all_cols_to_select)} FROM work_orders"
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df

def get_progress_info(row, time_cols, station_names):
    if all(pd.isna(row[col]) for col in time_cols): return 0, "未開始"
    if all(pd.notna(row[col]) for col in time_cols): return len(time_cols), "已完成"
    for i in reversed(range(len(time_cols))):
        if pd.notna(row[time_cols[i]]): return i + 1, station_names[i]
    return 0, "狀態不明"

def preprocess_data(df):
    for col in TIME_COLS:
        df[col] = pd.to_datetime(df[col], errors='coerce')
    df["日期_parsed"] = pd.to_datetime(df["日期"], errors='coerce')
    df["製令數量"] = pd.to_numeric(df["製令數量"], errors="coerce")
    progress_info = df.apply(
        lambda row: pd.Series(get_progress_info(row, TIME_COLS, STATION_NAMES)), axis=1
    )
    df[["進度階段", "目前工站"]] = progress_info
    df["進度百分比"] = df["進度階段"].apply(lambda x: int(x / len(TIME_COLS) * 100))
    return df



# --- 3. Sidebar 篩選與圖表 ---

def setup_sidebar(df):
    """設定 Sidebar 內容並回傳篩選後的 DataFrame"""
    
    # --- ★ 2. 這是最終的正確寫法 ★ ---
    # 使用 'with st.sidebar:' 區塊
    # 並在裡面呼叫 'components.html(...)'
    
    with st.sidebar:

        st.sidebar.header("🔎 工單篩選")

    selected_work_order = st.sidebar.text_input("輸入工單號 (可留空)")
    selected_bead_name = st.sidebar.text_input("輸入 Bead_Name (忽略大小寫, 可留空)")

    # (日期篩選邏輯... 保持不變)
    db_min_date_ts = df["日期_parsed"].min()
    db_max_date_ts = df["日期_parsed"].max()
    today = datetime.now().date()
    seven_days_ago = today - timedelta(days=7)
    db_min_date = db_min_date_ts.date() if pd.notna(db_min_date_ts) else seven_days_ago
    db_max_date = db_max_date_ts.date() if pd.notna(db_max_date_ts) else today
    min_val = min(db_min_date, seven_days_ago)
    max_val = max(db_max_date, today)
    default_start_date = seven_days_ago
    default_end_date = today

    start_date, end_date = st.sidebar.date_input(
        "選擇日期區間", 
        [default_start_date, default_end_date], 
        min_value=min_val, 
        max_value=max_val
    )
    
    only_incomplete = st.sidebar.checkbox("只顯示尚未完成工單")
    
    # (篩選邏輯... 保持不變)
    start_datetime_obj = pd.to_datetime(start_date)
    end_datetime_obj = pd.to_datetime(end_date)
    filtered_df = df[
        (df["日期_parsed"] >= start_datetime_obj) &
        (df["日期_parsed"] <= end_datetime_obj)
    ]
    if selected_work_order:
        filtered_df = filtered_df[filtered_df["工單號"].astype(str).str.contains(selected_work_order.strip(), case=False, na=False)]
    if selected_bead_name:
        filtered_df = filtered_df[filtered_df["bead_name"].astype(str).str.contains(selected_bead_name.strip(), case=False, na=False)]
    if only_incomplete:
        filtered_df = filtered_df[filtered_df["進度百分比"] < 100]
    
    # (排序邏輯... 保持不變)
    if "日期_parsed" in filtered_df.columns and "進度百分比" in filtered_df.columns and not filtered_df.empty:
        filtered_df = filtered_df.sort_values(by=["日期_parsed", "進度百分比"], ascending=[False, True])

    # (統計圖表邏輯... 保持不變)
    with st.sidebar.expander("📊 統計圖表"):
        st.markdown("**1. 各 bead_name 製令數量加總**")
        if not filtered_df.empty and "bead_name" in filtered_df.columns:
            bead_summary = filtered_df.groupby("bead_name")["製令數量"].sum().sort_values(ascending=False)
            st.bar_chart(bead_summary, horizontal=True)
        else:
            st.info("無資料可顯示")

        st.markdown("**2. 各 bead_name 生產時間統計**")
        start_col = st.selectbox("起始時間欄位", STATION_NAMES, index=0, key="time_start")
        end_col = st.selectbox("結束時間欄位", STATION_NAMES, index=len(STATION_NAMES)-1, key="time_end")
        start_col_key = TIME_COLS[STATION_NAMES.index(start_col)]
        end_col_key = TIME_COLS[STATION_NAMES.index(end_col)]

        if STATION_NAMES.index(start_col) >= STATION_NAMES.index(end_col):
            st.error("❌ 選擇區間順序錯誤，結束時間必須在起始時間之後")
        else:
            done_df = filtered_df[(filtered_df[end_col_key].notna()) & (filtered_df[start_col_key].notna())].copy()
            if done_df.empty:
                st.info("在選定區間内無已完成的工單可供統計。")
            else:
                done_df["生產時長"] = (done_df[end_col_key] - done_df[start_col_key]).dt.total_seconds() / 3600
                prod_stats = done_df.groupby("bead_name")["生產時長"].agg(["min", "max", "mean"]).sort_values(by="mean", ascending=False)
                fig2, ax2 = plt.subplots(figsize=(5, 3)) 
                x = prod_stats.index.astype(str)
                width = 0.2
                x_range = range(len(x))
                bar1 = ax2.bar([i - width for i in x_range], prod_stats["min"], width=width, label="最短", color="skyblue")
                bar2 = ax2.bar(x_range, prod_stats["mean"], width=width, label="平均", color="orange")
                bar3 = ax2.bar([i + width for i in x_range], prod_stats["max"], width=width, label="最長", color="lightgreen")
                ax2.set_ylabel("小時")
                ax2.set_title("各 bead_name 生產時長 (min / avg / max)")
                ax2.set_xticks(x_range)
                ax2.set_xticklabels(x, rotation=45, ha='right')
                ax2.legend()
                for bars in [bar1, bar2, bar3]:
                    for bar in bars:
                        height = bar.get_height()
                        if height > 0:
                            ax2.annotate(f"{height:.2f}",
                                        xy=(bar.get_x() + bar.get_width() / 2, height),
                                        xytext=(0, 3), textcoords="offset points",
                                        ha='center', va='bottom', fontsize=8)
                fig2.tight_layout() 
                st.pyplot(fig2)

    return filtered_df

# --- 4. 主頁面顯示 ---
# (此處程式碼不變)
def display_photo_viewer():
    st.subheader("🖼️ 照片檢視")
    st.image(st.session_state["viewing_photo"], caption=st.session_state["viewing_caption"], use_container_width=True)
    if st.button("🔙 返回儀表板"):
        st.session_state.pop("viewing_photo")
        st.session_state.pop("viewing_caption")
        st.rerun()
    st.stop()

def display_dashboard(filtered_df):
    if "viewing_photo" in st.session_state:
        display_photo_viewer()
    for _, row in filtered_df.iterrows():
        col0, col1 = st.columns([0.1, 0.9])
        with col0:
            show_photos_checkbox = st.checkbox("顯示照片", key=f"show_{row['工單號']}")
        with col1:
            st.write(f"### 工單號: {row['工單號']} | 目前工站: {row['目前工站']}")
            st.progress(row["進度百分比"])
            hide_photos = False
            end_time = row[TIME_COLS[-1]] 
            if pd.notna(end_time) and (datetime.now() - end_time > timedelta(hours=1)):
                hide_photos = True
            if not hide_photos or show_photos_checkbox:
                cols = st.columns(len(STATIONS_CONFIG))
                for station, col in zip(STATIONS_CONFIG, cols):
                    with col, st.container():
                        photo_file = row[station["photo_col"]]
                        raw_ts = row[station["time_col"]]
                        uploader = row[station["uploader_col"]]
                        time_stamp = format_timestamp(raw_ts)
                        uploader_name = uploader if pd.notna(uploader) and str(uploader).strip() else "未知"
                        station_label = station["name"]
                        if pd.notna(photo_file) and photo_file:
                            img_path = PHOTO_DIR / photo_file
                            if img_path.exists():
                                st.image(str(img_path), caption="", width=150)
                                st.markdown(
                                    f"<div style='text-align:center; font-size:0.9em; line-height:1.4em;'>"
                                    f"<strong>{station_label}</strong><br>{time_stamp}<br>By: {uploader_name}"
                                    f"</div>", unsafe_allow_html=True
                                )
                                if st.button(f"放大 {station_label}", key=f"view_{row['工單號']}_{station['name']}"):
                                    st.session_state["viewing_photo"] = str(img_path)
                                    st.session_state["viewing_caption"] = f"{station_label} - {row['工單號']}\n{time_stamp} by {uploader_name}"
                                    st.rerun()
                            else:
                                st.warning("❗ 檔案不存在")
                                st.markdown(f"**{station_label}**<br>{time_stamp}", unsafe_allow_html=True)
                        else:
                            st.info("📷 無照片")
                            st.markdown(
                                f"<div style='text-align:center; font-size:0.9em; line-height:1.4em; color:gray;'>"
                                f"<strong>{station_label}</strong><br>{time_stamp}"
                                f"</div>", unsafe_allow_html=True
                            )
            else:
                st.caption(f"🕒 {STATION_NAMES[-1]} 已超過 1 小時，預設不顯示照片（可勾選左側）")
            st.write("---")
    if st.checkbox("📋 顯示完整欄位", key="main_show_full_table"):
        df_display = filtered_df.copy()
        display_time_cols = ["日期_parsed"] + TIME_COLS
        for col in display_time_cols:
            if col in df_display:
                 df_display[col] = df_display[col].apply(format_timestamp)
        df_display = df_display.rename(columns={"日期_parsed": "日期"})
        st.dataframe(df_display[
            ["工單號", "製令數量", "bead_name", "日期", "目前工站", "進度百分比"] + TIME_COLS
        ])

# --- 5. 主程式 ---
def main():
    
    try:
        raw_df = load_data()
        if raw_df.empty:
            st.warning("⚠ 資料庫中目前沒有工單資料。")
            return

        df = preprocess_data(raw_df)
        filtered_df = setup_sidebar(df)
        
        if filtered_df.empty:
            st.info("ℹ️ 根據目前的篩選條件，沒有符合的工單。")
        else:
            display_dashboard(filtered_df)
            
    except sqlite3.OperationalError as e:
        st.error(f"❌ 資料庫連接失敗：{e}")
        st.error(f"請檢查路徑是否正確且可存取： {DB_PATH}")
    except Exception as e:
        st.error(f"發生未預期的錯誤：{e}")

if __name__ == "__main__":
    main()