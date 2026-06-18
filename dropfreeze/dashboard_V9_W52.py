import streamlit as st
import pandas as pd
import sqlite3
from pathlib import Path
from streamlit_autorefresh import st_autorefresh
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
import matplotlib
from matplotlib.colors import LinearSegmentedColormap
import streamlit.components.v1 as components
import numpy as np

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
    if pd.isna(val):
        return None

    s = str(val).strip()
    if not s or s.upper() in ("NULL", "NONE", "NAN"):
        return None

    # 民國年 (例如 113/01/03)
    try:
        if "/" in s:
            parts = s.split()
            date_part = parts[0]
            ymd = date_part.split("/")
            if len(ymd[0]) <= 3:  # 民國年
                y = int(ymd[0]) + 1911
                m = int(ymd[1])
                d = int(ymd[2])
                time_part = parts[1] if len(parts) > 1 else "00:00:00"
                return pd.to_datetime(f"{y}-{m:02d}-{d:02d} {time_part}", errors="coerce")
    except:
        pass

    # 一般 datetime
    try:
        return pd.to_datetime(s, errors="coerce")
    except:
        return None


def preprocess_data(df):
    if df.empty:
        return df

    df = df.copy()

    # 解析時間欄位
    for col in TIME_COLS:
        if col in df.columns:
            df[col] = df[col].apply(safe_parse_datetime)

    # 日期來源（優先 日期，其次 收藥時間）
    df["日期_原始_parsed"] = df["日期"].apply(safe_parse_datetime)
    df["時間_收藥_parsed"] = df["時間_收藥"].apply(safe_parse_datetime)

    df["日期_parsed"] = df.apply(
        lambda r: r["日期_原始_parsed"]
        if pd.notna(r["日期_原始_parsed"])
        else r["時間_收藥_parsed"],
        axis=1
    )

    # ⚠️ 關鍵：這裡「不要刪掉 NaT」
    # df = df[df["日期_parsed"].notna()] ❌（已移除）

    # 數量轉型
    df["製令數量"] = pd.to_numeric(df["製令數量"], errors="coerce")

    # 進度計算
    prog = df.apply(
        lambda r: pd.Series(get_progress_info(r, TIME_COLS, STATION_NAMES)),
        axis=1
    )
    df[["進度階段", "目前工站"]] = prog
    df["進度百分比"] = (df["進度階段"] / len(TIME_COLS) * 100).astype(int)

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
# --- 4. Sidebar (修正版) ---
def setup_sidebar(df):
    st.sidebar.header("🔎 功能選單")
    
    # 初始化 session state
    if 'show_statistics' not in st.session_state:
        st.session_state.show_statistics = False
    if 'stat_period' not in st.session_state:
        st.session_state.stat_period = 'week'
    
    # 統計按鈕區
    col1, col2 = st.sidebar.columns(2)
    with col1:
        if st.button("📈 統計", use_container_width=True, 
                     type="primary" if st.session_state.show_statistics else "secondary"):
            st.session_state.show_statistics = True
    with col2:
        if st.button("📋 工單", use_container_width=True, 
                     type="primary" if not st.session_state.show_statistics else "secondary"):
            st.session_state.show_statistics = False
    
    # 如果在統計模式，顯示週期選擇
    if st.session_state.show_statistics:
        st.sidebar.markdown("---")
        st.sidebar.markdown("### ⚙️ 統計設定")
        st.session_state.stat_period = st.sidebar.selectbox(
            "統計週期",
            options=['week', 'month', 'quarter', 'year'],
            format_func=lambda x: {'week': '週統計', 'month': '月統計', 'quarter': '季統計', 'year': '年統計'}[x],
            key='period_select'
        )
        st.sidebar.info("📈 顯示生產次數最多的前 24 種 Beads")
        return df
    
    # 工單篩選區
    st.sidebar.markdown("---")
    st.sidebar.markdown("### 🔍 工單篩選")
    st.sidebar.info(f"📊 總筆數: {len(df)}")
    
    wo_input = st.sidebar.text_input("工單號")
    bn_input = st.sidebar.text_input("Bead Name")
    
    if df.empty or "日期_parsed" not in df.columns: return df
    
    # --- 🔥 重點修正：日期錨點邏輯 ---
    valid_dates = df["日期_parsed"].dropna()
    today = datetime.today().date()
    
    if valid_dates.empty:
        # 沒資料時的 Fallback
        d_min, d_max = today, today
        default_start, default_end = today, today
    else:
        d_min = valid_dates.min().date()
        d_max = valid_dates.max().date() # 資料庫裡真正的最後一天 (例如 2026-01-05)
        
        # [核心修正] 
        # 預設結束日：直接鎖定「資料庫的最後一天」，確保一定看得到最新的單
        default_end = d_max  
        
        # 預設開始日：資料最後一天往前推 7 天
        default_start = default_end - timedelta(days=7)

    # Date Picker 的最大值 (max_value)：
    # 取 (今天, 資料最後一天) 的最大值
    # 這樣如果資料庫有 2026-01-05，選單就能選到那裡
    picker_max = max(today, d_max)

    dates = st.sidebar.date_input(
        "日期區間",
        value=[default_start, default_end], # 預設值
        min_value=d_min,
        max_value=picker_max                # 可選範圍
    )
    
    if len(dates) == 2:
        s, e = dates
        # 包含結束日當天的整整 24 小時
        edt = pd.to_datetime(e) + timedelta(days=1) - timedelta(seconds=1)
        filtered = df[(df["日期_parsed"] >= pd.to_datetime(s)) & (df["日期_parsed"] <= edt)].copy()
    else:
        filtered = df.copy()
        
    if wo_input: filtered = filtered[filtered["工單號"].astype(str).str.contains(wo_input.strip(), case=False, na=False)]
    if bn_input: filtered = filtered[filtered["bead_name"].astype(str).str.contains(bn_input.strip(), case=False, na=False)]
    if st.sidebar.checkbox("只顯示未完成"): filtered = filtered[filtered["進度百分比"] < 100]
    
    return filtered.sort_values(by=["日期_parsed", "進度百分比"], ascending=[False, True])

# --- 5. 生產統計熱力圖 (純 matplotlib 版本) ---
def get_week_number(dt):
    """取得週數 (ISO week)"""
    return dt.isocalendar()[1]

def get_quarter(dt):
    """取得季度"""
    return f"Q{(dt.month - 1) // 3 + 1}"

def plot_production_heatmap(df, period='week'):
    """
    繪製生產統計熱力圖 (使用純 matplotlib)
    period: 'week', 'month', 'quarter', 'year'
    """
    if df.empty or "日期_parsed" not in df.columns:
        st.warning("無資料可供統計")
        return
    
    # 準備資料
    stats_df = df[df["日期_parsed"].notna()].copy()
    
    # 根據週期分組
    if period == 'week':
        stats_df['period'] = stats_df['日期_parsed'].apply(
            lambda x: f"{x.year}-W{get_week_number(x):02d}"
        )
        title = "週生產統計 (Top 24 Beads)"
        xlabel = "週別"
    elif period == 'month':
        stats_df['period'] = stats_df['日期_parsed'].dt.to_period('M').astype(str)
        title = "月生產統計 (Top 24 Beads)"
        xlabel = "月份"
    elif period == 'quarter':
        stats_df['period'] = stats_df['日期_parsed'].apply(
            lambda x: f"{x.year}-{get_quarter(x)}"
        )
        title = "季生產統計 (Top 24 Beads)"
        xlabel = "季度"
    else:  # year
        stats_df['period'] = stats_df['日期_parsed'].dt.year.astype(str)
        title = "年生產統計 (Top 24 Beads)"
        xlabel = "年份"
    
    # 計算各 bead 在各時期的生產次數
    pivot_data = stats_df.groupby(['bead_name', 'period']).size().reset_index(name='count')
    
    # 取得 Top 24 beads (總生產次數最多的24種)
    top_beads = (
        pivot_data.groupby('bead_name')['count']
        .sum()
        .sort_values(ascending=False)
        .head(24)
        .index.tolist()
    )
    
    if not top_beads:
        st.warning("無足夠資料繪製熱力圖")
        return
    
    # 篩選 top beads
    pivot_data = pivot_data[pivot_data['bead_name'].isin(top_beads)]
    
    # 建立 pivot table
    heatmap_data = pivot_data.pivot(index='bead_name', columns='period', values='count')
    heatmap_data = heatmap_data.fillna(0)
    
    # 依照總生產次數排序 (由多到少)
    row_sums = heatmap_data.sum(axis=1).sort_values(ascending=False)
    heatmap_data = heatmap_data.reindex(row_sums.index)
    
    # 繪製熱力圖 (使用 matplotlib)
    # 大幅縮小尺寸
    fig_width = max(6, len(heatmap_data.columns) * 0.4) * 0.65
    fig_height = max(4, len(heatmap_data) * 0.2) * 0.65
    fig, ax = plt.subplots(figsize=(fig_width, fig_height))
    
    # 創建自定義 colormap (YlOrRd 風格)
    colors = ['#FFFFCC', '#FFEDA0', '#FED976', '#FEB24C', '#FD8D3C', '#FC4E2A', '#E31A1C', '#BD0026', '#800026']
    n_bins = 256
    cmap = LinearSegmentedColormap.from_list('YlOrRd', colors, N=n_bins)
    
    # 繪製熱力圖
    im = ax.imshow(heatmap_data.values, cmap=cmap, aspect='auto')
    
    # 設定刻度
    ax.set_xticks(np.arange(len(heatmap_data.columns)))
    ax.set_yticks(np.arange(len(heatmap_data.index)))
    ax.set_xticklabels(heatmap_data.columns, fontsize=6)
    ax.set_yticklabels(heatmap_data.index, fontsize=7)
    
    # 旋轉 x 軸標籤
    plt.setp(ax.get_xticklabels(), rotation=45, ha="right", rotation_mode="anchor")
    
    # 添加數值標註（縮小字體）
    for i in range(len(heatmap_data.index)):
        for j in range(len(heatmap_data.columns)):
            value = heatmap_data.values[i, j]
            if value > 0:
                text = ax.text(j, i, int(value),
                             ha="center", va="center", color="black" if value < heatmap_data.values.max() * 0.5 else "white",
                             fontsize=6, fontweight='bold')
    
    # 不顯示 colorbar
    
    # 添加網格線
    ax.set_xticks(np.arange(len(heatmap_data.columns)) - 0.5, minor=True)
    ax.set_yticks(np.arange(len(heatmap_data.index)) - 0.5, minor=True)
    ax.grid(which="minor", color="gray", linestyle='-', linewidth=0.3)
    
    # 設定標題和標籤（縮小字體）
    ax.set_title(title, fontsize=11, fontweight='bold', pad=10)
    ax.set_xlabel(xlabel, fontsize=9, fontweight='bold')
    ax.set_ylabel('Bead Name', fontsize=9, fontweight='bold')
    
    # 調整布局，增加左側空間，右側不需要留給 colorbar
    plt.subplots_adjust(left=0.25, right=0.98, top=0.93, bottom=0.15)
    st.pyplot(fig)
    plt.close()

def show_production_statistics(df, period='week'):
    """顯示生產統計 Heatmap"""
    st.header("📊 生產統計分析")
    
    # 週期名稱對照
    period_names = {
        'week': '週統計', 
        'month': '月統計', 
        'quarter': '季統計', 
        'year': '年統計'
    }
    st.info(f"📈 顯示生產次數最多的前 24 種 Beads - {period_names[period]}")
    
    # 繪製熱力圖
    plot_production_heatmap(df, period=period)

# --- 6. 顯示邏輯 ---

def display_dashboard(filtered_df):
    # 開始渲染工單
    for _, row in filtered_df.iterrows():
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
                                                    
                                                    # 3. 使用 on_click=show_photo_modal 並透過 args 鎖定變數
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

# --- 7. 執行 ---
def main():
    try:
        raw_df = load_data()
        if raw_df.empty:
            st.warning("⚠ 無資料")
            return
        df = preprocess_data(raw_df)
        final_df = setup_sidebar(df)
        
        # 根據 session_state 決定顯示內容
        if st.session_state.get('show_statistics', False):
            # 顯示生產統計
            if not df.empty:
                show_production_statistics(df, period=st.session_state.get('stat_period', 'week'))
            else:
                st.warning("⚠️ 無資料可供統計")
        else:
            # 顯示工單追蹤
            if final_df.empty:
                st.info("ℹ️ 無符合工單")
            else:
                display_dashboard(final_df)
            
    except Exception as e:
        st.error(f"Error: {e}")
        import traceback
        st.code(traceback.format_exc())

if __name__ == "__main__":
    main()