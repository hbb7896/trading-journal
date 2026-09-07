import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import FinanceDataReader as fdr
import altair as alt
from datetime import datetime, timedelta
import random
import json
import re
import google.generativeai as genai
from PIL import Image
import gspread
from google.oauth2.service_account import Credentials

# 1. 페이지 설정
st.set_page_config(page_title="Trading Master Dashboard", page_icon="💎", layout="wide")

# 2. 구글 시트 직접 연결 (gspread 다이렉트 우회로 적용)
@st.cache_resource
def get_gspread_client():
    try:
        scope = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        gcp_cred = json.loads(st.secrets["google_json"])
        creds = Credentials.from_service_account_info(gcp_cred, scopes=scope)
        client = gspread.authorize(creds)
        sheet_url = st.secrets["sheet_url"]
        doc = client.open_by_url(sheet_url)
        return doc
    except Exception as e:
        st.error(f"🚨 구글 시트 직접 연결 오류: {e}")
        return None

doc = get_gspread_client()

if doc is None:
    st.stop()

# 시트 데이터 읽어오는 헬퍼 함수
def read_sheet_data(worksheet_idx):
    try:
        ws = doc.get_worksheet(worksheet_idx)
        data = ws.get_all_records()
        return pd.DataFrame(data)
    except Exception:
        return pd.DataFrame()

def update_sheet_data(worksheet_idx, df):
    try:
        ws = doc.get_worksheet(worksheet_idx)
        ws.clear()
        ws.update([df.columns.values.tolist()] + df.values.tolist())
    except Exception as e:
        st.error(f"시트 업데이트 실패: {e}")

# --- 설정값 & 상태 영구 저장/불러오기 ---
def load_status():
    try:
        df_config = read_sheet_data(1)
        if df_config.empty:
            return 20000000, 5000000, [] 
        row = df_config.iloc[0]
        equity = int(row.get('Total_Equity', 20000000))
        max_pos = int(row.get('Max_Position', 5000000))
        history_str = str(row.get('History', ''))
        if history_str and history_str != 'nan': history = history_str.split(',')
        else: history = []
        return equity, max_pos, history
    except Exception:
        return 20000000, 5000000, []

def save_status(equity, max_pos, history):
    try:
        history_str = ",".join(history)
        df_config = read_sheet_data(1)
        if not df_config.empty:
            new_df = df_config.copy()
            new_df.at[0, 'Total_Equity'] = equity
            new_df.at[0, 'Max_Position'] = max_pos
            new_df.at[0, 'History'] = history_str
        else:
            new_df = pd.DataFrame([{'Total_Equity': equity, 'Max_Position': max_pos, 'History': history_str}])
        update_sheet_data(1, new_df)
    except Exception as e:
        st.error(f"저장 실패: {e}")

@st.cache_data(ttl=0)
def load_settings():
    try:
        df = read_sheet_data(1)
        if not df.empty: return df.iloc[0].to_dict()
    except: pass
    return {}

saved_config = load_settings()

@st.cache_data(ttl=3600)
def get_krx_list():
    try:
        df = fdr.StockListing('KRX')
        return df[['Code', 'Name', 'Market']]
    except Exception as e:
        return pd.DataFrame()

REQUIRED_COLUMNS = [
    'Date', 'Ticker', 'Buy_Amount', 'Sell_Amount', 'P_L_Amount', 
    'ROI_Percent', 'Mistake_Tags', 'Emotion', 'Discipline', 'Memo'
]

def load_data():
    try:
        df = read_sheet_data(0)
        if df.empty: return pd.DataFrame(columns=REQUIRED_COLUMNS)
        df = df.dropna(subset=['Date'])
        
        num_cols = ['P_L_Amount', 'ROI_Percent', 'Buy_Amount', 'Sell_Amount']
        for col in num_cols:
            if col in df.columns:
                df[col] = df[col].astype(str).str.replace(',', '').str.replace('%', '')
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        
        df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
        if 'Buy_Amount' not in df.columns: df['Buy_Amount'] = 0.0
        if 'Sell_Amount' not in df.columns: df['Sell_Amount'] = 0.0
        
        mask = (df['Buy_Amount'] == 0) & (df['ROI_Percent'] != 0)
        df.loc[mask, 'Buy_Amount'] = (df.loc[mask, 'P_L_Amount'] / (df.loc[mask, 'ROI_Percent'] / 100)).abs()
        df.loc[mask, 'Sell_Amount'] = df.loc[mask, 'Buy_Amount'] + df.loc[mask, 'P_L_Amount']

        for col in ['Mistake_Tags', 'Emotion', 'Discipline', 'Memo']:
            if col not in df.columns: df[col] = None
        return df
    except:
        return pd.DataFrame(columns=REQUIRED_COLUMNS)

df = load_data()
krx_list = get_krx_list() 

# ==========================================
# 사이드바: AI 영수증 캡쳐 분석 모듈
# ==========================================
st.sidebar.header("📸 AI 영수증 자동 입력")
with st.sidebar.expander("🤖 캡쳐 화면 올리기", expanded=False):
    st.markdown("수익/손실 화면을 올리면 알아서 타이핑해드립니다.")
    api_key = st.text_input("Gemini API Key (최초 1회 입력)", type="password", key="sidebar_api")
    uploaded_file = st.file_uploader("증권사 캡쳐 이미지", type=['png', 'jpg', 'jpeg'], key="sidebar_uploader")
    
    if st.button("🔍 데이터 추출하기", use_container_width=True):
        if not api_key:
            st.error("Gemini API Key가 필요합니다.")
        elif not uploaded_file:
            st.error("이미지를 올려주세요.")
        else:
            with st.spinner("김 프로가 캡쳐를 분석 중입니다..."):
                try:
                    clean_api_key = api_key.strip()
                    genai.configure(api_key=clean_api_key)
                    model = genai.GenerativeModel('gemini-2.5-flash')
                    
                    img = Image.open(uploaded_file)
                    if img.mode != 'RGB':
                        img = img.convert('RGB')
                    img.thumbnail((800, 800)) 
                    
                    prompt = """
                    당신은 한국 주식 증권사 앱의 캡쳐 화면을 분석하는 최고 수준의 AI 트레이딩 보조입니다.
                    이미지에서 다음 3가지 데이터를 반드시 추출하세요.
                    1. 종목명 (예: 두산퓨얼셀)
                    2. 매수금액 (콤마(,)를 모두 제거한 순수 숫자만. 예: 2991450)
                    3. 수익률(%) (콤마(,) 및 % 기호를 제거한 순수 숫자만. 예: 0.04)

                    [중요 규칙 - 수익률이 없을 때]
                    화면에 '수익률(%)'이 직접 적혀있지 않고 '손익금액'과 '매수금액'만 있다면, 당신이 직접 수익률을 계산하세요!
                    * 계산식: (손익금액 / 매수금액) * 100
                    * 소수점 셋째 자리에서 반올림하여 둘째 자리까지만 출력하세요.
                    
                    결과는 반드시 아래 JSON 형식으로만 출력하세요. 다른 설명은 절대 추가하지 마세요.
                    {"ticker": "두산퓨얼셀", "buy_amount": 2991450, "roi": 0.04, "memo": "AI 스캔 완료"}
                    """
                    response = model.generate_content([prompt, img])
                    
                    if not response.parts:
                        st.error("🚨 AI가 응답을 반환하지 않았습니다.")
                    else:
                        result_text = response.text.strip()
                        match = re.search(r'\{.*\}', result_text, re.DOTALL)
                        if match: clean_json = match.group(0)
                        else: clean_json = result_text 
                            
                        data = json.loads(clean_json)
                        st.session_state.ai_ticker = data.get('ticker', '')
                        buy_amt_raw = str(data.get('buy_amount', 0)).replace(',', '')
                        st.session_state.ai_buy_amt = int(float(buy_amt_raw))
                        roi_raw = str(data.get('roi', 0.0)).replace(',', '').replace('%', '')
                        st.session_state.ai_roi = float(roi_raw)
                        st.session_state.ai_memo = data.get('memo', '📸 AI 분석 자동 입력')
                        
                        if 'form_reset_trigger' not in st.session_state:
                            st.session_state.form_reset_trigger = 0
                        st.session_state.form_reset_trigger += 1
                        st.success("✅ 분석 성공! 아래 폼에 입력되었습니다.")
                except Exception as e:
                    st.error(f"🚨 해독 실패: {e}")

if 'form_reset_trigger' not in st.session_state:
    st.session_state.form_reset_trigger = 0
    
def_ticker = st.session_state.get('ai_ticker', '')
def_buy_amt = int(st.session_state.get('ai_buy_amt', 0))
def_roi = float(st.session_state.get('ai_roi', 0.0))
def_memo = st.session_state.get('ai_memo', '')
fc = st.session_state.form_reset_trigger

# --- 사이드바 입력 ---
st.sidebar.markdown("---")
st.sidebar.header("📝 매매 기록 입력")
with st.sidebar.form("quick_input", clear_on_submit=True):
    date = st.date_input("일자", datetime.today())
    ticker = st.text_input("종목명 (예: 삼성전자)", value=def_ticker, key=f"t_{fc}").strip()
    st.markdown("---")
    buy_amt = st.number_input("총 매수 금액 (원)", value=def_buy_amt, step=100000, key=f"b_{fc}")
    roi = st.number_input("수익률 (%)", value=def_roi, format="%.2f", key=f"r_{fc}")
    
    sell_amt = 0.0
    pn_l = 0.0
    if buy_amt != 0:
        pn_l = buy_amt * (roi / 100)
        sell_amt = buy_amt + pn_l
        st.info(f"""
        🧮 **자동 계산 결과**
        - 수익금: {pn_l:,.0f}원
        - 매도금액: {sell_amt:,.0f}원
        """)

    st.markdown("---")
    memo = st.text_input("메모 (특이사항 등)", value=def_memo, key=f"m_{fc}")
    
    if st.form_submit_button("기록 저장"):
        if ticker:
            with st.spinner("안전하게 저장 중입니다... 🛡️"):
                try:
                    new_data = pd.DataFrame([{
                        'Date': date.strftime('%Y-%m-%d'), 
                        'Ticker': ticker, 
                        'Buy_Amount': buy_amt, 
                        'Sell_Amount': sell_amt,
                        'P_L_Amount': pn_l, 
                        'ROI_Percent': roi, 
                        'Mistake_Tags': None,
                        'Emotion': None,
                        'Discipline': None,
                        'Memo': memo
                    }])
                    
                    live_df = read_sheet_data(0)
                    if live_df.empty and not df.empty:
                        safe_df = df.copy() 
                        safe_df['Date'] = pd.to_datetime(safe_df['Date']).dt.strftime('%Y-%m-%d')
                        updated_df = pd.concat([safe_df, new_data], ignore_index=True)
                    elif not live_df.empty:
                        live_df['Date'] = pd.to_datetime(live_df['Date']).dt.strftime('%Y-%m-%d')
                        updated_df = pd.concat([live_df, new_data], ignore_index=True)
                    else:
                        updated_df = new_data
                        
                    update_sheet_data(0, updated_df)
                    
                    if 'ai_ticker' in st.session_state:
                        st.session_state.ai_ticker = ""
                        st.session_state.ai_buy_amt = 0
                        st.session_state.ai_roi = 0.0
                        st.session_state.ai_memo = ""
                        
                    st.success(f"✅ {ticker} 완벽하게 저장 완료!")
                    st.rerun()
                except Exception as e:
                    st.error(f"🚨 저장 실패: {e}")
        else: 
            st.error("종목명을 입력해주세요.")

# --- 메인 화면 ---
st.title("💎 Trading Master Dashboard")

if not df.empty:
    def color_profit_loss(val):
        try:
            if pd.isna(val): return ''
            if float(val) > 0: return 'color: #FF4444; font-weight: bold;'
            elif float(val) < 0: return 'color: #0066CC; font-weight: bold;'
        except: pass
        return ''

    tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
        "📊 차트", "📅 월별", "📆 연도별", "📋 원본", 
        "⚖️ 빅터 스페란데오", "🎯 R-배수 분석", "🔔 손익 분포"
    ])
    
    df['Year'] = df['Date'].dt.year
    df['YearMonth'] = df['Date'].dt.strftime('%Y-%m')
    
    total_trades = len(df)
    wins = df[df['ROI_Percent'] > 0]
    losses = df[df['ROI_Percent'] <= 0]
    win_rate = (len(wins) / total_trades) * 100 if total_trades > 0 else 0
    avg_win = wins['ROI_Percent'].mean() if not wins.empty else 0
    avg_loss = abs(losses['ROI_Percent'].mean()) if not losses.empty else 0
    avg_roi = df['ROI_Percent'].mean()

    with tab1:
        st.subheader("🏆 전체 종합 성적표 (Total Legend)")
        total_pl = df['P_L_Amount'].sum()
        total_cnt = len(df)
        all_wins = df[df['ROI_Percent'] > 0]
        all_losses = df[df['ROI_Percent'] <= 0]
        
        gross_p = all_wins['P_L_Amount'].sum()
        gross_l = abs(all_losses['P_L_Amount'].sum())
        total_pf = gross_p / gross_l if gross_l > 0 else 0
        
        all_avg_profit_amt = all_wins['P_L_Amount'].mean() if not all_wins.empty else 0
        all_avg_loss_amt = abs(all_losses['P_L_Amount'].mean()) if not all_losses.empty else 0
        money_rr_ratio = all_avg_profit_amt / all_avg_loss_amt if all_avg_loss_amt > 0 else 0
        
        all_avg_profit_pct = all_wins['ROI_Percent'].mean() if not all_wins.empty else 0
        all_avg_loss_pct = abs(all_losses['ROI_Percent'].mean()) if not all_losses.empty else 0
        period_rr_ratio = all_avg_profit_pct / all_avg_loss_pct if all_avg_loss_pct > 0 else 0
        
        win_prob = (len(all_wins) / total_cnt) if total_cnt > 0 else 0
        loss_prob = 1 - win_prob
        expectancy = (win_prob * all_avg_profit_pct) - (loss_prob * all_avg_loss_pct)

        if money_rr_ratio > 0:
            kelly_fraction = win_prob - (loss_prob / money_rr_ratio)
            kelly_pct = max(0.0, kelly_fraction * 100) 
        else:
            kelly_pct = 0.0
            
        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("💰 누적 총 손익", f"{total_pl:,.0f}원")
        m2.metric("🎯 전체 승률", f"{win_rate:.1f}%")
        m3.metric("🔮 기간 기댓값", f"{expectancy:.2f}%")
        m4.metric("💎 Profit Factor", f"{total_pf:.2f}")
        m5.metric("⚖️ 켈리 베팅", f"{kelly_pct:.1f}%")
        
        st.divider()
        st.subheader("🚀 내 계좌 vs KOSPI 지수")
        daily_df = df.groupby('Date')['P_L_Amount'].sum().reset_index().sort_values('Date')
        daily_df['Cumulative'] = daily_df['P_L_Amount'].cumsum()
        try:
            start = daily_df['Date'].min().strftime('%Y-%m-%d')
            kospi = yf.download("^KS11", start=start, progress=False)['Close'].reset_index()
            kospi.columns = ['Date', 'KOSPI']
            kospi['Date'] = pd.to_datetime(kospi['Date']).dt.tz_localize(None)
            base = alt.Chart(daily_df).encode(x='Date:T')
            my_chart = base.mark_line(color='#00AA00', strokeWidth=3).encode(y=alt.Y('Cumulative:Q', title='내 수익'), tooltip=['Date', 'Cumulative'])
            kospi_chart = alt.Chart(kospi).mark_line(color='#FF4444', strokeDash=[5,5]).encode(x='Date:T', y=alt.Y('KOSPI:Q', title='KOSPI', scale=alt.Scale(zero=False)))
            st.altair_chart(alt.layer(my_chart, kospi_chart).resolve_scale(y='independent'), use_container_width=True)
        except: st.line_chart(daily_df.set_index('Date')['Cumulative'])

    with tab2:
        st.subheader("📅 월별 상세 성적표")
        monthly_stats = []
        for ym, group in df.groupby('YearMonth'):
            g_wins = group[group['ROI_Percent'] > 0]; g_losses = group[group['ROI_Percent'] <= 0]
            gross_profit = group[group['P_L_Amount'] > 0]['P_L_Amount'].sum()
            gross_loss = abs(group[group['P_L_Amount'] <= 0]['P_L_Amount'].sum())
            pf = gross_profit / gross_loss if gross_loss > 0 else 0
            m_avg_gain_pct = g_wins['ROI_Percent'].mean() if not g_wins.empty else 0
            m_avg_loss_pct = abs(g_losses['ROI_Percent'].mean()) if not g_losses.empty else 0
            m_wl_ratio = m_avg_gain_pct / m_avg_loss_pct if m_avg_loss_pct > 0 else 0
            m_count = len(group)
            win_prob = len(g_wins) / m_count if m_count > 0 else 0
            loss_prob = 1 - win_prob
            m_expectancy = (win_prob * m_avg_gain_pct) - (loss_prob * m_avg_loss_pct)
            
            monthly_stats.append({
                "기간": str(ym), "총 손익": float(group['P_L_Amount'].sum()), 
                "거래횟수": int(m_count), "승률": float(win_prob*100), 
                "손익비": float(m_wl_ratio), "PF": float(pf), "기대수익": float(m_expectancy)
            })
        df_monthly = pd.DataFrame(monthly_stats).sort_values("기간", ascending=False)
        try:
            st.dataframe(df_monthly.style.map(color_profit_loss, subset=['총 손익', '기대수익']), use_container_width=True)
        except AttributeError:
            st.dataframe(df_monthly.style.applymap(color_profit_loss, subset=['총 손익', '기대수익']), use_container_width=True)

    with tab3:
        st.subheader("📆 연도별 종합 성적표")
        yearly_stats = []
        for y, group in df.groupby('Year'):
            g_wins = group[group['ROI_Percent'] > 0]; g_losses = group[group['ROI_Percent'] <= 0]
            gross_profit = group[group['P_L_Amount'] > 0]['P_L_Amount'].sum()
            gross_loss = abs(group[group['P_L_Amount'] <= 0]['P_L_Amount'].sum())
            pf = gross_profit / gross_loss if gross_loss > 0 else 0
            y_avg_gain_pct = g_wins['ROI_Percent'].mean() if not g_wins.empty else 0
            y_avg_loss_pct = abs(g_losses['ROI_Percent'].mean()) if not g_losses.empty else 0
            y_wl_ratio = y_avg_gain_pct / y_avg_loss_pct if y_avg_loss_pct > 0 else 0
            y_count = len(group)
            win_prob = len(g_wins) / y_count if y_count > 0 else 0
            loss_prob = 1 - win_prob
            y_expectancy = (win_prob * y_avg_gain_pct) - (loss_prob * y_avg_loss_pct)
            
            yearly_stats.append({
                "연도": int(y), "총 손익": float(group['P_L_Amount'].sum()), 
                "거래횟수": int(y_count), "승률": float(win_prob*100), 
                "손익비": float(y_wl_ratio), "PF": float(pf), "기대수익": float(y_expectancy)
            })
        df_yearly = pd.DataFrame(yearly_stats).sort_values("연도", ascending=False)
        try:
            st.dataframe(df_yearly.style.map(color_profit_loss, subset=['총 손익', '기대수익']), use_container_width=True)
        except AttributeError:
            st.dataframe(df_yearly.style.applymap(color_profit_loss, subset=['총 손익', '기대수익']), use_container_width=True)

    with tab4: 
        df_sorted = df.sort_values('Date', ascending=False)
        try:
            st.dataframe(df_sorted.style.map(color_profit_loss, subset=['ROI_Percent', 'P_L_Amount']), use_container_width=True)
        except AttributeError:
            st.dataframe(df_sorted.style.applymap(color_profit_loss, subset=['ROI_Percent', 'P_L_Amount']), use_container_width=True)

    with tab5:
        st.subheader("⚖️ Victor Sperandeo's Reward-to-Risk Analysis")
        v_wins = df[df['ROI_Percent'] > 0]; v_losses = df[df['ROI_Percent'] <= 0]
        v_avg_win = v_wins['ROI_Percent'].mean() if not v_wins.empty else 0
        v_avg_loss = abs(v_losses['ROI_Percent'].mean()) if not v_losses.empty else 0
        v_rr_ratio = v_avg_win / v_avg_loss if v_avg_loss > 0 else 0
        st.metric("기간 손익비 (R/R)", f"{v_rr_ratio:.2f} : 1")

    with tab6:
        st.subheader("🎯 R-배수 분석")
        r_losses = df[df['P_L_Amount'] < 0]
        avg_loss_abs = abs(r_losses['P_L_Amount'].mean()) if not r_losses.empty else 1
        df['R_Value'] = df['P_L_Amount'] / avg_loss_abs
        st.metric("평균 R-배수", f"{df['R_Value'].mean():.2f}R")

    with tab7:
        st.subheader("🔔 손익 분포")
        hist_chart = alt.Chart(df).mark_bar().encode(
            x=alt.X('ROI_Percent', bin=alt.Bin(step=2.5), title='수익률 구간 (%)'),
            y=alt.Y('count()', title='거래 횟수'),
            color=alt.condition(alt.datum.ROI_Percent > 0, alt.value("#00AA00"), alt.value("#FF4444"))
        ).properties(height=400)
        st.altair_chart(hist_chart, use_container_width=True)
else:
    st.info("👈 사이드바 매매 기록을 입력하면 대시보드가 활성화됩니다.")
