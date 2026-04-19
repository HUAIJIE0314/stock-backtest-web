import os  # 記得在最上面引入 os

# ==========================================
# 1. 中文字型處理 (加入嚴格的檔案檢查防呆機制)
# ==========================================
@st.cache_resource
def load_font():
    font_path = 'NotoSansTC-Regular.ttf'
    # 先檢查檔案是否真實存在於伺服器上
    if os.path.exists(font_path):
        return fm.FontProperties(fname=font_path)
    else:
        # 如果找不到檔案，在網頁上印出警告，但不要讓程式崩潰
        st.warning(f"⚠️ 找不到中文字型檔 '{font_path}'，圖表可能會出現亂碼。請確認檔案已上傳至 GitHub。")
        return None

font_prop = load_font()
if font_prop:
    plt.rcParams['font.sans-serif'] = [font_prop.get_name()]
    plt.rcParams['axes.unicode_minus'] = False