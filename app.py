import streamlit as st
import yfinance as yf
import pandas as pd
import math
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import os
from datetime import datetime, timedelta
import requests

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


@st.cache_data(show_spinner=False)
def get_taiwan_etn_finmind(ticker, start_date, end_date):
    url = "https://api.finmindtrade.com/api/v4/data"
    # FinMind 只吃純代號，需濾除 Yahoo Finance 的字尾 (.TW / .TWO)
    clean_ticker = ticker.upper().replace('.TW', '').replace('.TWO', '')
    parameter = {
        "dataset": "TaiwanStockPrice",
        "data_id": clean_ticker,
        "start_date": start_date,
        "end_date": end_date,
    }
    try:
        r = requests.get(url, params=parameter, timeout=10)
        data = r.json()
        if data.get('msg') == 'success' and len(data.get('data', [])) > 0:
            df = pd.DataFrame(data['data'])
            # 將 FinMind 的小寫欄位轉為首字母大寫，接軌 yfinance 格式
            df = df.rename(columns={'date': 'Date', 'close': 'Close'})
            df.set_index(pd.to_datetime(df['Date']), inplace=True)
            return df
    except Exception as e:
        pass # 靜默處理，若發生錯誤會回傳空表，交由主程式略過
        
    return pd.DataFrame()

# ==========================================
# 2. 核心回測邏輯 (新增每日報酬率計算)(雙資料源備援：yfinance + FinMind)
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
            # 階段 1：嘗試從 yfinance 撈取資料
            data = yf.download(ticker, start=start_date, end=end_date, progress=False)

            # yfinance 備援：若為空，嘗試台股字尾互換
            if data.empty:
                alt = None
                t_up = ticker.upper()
                if t_up.endswith('.TW'):
                    alt = ticker.replace('.TW', '.TWO') or ticker.replace('.tw', '.two')
                elif t_up.endswith('.TWO'):
                    alt = ticker.replace('.TWO', '.TW') or ticker.replace('.two', '.tw')
                elif '.' not in ticker:
                    alt = ticker + '.TW'

                if alt:
                    data = yf.download(alt, start=start_date, end=end_date, progress=False)
                    if not data.empty:
                        ticker = alt

            # 階段 2：若 yfinance 徹底失效 (例如 02001L 等 ETN)，啟動 FinMind 救援
            if data.empty:
                data = get_taiwan_etn_finmind(ticker, start_date, end_date)
                if data.empty:
                    # 如果雙資料源都找不到，放棄該標的
                    continue

            # --- 欄位清理與正規化 ---
            # 拍平 yfinance 特有的 MultiIndex
            if isinstance(data.columns, pd.MultiIndex):
                data.columns = [col[0] if isinstance(col, tuple) else col for col in data.columns]
            data.columns = [str(col).strip() for col in data.columns]

            price_col = 'Adj Close' if 'Adj Close' in data.columns else 'Close'
            
            # 確保有抓到價格欄位
            if price_col not in data.columns:
                continue

            # --- 後續計算邏輯保持不變 ---
            
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
                # '00631L.TW': {'date': '2026-03-31', 'ratio': 22},
                '0052.TW':   {'date': '2025-11-26', 'ratio': 7}
            }
            # 支援以不同後綴查詢分割事件（若使用者後綴為 .TWO，但 split_events 以 .TW 記錄）
            lookup_key = ticker
            split_info = split_events.get(lookup_key)
            if split_info is None:
                if lookup_key.upper().endswith('.TWO'):
                    alt_key = lookup_key[:-4] + '.TW'
                    split_info = split_events.get(alt_key)
                elif lookup_key.upper().endswith('.TW'):
                    alt_key = lookup_key[:-3] + '.TWO'
                    split_info = split_events.get(alt_key)

            if split_info:
                split_date_str = split_info['date']
                split_ratio = split_info['ratio']
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
entry_date = st.sidebar.date_input("開始日期", value=pd.to_datetime('2026-01-01'))
# exit_date = st.sidebar.date_input("結束日期", value=pd.to_datetime('2026-04-19'))
exit_date = st.sidebar.date_input("結束日期", value=datetime.today() - timedelta(days=1))

# --- 側邊欄：獨立 20 個輸入框 ---
Max_of_tickers = 20

st.sidebar.header(f"選擇股票 (最多{Max_of_tickers}檔)")
st.sidebar.markdown("*(台股直接輸入代號即可)*")

# default_tickers = ["009816", "00631L", "00991A", "00982A", "00992A", "00981A", "0050", "2330"]

# default_tickers = [
# "009816", "00631L", "0050", "2330", 
# "00991A", "00982A", "00992A", "00981A", 
# "00988A", "00947", "00990A", "00987A",
# "00708L",
# "02001L"
# ]

default_tickers = [
"00631L", "0050", "2330", 
"00991A", "00982A", "00992A", "00981A", 
"00988A", "00947", "00990A", "00987A",
"00708L",
"02001L"
]

len_of_default_tickers = len(default_tickers)
for i in range(Max_of_tickers-len_of_default_tickers):
    default_tickers.append("")

selected_tickers = []

for i in range(Max_of_tickers):
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
                
                # ==========================================
                # 【新增功能】偵測最晚上市日與資料對齊提示
                # ==========================================
                # 將所有標的的實際買入日轉為日期格式並找出最大值（最晚那一天）
                latest_start_date = pd.to_datetime(df['實際買入日']).max().strftime('%Y-%m-%d')
                
                # 如果最晚的資料起點大於使用者設定的開始日期，代表有標的時間落後、未對齊
                if latest_start_date > start_str:
                    st.warning(
                        f"⚠️ **注意：資料時間未完全對齊！**\n\n"
                        f"您設定的開始日期為 **{start_str}**，但測試標的中含有全新上市或近期掛牌的商品。\n\n"
                        f"目前所有標的中，**最晚的資料起點（上市/有數據日）為：{latest_start_date}**。部分商品的早期累積報酬率可能因此無法呈現或比較。"
                    )
                else:
                    st.info(f"💡 目前所有測試標的之資料皆成功自設定起點 `{start_str}` 開始對齊計算。")
                # ==========================================

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
                # 【新增修改 1】：將 DataFrame 依照 '報酬率%' 進行排序 
                # ascending=True 代表由低到高排序 (若想由高到低，請改為 False)
                df_sorted = df.sort_values(by='報酬率%', ascending=True)
                
                # 【新增修改 2】：將回測的起始與結束時間加入標題字串中
                st.subheader(f"📊 各標的最終報酬率比較 ({start_str} ~ {end_str})")
                
                fig, ax = plt.subplots(figsize=(10, 5))
                
                # 注意：這裡的顏色判定與 X 軸標籤，都要改從「排序後」的 df_sorted 取值
                # colors = ['#ef4444' if val < 0 else '#22c55e' for val in df_sorted['報酬率%']]

                # 虧損 (< 0) 顯示綠色，獲利 (>= 0) 顯示紅色
                colors = ['#22c55e' if val < 0 else '#ef4444' for val in df_sorted['報酬率%']]

                x_labels = df_sorted['股票代號'].tolist()
                
                # 繪製長條圖 (同樣改用 df_sorted['報酬率%'])
                bars = ax.bar(x_labels, df_sorted['報酬率%'], color=colors, edgecolor='black', alpha=0.7)
                
                # 【新增這兩行】：設定 X 軸刻度並將標籤旋轉 45 度，對齊右側
                ax.set_xticks(range(len(x_labels)))
                ax.set_xticklabels(x_labels, rotation=45, ha='right', fontproperties=font_prop)

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
