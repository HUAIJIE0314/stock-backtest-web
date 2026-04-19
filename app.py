import streamlit as st
import yfinance as yf
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm

# --- 1. 中文字型處理 (針對雲端環境優化) ---
@st.cache_resource
def load_font():
    # 下載 NotoSansTC-Regular.ttf 放在同目錄下
    font_path = 'NotoSansTC-Regular.ttf'
    return fm.FontProperties(fname=font_path)

font_prop = load_font()

# --- 2. 側邊欄設定 (互動輸入) ---
st.sidebar.title("📈 回測參數設定")
capital = st.sidebar.number_input("投入總本金", value=500000, step=10000)
entry_date = st.sidebar.date_input("開始日期", value=pd.to_datetime('2026-04-01'))
exit_date = st.sidebar.date_input("結束日期", value=pd.to_datetime('2026-04-19'))

# 選擇標的 (從你原本的 STOCK_NAMES 挑選)
selected_tickers = st.sidebar.multiselect(
    "選擇投資組合", 
    options=list(STOCK_NAMES.keys()),
    default=['0050.TW', '2330.TW']
)

# --- 3. 執行按鈕 ---
if st.sidebar.button("開始回測"):
    with st.spinner('資料撈取中...'):
        # 呼叫你原本的 calculate_lump_sum_roi_v2 邏輯
        df = calculate_lump_sum_roi_v2(selected_tickers, entry_date, exit_date, capital)
        
        if not df.empty:
            st.success("回測完成！")
            
            # 顯示表格
            st.subheader("📊 回測明細")
            st.dataframe(df.style.format(subset=['報酬率%', '年化報酬率%'], formatter="{:.2f}%"))
            
            # 顯示圖表
            fig, ax = plt.subplots()
            # 繪圖邏輯... (記得在 title/label 加上 fontproperties=font_prop)
            ax.set_title("各標的報酬率", fontproperties=font_prop)
            st.pyplot(fig)