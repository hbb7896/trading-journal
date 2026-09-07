import streamlit as st
import pandas as pd
from datetime import datetime
import json
import gspread
from google.oauth2.service_account import Credentials

# 1. 어플 기본 설정 (모바일 최적화)
st.set_page_config(page_title="추세추종 매매일지", page_icon="📈", layout="wide")

# 2. 구글 시트 다이렉트 연결 (안정성 100% 순정 방식)
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
        st.error(f"🚨 구글 시트 연결 오류가 발생했습니다: {e}")
        return None

doc = get_gspread_client()
if doc is None:
    st.stop() # 에러 시 어플 렌더링 중단

# 3. 데이터 불러오기 및 저장 함수 (0번 탭 기준)
def load_journal_data():
    try:
        ws = doc.get_worksheet(0)
        data = ws.get_all_records()
        if not data:
            return pd.DataFrame(columns=[
                'Date', 'Ticker', 'Buy_Price', 'Stop_Loss', 'Target_Price', 
                'R_Multiple', 'VCP', 'Darvas', 'Volume_Surge', 'Emotion', 'Mistake', 'Reflection'
            ])
        return pd.DataFrame(data)
    except Exception:
        return pd.DataFrame()

def save_journal_data(df):
    try:
        ws = doc.get_worksheet(0)
        ws.clear()
        ws.update([df.columns.values.tolist()] + df.values.tolist())
    except Exception as e:
        st.error(f"데이터 저장 중 에러가 발생했습니다: {e}")

df = load_journal_data()

# ==========================================
# 4. 사이드바: 타점 기록 및 반성 폼 (입력부)
# ==========================================
st.sidebar.header("🎯 신규 타점 및 복기 입력")
with st.sidebar.form("trend_journal_form", clear_on_submit=True):
    trade_date = st.date_input("매수 일자", datetime.today())
    ticker = st.text_input("종목명 (예: 알테오젠, HD현대일렉트릭)").strip()
    
    st.markdown("---")
    st.markdown("##### 📐 가격 및 리스크 관리 (R-Multiple)")
    buy_price = st.number_input("매수가 (원)", min_value=0.0, step=100.0)
    stop_loss = st.number_input("초기 손절가 (원) [필수]", min_value=0.0, step=100.0)
    target_price = st.number_input("1차 목표가 (원)", min_value=0.0, step=100.0)
    
    # R-Multiple 실시간 계산 로직 (오류 방어막 적용)
    r_multiple = 0.0
    if buy_price > 0 and stop_loss > 0 and buy_price > stop_loss:
        risk = buy_price - stop_loss
        reward = target_price - buy_price if target_price > buy_price else 0
        if risk > 0:
            r_multiple = reward / risk
            if r_multiple >= 3.0:
                st.success(f"⚖️ 기대 R-배수: {r_multiple:.2f}R (🔥 빅터 스페란데오 기준 충족!)")
            else:
                st.warning(f"⚠️ 기대 R-배수: {r_multiple:.2f}R (3R 미달 - 진입 근거 재확인 필요)")

    st.markdown("---")
    st.markdown("##### ✅ 추세추종 돌파 조건 체크")
    vcp = st.checkbox("VCP (변동성 축소 패턴) 완성")
    darvas = st.checkbox("다바스 박스 상단 돌파")
    volume_surge = st.checkbox("기준 거래량 대폭 유입")
    
    st.markdown("---")
    st.markdown("##### 🧠 트레이더 심리 및 뼈저린 반성")
    emotion = st.selectbox("진입 당시 심리 상태", ["차분함 / 원칙 준수", "조급함 / FOMO", "불안함", "확신에 찬 상태"])
    mistake = st.selectbox("주요 실수 여부", ["없음 (완벽한 원칙 매매)", "손절가 이탈 늦음", "뇌동매매 / 조급한 진입", "비중 조절 실패", "추세 오판"])
    reflection = st.text_area("매매 반성 및 복기 노트", placeholder="이번 매매에서 배운 점이나 개선할 점을 가감 없이 적어보십시오.")
    
    submitted = st.form_submit_button("매매일지 시트에 박제하기")
    
    if submitted:
        if ticker and buy_price > 0 and stop_loss > 0:
            new_row = pd.DataFrame([{
                'Date': trade_date.strftime('%Y-%m-%d'),
                'Ticker': ticker,
                'Buy_Price': buy_price,
                'Stop_Loss': stop_loss,
                'Target_Price': target_price,
                'R_Multiple': round(r_multiple, 2),
                'VCP': "O" if vcp else "X",
                'Darvas': "O" if darvas else "X",
                'Volume_Surge': "O" if volume_surge else "X",
                'Emotion': emotion,
                'Mistake': mistake,
                'Reflection': reflection
            }])
            
            if not df.empty:
                updated_df = pd.concat([df, new_row], ignore_index=True)
            else:
                updated_df = new_row
                
            save_journal_data(updated_df)
            st.success(f"[{ticker}] 타점 및 복기 기록이 구글 시트에 안전하게 전송되었습니다! 🫡")
            st.rerun()
        else:
            st.error("대표님, 종목명과 매수가, 초기 손절가는 리스크 관리를 위해 반드시 입력해야 합니다.")

# ==========================================
# 5. 메인 화면: 기록 열람 및 요약 (출력부)
# ==========================================
st.title("📈 추세추종 매매일지 & 반성 센터")
st.markdown("마크 미너비니와 니콜라스 다바스의 철학을 갤25에 담은 **타점 및 리스크 관리 전용 워크스테이션**입니다.")

if not df.empty:
    st.divider()
    st.subheader("📋 나의 전체 매매일지 및 복기 아카이브")
    
    # 최신 날짜가 위로 올라오도록 정렬
    if 'Date' in df.columns:
        df_sorted = df.sort_values('Date', ascending=False)
    else:
        df_sorted = df
        
    # 구글 시트 데이터를 예쁘게 표출
    st.dataframe(df_sorted, use_container_width=True, hide_index=True)
    
    st.divider()
    st.subheader("🔍 트레이딩 통계 요약")
    col1, col2, col3 = st.columns(3)
    col1.metric("기록된 총 타점 수", f"{len(df):,}개")
    
    avg_r = df['R_Multiple'].mean() if 'R_Multiple' in df.columns else 0
    col2.metric("평균 기대 R-배수", f"{avg_r:.2f}R")
    
    vcp_count = len(df[df['VCP'] == 'O']) if 'VCP' in df.columns else 0
    col3.metric("VCP 원칙 준수 횟수", f"{vcp_count}회")

else:
    st.info("👈 왼쪽 탭을 열어 첫 번째 추세추종 매매 타점과 반성 노트를 기록해 주십시오!")
