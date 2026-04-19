import streamlit as st
import yfinance as yf
import pandas as pd
import math
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm

# ==========================================
# 1. 中文字型處理 (為了讓圖表上的數字或標題正常顯示)
# ==========================================
@st.cache_resource
def load_font():
    try:
        font_path = 'NotoSansTC-Regular.ttf'
        return fm.FontProperties(fname=font_path)
    except:
        return None

font_prop = load_font()
if font_prop:
    plt.rcParams['font.sans-serif'] = [font_prop.get_name()]
    plt.rcParams['axes.unicode_minus'] = False

# ==========================================
# 2. 核心回測邏輯 (已移除 STOCK_NAMES 與中文名稱邏輯)
# ==========================================
@st.cache_data(show_spinner=False)
def calculate_lump_sum_roi_v2(tickers, start_date, end_date, investment_per_stock):
    fee_rate = 0.001425
    tax_rate = 0.003
    results = []

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
            
            split_events = {
                '00631L.TW': {'date': '2026-03-31', 'ratio': 22},
                '0052.TW':   {'date': '2025-11-26', 'ratio': 7}
            }
            if ticker in split_events:
                split_date = split_events[ticker]['date']
                split_ratio = split_events[ticker]['ratio']
                if actual_start <= split_date <= actual_end:
                    shares_bought = shares_bought * split_ratio
            
            gross_sell_value = shares_bought * current_price
            net_sell_value = gross_sell_value * (1 - fee_rate - tax_rate)
            final_value = net_sell_value + leftover_cash
            roi = ((final_value - investment_per_stock) / investment_per_stock) * 100

            total_days = (data.index[-1] - data.index[0]).days
            years = total_days / 365.25  
            annualized_roi = ((1 + roi/100)**(1/years) - 1) * 100 if years > 0 else 0
            
            # 結果只保留代號，拿掉中文名稱
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
        except Exception as e:
            st.error(f"❌ {ticker} 錯誤: {e}")

    return pd.DataFrame(results)

# ==========================================
# 3. Streamlit 網頁介面 (UI)
# ==========================================
st.set_page_config(page_title="投資回測系統", layout="wide")
st.title("📈 歷史回測分析機器人")

st.sidebar.header("回測參數設定")
capital = st.sidebar.number_input("單一標的投入本金", value=500000, step=10000)
entry_date = st.sidebar.date_input("開始日期", value=pd.to_datetime('2026-04-01'))
exit_date = st.sidebar.date_input("結束日期", value=pd.to_datetime('2026-04-19'))

# 🌟 改用文字輸入框，讓你可以隨意輸入任何 Yahoo Finance 的代號
tickers_input = st.sidebar.text_input(
    "輸入股票代號 (以逗號分隔)", 
    value="0050.TW, 2330.TW, 009816.TW, 00981A.TW, 00631L.TW"
)

if st.sidebar.button("🚀 開始回測", type="primary"):
    # 將使用者輸入的字串依逗號切分，並自動去掉多餘的空白
    selected_tickers = [t.strip() for t in tickers_input.split(',') if t.strip()]
    
    if not selected_tickers:
        st.warning("請至少輸入一檔股票代號！")
    else:
        with st.spinner('📥 正在從 Yahoo Finance 撈取歷史資料並計算中...'):
            start_str = entry_date.strftime('%Y-%m-%d')
            end_str = exit_date.strftime('%Y-%m-%d')
            
            df = calculate_lump_sum_roi_v2(selected_tickers, start_str, end_str, capital)
            
            if not df.empty:
                st.success("✅ 回測計算完成！")
                
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
                
                st.subheader("📈 各標的報酬率比較")
                fig, ax = plt.subplots(figsize=(10, 5))
                
                colors = ['#ef4444' if val < 0 else '#22c55e' for val in df['報酬率%']]
                x_labels = df['股票代號'].tolist() # X 軸直接使用代號
                
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