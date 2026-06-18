import streamlit as st
import pandas as pd
import sqlite3
from pathlib import Path
import requests

DB_PATH = r"C:\Users\harryhrguo\WebApp\dropfreeze\work_orders.db"
# 本地照片資料夾路徑（請調整成你的實際照片目錄）
PHOTO_DIR = Path(r"C:\Users\harryhrguo\WebApp\dropfreeze\photos")


st.set_page_config(page_title="工單追蹤儀表板", layout="wide")
st.title("📦 工單 QR 掃描追蹤系統 + 照片")

@st.cache_data(ttl=10)
def load_data():
    if not Path(DB_PATH).exists():
        st.error("找不到資料庫！請確認資料庫路徑正確。")
        return pd.DataFrame()
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        query = """
        SELECT 
            col1 AS 工單號, col2 AS 製令數量, col3 AS bead_name, col4 AS PN,
            col5 AS 是否懸浮, col6 AS 日期, col7 AS L1反應OD, col8 AS L1起始OD,
            col9 AS L2反應OD, col10 AS L2起始OD, col11 AS liquid_storge_避光,
            col12 AS liquid_storge_冰浴, col13 AS 滴定_避光, col14 AS 滴定_冰浴,
            col15 AS 滴定_攪拌, col16 AS Dispense_Lot_1, col17 AS port_1,
            col18 AS pump_1, col19 AS 凍乾機_1, col20 AS Dispense_Lot_2,
            col21 AS port_2, col22 AS pump_2, col23 AS 凍乾機_2, col24 AS Dispense_Lot_3,
            col25 AS port_3, col26 AS pump_3, col27 AS 凍乾機_3, col28 AS Dispense_Lot_4,
            col29 AS port_4, col30 AS pump_4, col31 AS 凍乾機_4, col32 AS 淨重g,
            col33 AS 時間_收藥, col34 AS 時間_滴定準備開始, col35 AS 時間_滴定開始,
            col36 AS 時間_滴定結束, col37 AS 時間_凍乾準備開始, col38 AS 時間_凍乾開始,
            col39 AS 時間_凍乾結束
        FROM work_orders
        """
        df = pd.read_sql_query(query, conn)
        return df
    except sqlite3.Error as e:
        st.error(f"資料庫查詢錯誤：{e}")
        return pd.DataFrame()
    finally:
        if conn:
            conn.close()

def check_photo_exists(url):
    try:
        r = requests.head(url, timeout=2)
        return r.status_code == 200
    except:
        return False
    
df = load_data()

if df.empty:
    st.warning("目前尚無工單資料或載入失敗。")
else:
    time_list = [
        "時間_收藥", "時間_滴定準備開始", "時間_滴定開始",
        "時間_滴定結束", "時間_凍乾準備開始", "時間_凍乾開始", "時間_凍乾結束"
    ]
    station_names = [
        "收藥", "滴定準備開始", "滴定開始",
        "滴定結束", "凍乾準備開始", "凍乾開始", "凍乾結束"
    ]

    work_orders = df["工單號"].unique()
    selected_order = st.selectbox("選擇工單號篩選", options=["全部"] + list(work_orders))

    if selected_order != "全部":
        df = df[df["工單號"] == selected_order]

    def get_station_progress(row):
        for i, col in reversed(list(enumerate(time_list))):
            if pd.notna(row[col]) and str(row[col]).strip() != "":
                return i + 1
        return 0

    df["進度階段"] = df.apply(get_station_progress, axis=1)
    df["目前工站"] = df["進度階段"].apply(lambda x: station_names[x-1] if x > 0 else "未開始")
    total_stations = len(time_list)
    df["進度百分比"] = df["進度階段"].apply(lambda x: int((x / total_stations) * 100))
     # 本地照片路徑欄位
    df["照片路徑"] = df["工單號"].apply(lambda x: str(PHOTO_DIR / f"{x}.jpg"))


    st.subheader("工單進度概覽")
    for _, row in df.iterrows():
        st.write(f"### 工單號: {row['工單號']} | 目前工站: {row['目前工站']}")
        st.progress(row["進度百分比"])
        
        photo_url = row["照片路徑"]
        if check_photo_exists(photo_url):
            st.image(photo_url, width=200, caption=f"工單 {row['工單號']} 照片")
            st.write(f"[🔗 查看原圖]({photo_url})")
        else:
            st.info("📷 尚未上傳照片")
        
        st.write("---")

    if st.checkbox("顯示完整欄位資料"):
        st.dataframe(df[["工單號", "製令數量", "bead_name", "日期", "目前工站", "進度百分比"] + time_list])