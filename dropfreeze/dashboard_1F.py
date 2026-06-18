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

DB_PATH = r"\\fls341\MBBU_FAB\MB_PD\BeadRecord\work_orders.db"
PHOTO_DIR = Path(r"\\fls341\MBBU_FAB\MB_PD\BeadRecord\Photos")

st.set_page_config(page_title="工單追蹤儀表板", layout="wide")
st.title("📦 工單 QR 掃描追蹤系統 + 照片")

st_autorefresh(interval=10000, key="refresh")

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
    st.write("資料已載入，共有", len(df), "筆工單")
else:
    st.warning("⚠ 資料庫中目前沒有工單資料。")
