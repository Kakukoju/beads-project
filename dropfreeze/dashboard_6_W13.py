import streamlit as st 
import pandas as pd
import sqlite3
from pathlib import Path
from streamlit_autorefresh import st_autorefresh
from PIL import Image
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
import matplotlib
matplotlib.rcParams['font.family'] = 'Microsoft JhengHei'
plt.rcParams['axes.unicode_minus'] = False 




DB_PATH = r"\\fls341\MBBU_FAB\MB_PD\BeadRecord\work_orders_test.db"
PHOTO_DIR = Path(r"\\fls341\MBBU_FAB\MB_PD\BeadRecord\Photos_test")

st.set_page_config(page_title="工單追蹤儀表板", layout="wide")
st.title("📦 工單 QR 掃描追蹤系統 + 照片")

st_autorefresh(interval=60000, key="refresh")

def format_timestamp(ts):
    try:
        dt = datetime.fromisoformat(str(ts))
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except:
        return "無時間"

@st.cache_data(ttl=5) 
def load_data():
    conn = sqlite3.connect(DB_PATH)
    query = """
    SELECT 工單號, 製令數量, bead_name, 日期,
           時間_收藥, 時間_滴定準備, 時間_滴定開始,
           時間_滴定結束, 時間_凍乾準備,
           時間_凍乾開始, 時間_凍乾結束,
           收藥_照片 AS col33_photo, 滴定準備_照片 AS col34_photo, 滴定開始_照片 AS col35_photo,
           滴定結束_照片 AS col36_photo, 凍乾準備_照片 AS col37_photo, 凍乾開始_照片 AS col38_photo,
           凍乾結束_照片 AS col39_photo,
           收藥_上傳者 AS col33_uploader, 滴定準備_上傳者 AS col34_uploader, 滴定開始_上傳者 AS col35_uploader,
           滴定結束_上傳者 AS col36_uploader, 凍乾準備_上傳者 AS col37_uploader, 凍乾開始_上傳者 AS col38_uploader,
           凍乾結束_上傳者 AS col39_uploader
    FROM work_orders
    """
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df

df = load_data()

if not df.empty:
    time_list = [
        "時間_收藥", "時間_滴定準備", "時間_滴定開始",
        "時間_滴定結束", "時間_凍乾準備", "時間_凍乾開始", "時間_凍乾結束"
    ]
    station_names = [
        "收藥", "滴定準備", "滴定開始", 
        "滴定結束", "凍乾準備", "凍乾開始", "凍乾結束"
    ]
    photo_cols = [
        "col33_photo", "col34_photo", "col35_photo", 
        "col36_photo", "col37_photo", "col38_photo", "col39_photo"
    ]
    uploader_cols = [
        "col33_uploader", "col34_uploader", "col35_uploader", 
        "col36_uploader", "col37_uploader", "col38_uploader", "col39_uploader"
    ]

    def get_progress_info(row):
        # 檢查是否所有時間欄都為空 → 顯示「未開始」
        if all(pd.isna(row[col]) or str(row[col]).strip() == "" for col in time_list):
            return 0, "未開始"

        # 檢查是否全部都填了 → 顯示「已完成」
        if all(pd.notna(row[col]) and str(row[col]).strip() != "" for col in time_list):
            return len(time_list), "已完成"

        # 否則：找出最後一個已填欄位 → 顯示該工站名稱
        for i in reversed(range(len(time_list))):
            if pd.notna(row[time_list[i]]) and str(row[time_list[i]]).strip() != "":
                return i + 1, station_names[i]


    df[["進度階段", "目前工站"]] = df.apply(lambda row: pd.Series(get_progress_info(row)), axis=1)
    df["進度百分比"] = df["進度階段"].apply(lambda x: int(x / len(time_list) * 100))

    # --- 篩選條件（Sidebar） ---
    st.sidebar.header("🔎 工單篩選")
    bead_options = sorted(df["bead_name"].dropna().unique())
    selected_beads = st.sidebar.multiselect("選擇 bead_name", options=bead_options, default=bead_options)

    df["日期_parsed"] = pd.to_datetime(df["日期"], errors='coerce')
    min_date = df["日期_parsed"].min()
    max_date = df["日期_parsed"].max()
    start_date, end_date = st.sidebar.date_input("選擇日期區間", [min_date, max_date], min_value=min_date, max_value=max_date)

    only_incomplete = st.sidebar.checkbox("只顯示尚未完成工單")
    sort_order = st.sidebar.radio("進度排序", options=["由高到低", "由低到高"], index=0)

    df["製令數量"] = pd.to_numeric(df["製令數量"], errors="coerce")

    filtered_df = df[
        df["bead_name"].isin(selected_beads) &
        (df["日期_parsed"] >= pd.to_datetime(start_date)) &
        (df["日期_parsed"] <= pd.to_datetime(end_date))
    ]
    if only_incomplete:
        filtered_df = filtered_df[filtered_df["進度百分比"] < 100]

    ascending = True if sort_order == "由低到高" else False
    filtered_df = filtered_df.sort_values(by="進度百分比", ascending=ascending)

      # === 統計圖表放在 Sidebar ===
    with st.sidebar.expander("📊 統計圖表"):
        st.markdown("**1. 各 bead_name 製令數量加總**")
        bead_summary = filtered_df.groupby("bead_name")["製令數量"].sum().sort_values(ascending=True)
        fig1, ax1 = plt.subplots(figsize=(4, 3))
        bead_summary.plot(kind="barh", ax=ax1)
        ax1.set_xlabel("製令數量")
        ax1.set_ylabel("bead_name")
        st.pyplot(fig1)

        st.markdown("**2. 各 bead_name 生產時間統計**")
        start_col = st.selectbox("起始時間欄位", time_list, index=0, key="time_start")
        end_col = st.selectbox("結束時間欄位", time_list, index=len(time_list)-1, key="time_end")

        if time_list.index(start_col) >= time_list.index(end_col):
            st.error("❌ 選擇區間順序錯誤，結束時間必須在起始時間之後")
        else:
            done_df = filtered_df[(filtered_df[end_col].notna()) & (filtered_df[start_col].notna())].copy()
            done_df["生產時長"] = (pd.to_datetime(done_df[end_col]) - pd.to_datetime(done_df[start_col])).dt.total_seconds() / 3600

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
            ax2.set_xticklabels(x)
            ax2.legend()

            # 加上數值標籤
            for bars in [bar1, bar2, bar3]:
                for bar in bars:
                    height = bar.get_height()
                    ax2.annotate(f"{height:.2f}",
                                xy=(bar.get_x() + bar.get_width() / 2, height),
                                xytext=(0, 3),  # 偏移值
                                textcoords="offset points",
                                ha='center', va='bottom', fontsize=8)

            st.pyplot(fig2)

    # === 顯示照片檢視（避免與按鈕衝突） ===
    if "viewing_photo" in st.session_state:
        st.subheader("🖼️ 照片檢視")
        st.image(st.session_state["viewing_photo"], caption=st.session_state["viewing_caption"], use_container_width=True)
        if st.button("🔙 返回儀表板"):
            st.session_state.pop("viewing_photo")
            st.session_state.pop("viewing_caption")
            st.rerun()
        st.stop()

    # === 顯示工單資料 ===
    for _, row in filtered_df.iterrows():
        col0, col1 = st.columns([0.1, 0.9])
        with col0:
            show_photos = st.checkbox("顯示照片", key=f"show_{row['工單號']}")
        with col1:
            st.write(f"### 工單號: {row['工單號']} | 目前工站: {row['目前工站']}")
            st.progress(row["進度百分比"])

            hide_photos = False
            end_time = row["時間_凍乾結束"]
            if pd.notna(end_time) and str(end_time).strip():
                try:
                    dt_end = pd.to_datetime(end_time)
                    if datetime.now() - dt_end > timedelta(hours=1):
                        hide_photos = True
                except Exception as e:
                    st.error(f"❗ 凍乾結束時間錯誤: {e}")

            if not hide_photos or show_photos:
                cols = st.columns(7)
                for i, col in enumerate(cols):
                    with col:
                        with st.container():
                            photo_file = row[photo_cols[i]]
                            raw_ts = row[time_list[i]]
                            time_stamp = format_timestamp(raw_ts)
                            uploader = row[uploader_cols[i]] if pd.notna(row[uploader_cols[i]]) and str(row[uploader_cols[i]]).strip() else "未知"
                            station_label = station_names[i]

                            if pd.notna(photo_file) and photo_file:
                                img_path = PHOTO_DIR / photo_file
                                if img_path.exists():
                                    st.image(str(img_path), caption="", width=150)
                                    st.markdown(
                                        f"<div style='text-align:center; font-size:0.9em; line-height:1.4em;'>"
                                        f"<strong>{station_label}</strong><br>{time_stamp}<br>By: {uploader}"
                                        f"</div>",
                                        unsafe_allow_html=True
                                    )
                                    if st.button(f"放大 {station_label}", key=f"view_{row['工單號']}_{i}"):
                                        st.session_state["viewing_photo"] = str(img_path)
                                        st.session_state["viewing_caption"] = f"{station_label} - {row['工單號']}\n{time_stamp} by {uploader}"
                                        st.rerun()
                                else:
                                    st.warning("❗ 檔案不存在")
                            else:
                                st.info("📷 無照片")
            else:
                st.caption("🕒 凍乾結束已超過 1 小時，預設不顯示照片（可勾選左側）")

            st.write("---")

    # === 📋 顯示完整欄位 ===
    if st.checkbox("📋 顯示完整欄位", key="main_show_full_table"):
        df2 = filtered_df.copy()
        for col in time_list:
            df2[col] = df2[col].apply(format_timestamp)
        st.dataframe(df2[["工單號", "製令數量", "bead_name", "日期", "目前工站", "進度百分比"] + time_list])

else:
    st.warning("⚠ 資料庫中目前沒有工單資料。")
