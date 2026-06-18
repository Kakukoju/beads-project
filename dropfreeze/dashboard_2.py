import streamlit as st
import pandas as pd
import sqlite3
from pathlib import Path
from streamlit_autorefresh import st_autorefresh

DB_PATH = r"C:\Users\harryhrguo\WebApp\dropfreeze\work_orders.db"
PHOTO_DIR = Path(r"C:\Users\harryhrguo\WebApp\dropfreeze\photos")

st.set_page_config(page_title="工單追蹤儀表板", layout="wide")
st.title("📦 工單 QR 掃描追蹤系統 + 照片")

# 自動刷新每 5 秒
st_autorefresh(interval=5000, key="refresh")

@st.cache_data(ttl=5)
def load_data():
    conn = sqlite3.connect(DB_PATH)
    query = """
    SELECT 工單號, 製令數量, bead_name, 日期,
           時間_收藥, 時間_滴定準備開始, 時間_滴定開始,
           時間_滴定結束, 時間_凍乾準備開始,
           時間_凍乾開始, 時間_凍乾結束,
           收藥_照片 AS col33_photo, 滴定準備_照片 AS col34_photo, 滴定開始_照片 AS col35_photo,
           滴定結束_照片 AS col36_photo, 凍乾準備_照片 AS col37_photo, 凍乾開始_照片 AS col38_photo,
           凍乾結束_照片 AS col39_photo
    FROM work_orders
    """
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df

df = load_data()

if not df.empty:
    time_list = [
        "時間_收藥", "時間_滴定準備開始", "時間_滴定開始",
        "時間_滴定結束", "時間_凍乾準備開始", "時間_凍乾開始", "時間_凍乾結束"
    ]
    station_names = [
        "收藥", "滴定準備開始", "滴定開始", 
        "滴定結束", "凍乾準備開始", "凍乾開始", "凍乾結束"
    ]
    photo_cols = [
        "col33_photo", "col34_photo", "col35_photo", 
        "col36_photo", "col37_photo", "col38_photo", "col39_photo"
    ]

    def get_progress_info(row):
        for i in reversed(range(len(time_list))):
            if pd.notna(row[time_list[i]]) and str(row[time_list[i]]).strip() != "":
                photo_file = row[photo_cols[i]]
                return i + 1, station_names[i], photo_file
        return 0, "未開始", None

    df[["進度階段", "目前工站", "照片檔名"]] = df.apply(lambda row: pd.Series(get_progress_info(row)), axis=1)
    df["進度百分比"] = df["進度階段"].apply(lambda x: int(x / len(time_list) * 100))
    df["照片路徑"] = df["照片檔名"].apply(lambda x: str(PHOTO_DIR / x) if pd.notna(x) and x else None)

    # 排序進度高的在上
    df = df.sort_values(by="進度百分比", ascending=False)

    for _, row in df.iterrows():
        st.write(f"### 工單號: {row['工單號']} | 目前工站: {row['目前工站']}")
        st.progress(row["進度百分比"])
        if row["照片路徑"] and Path(row["照片路徑"]).exists():
            st.image(row["照片路徑"], width=200, caption=f"{row['工單號']} 照片")
        else:
            st.info(f"📷 尚未上傳照片")

        st.write("---")

    if st.checkbox("顯示完整欄位"):
        st.dataframe(df[["工單號", "製令數量", "bead_name", "日期", "目前工站", "進度百分比", "照片檔名"] + time_list])
else:
    st.warning("資料庫目前沒有工單資料。")
