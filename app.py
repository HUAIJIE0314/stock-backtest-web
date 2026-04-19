import streamlit as st
import yfinance as yf
import pandas as pd
import math
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import os

# ==========================================
# 1. 中文字型處理 (加入嚴格的檔案檢查防呆機制)
# ==========================================
@st.cache_resource
def load_font():
    font_path = 'NotoSansTC-Regular.ttf'
    if os.path.exists(font_path):
        return fm.FontProperties(fname=font_path)
    else:
        st.warning(f"⚠️ 找不到中文字型檔 '{font_path}'，圖表可能會出現亂碼。請確認檔案已上傳至 GitHub。")
        return None

font_prop = load_font()
if font_prop:
    plt.rcParams['font.sans-serif'] = [font_prop.get_name()]
    plt.rcParams['axes.unicode_minus'] = False

# ==========================================
# 2. 核心回測邏輯 (新增每日報酬率計算)
# ==========================================
@st.cache_data(show_spinner=False)
def calculate_lump_sum_roi_v2(tickers, start_date, end_date, investment_per_stock):
    fee_rate = 0.001425
    tax_rate = 0.003
    results = []
    daily_returns_dict = {} # 用來收集每天的報酬率資料

    for ticker in tickers:
        if not ticker: continue
        try:
            data = yf.download(ticker, start=start_date, end=end_date, progress=False)
            if data.empty: continue

            if isinstance(data.columns, pd.MultiIndex):
                data.columns = data.columns.get_level_values(0)

            price_col = 'Adj Close' if 'Adj Close' in data.columns else 'Close'
            
            initial_price = float(data[price_col].iloc[0])
            current_price = float(data[price_col].iloc[-1])
            actual_start = data.index[0].strftime('%Y-%m-%d')
            actual_end = data.index[-1].strftime('%Y-%m-%d')

            cost_per_share = initial_price * (1 + fee_rate)
            shares_bought = math.floor(investment_per_stock / cost_per_share)
            buy_cost = shares_bought * initial_price * (1 + fee_rate)
            leftover_cash = investment_per_stock - buy_cost
            
            # 複製一份每日價格來計算曲線
            daily_prices = data[price_col].copy()
            
            # --- 股票分割校正邏輯 ---
            split_events = {
                '00631L.TW': {'date': '2026-03-31', 'ratio': 22},
                '0052.TW':   {'date': '2025-11-26', 'ratio': 7}
            }
            if ticker in split_events:
                split_date_str = split_events[ticker]['date']
                split_ratio = split_events[ticker]['ratio']
                if actual_start <= split_date_str <= actual_end:
                    shares_bought = shares_bought * split_ratio
                    # 為了讓走勢圖平滑，分割日(含)之後的價格乘上比例，還原真實走勢
                    split_datetime = pd.to_datetime(split_date_str)
                    daily_prices[daily_prices.index >= split_datetime] *= split_ratio
            
            gross_sell_value = shares_bought * current_price
            net_sell_value = gross_sell_value * (1 - fee_rate - tax_rate)
            final_value = net_sell_value + leftover_cash
            roi = ((final_value - investment_per_stock) / investment_per_stock) * 100

            total_days = (data.index[-1] - data.index[0]).days
            years = total_days / 365.25  
            annualized_roi = ((1 + roi/100)**(1/years) - 1) * 100 if years > 0 else 0
            
            # 紀錄單次結算總表
            results.append({
                '股票代號': ticker,
                '實際買入日': actual_start,
                '實際結算日': actual_end,
                '買入價': round(initial_price, 2),
                '結算價': round(current_price, 2),
                '股數': shares_bought,
                '投入本金': round(buy_cost, 0),
                '結算價值': round(final_value, 0),
                '報酬率%': round(roi, 2),
                '年化報酬率%': round(annualized_roi, 2)
            })
            
            # 計算每日累積報酬率 (%) 並存入字典
            daily_roi = (daily_prices / initial_price - 1) * 100
            daily_returns_dict[ticker] = daily_roi

        except Exception as e:
            st.error(f"❌ {ticker} 錯誤: {e}")

    # 將每日報酬率轉換為 DataFrame，並填補可能因不同標的休市導致的缺失值
    daily_returns_df = pd.DataFrame(daily_returns_dict).ffill()
    
    return pd.DataFrame(results), daily_returns_df

# ==========================================
# 3. Streamlit 網頁介面 (UI)
# ==========================================
st.set_page_config(page_title="投資回測系統", layout="wide")
st.title("📈 歷史回測分析機器人")

# --- 側邊欄：參數設定 ---
st.sidebar.header("回測參數設定")
capital = st.sidebar.number_input("單一標的投入本金", value=500000, step=10000)
entry_date = st.sidebar.date_input("開始日期", value=pd.to_datetime('2025-06-01'))
exit_date = st.sidebar.date_input("結束日期", value=pd.to_datetime('2026-04-01'))

# --- 側邊欄：獨立 6 個輸入框 ---
st.sidebar.header("選擇股票 (最多6檔)")
st.sidebar.markdown("*(台股直接輸入代號即可)*")

default_tickers = ["0050", "2330", "00631L", "00981A", "", ""]
selected_tickers = []

for i in range(6):
    val = st.sidebar.text_input(f"標的 {i+1}", value=default_tickers[i])
    val = val.strip().upper() # 移除空白並轉大寫
    
    if val:
        # 如果使用者沒有輸入小數點(.)，自動補上 .TW 成為台股代號
        if '.' not in val:
            val += '.TW'
        
        # 避免重複輸入相同的標的
        if val not in selected_tickers:
            selected_tickers.append(val)

# --- 執行按鈕 ---
if st.sidebar.button("🚀 開始回測", type="primary"):
    
    if not selected_tickers:
        st.warning("請至少輸入一檔股票代號！")
    else:
        with st.spinner('📥 正在從 Yahoo Finance 撈取歷史資料並計算中...'):
            start_str = entry_date.strftime('%Y-%m-%d')
            end_str = exit_date.strftime('%Y-%m-%d')
            
            # 取得回測總表與每日走勢資料
            df, daily_returns_df = calculate_lump_sum_roi_v2(selected_tickers, start_str, end_str, capital)
            
            if not df.empty:
                st.success("✅ 回測計算完成！")
                
                # --- 區塊 1：動態折線圖 (歷史走勢) ---
                st.subheader("📈 歷史累積報酬率走勢 (%)")
                st.line_chart(daily_returns_df)
                
                # --- 區塊 2：明細數據表 ---
                st.subheader("📊 回測明細")
                st.dataframe(
                    df.style.format({
                        '買入價': '{:.2f}',
                        '結算價': '{:.2f}',
                        '股數': '{:,}',
                        '投入本金': '{:,.0f}',
                        '結算價值': '{:,.0f}',
                        '報酬率%': '{:.2f}%',
                        '年化報酬率%': '{:.2f}%'
                    }),
                    use_container_width=True
                )
                
                # --- 區塊 3：總結長條圖 ---
                st.subheader("📊 各標的最終報酬率比較")
                fig, ax = plt.subplots(figsize=(10, 5))
                
                colors = ['#ef4444' if val < 0 else '#22c55e' for val in df['報酬率%']]
                x_labels = df['股票代號'].tolist()
                
                bars = ax.bar(x_labels, df['報酬率%'], color=colors, edgecolor='black', alpha=0.7)
                
                for bar in bars:
                    height = bar.get_height()
                    ax.text(bar.get_x() + bar.get_width()/2., height, f'{height:.1f}%', 
                            ha='center', va='bottom' if height > 0 else 'top', fontweight='bold',
                            fontproperties=font_prop if font_prop else None)

                ax.axhline(0, color='black', linewidth=0.8)
                ax.grid(axis='y', linestyle='--', alpha=0.5)
                
                st.pyplot(fig)
            else:
                st.error("無法取得資料，請確認日期區間是否為交易日，或標的代號是否正確。")
