import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime

# 1. 구글 시트 연동 설정 (Streamlit Secrets 활용)
scope = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

@st.cache_resource
def get_google_sheet():
    try:
        # 스트림릿 시크릿에 등록된 인증 정보를 가져옵니다.
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
        client = gspread.authorize(creds)
        
        # '매매일지'라는 이름의 구글 스프레드시트를 연동합니다.
        sheet = client.open("매매일지").sheet1
        return sheet
    except Exception as e:
        return None

st.title("📈 제이슨 대표님의 추세추종 매매일지")
st.subheader("마크 미너비니 & 윌리엄 오닐 트레이딩 시스템 (with 구글 시트)")

sheet = get_google_sheet()

if sheet is None:
    st.error("⚠️ 구글 시트 연결에 실패했습니다! 스트림릿 Secrets 설정을 확인해 주세요.")
else:
    with st.form("trade_form"):
        st.write("### 🎯 신규 매수 타점 기록")
        
        col_a, col_b = st.columns(2)
        with col_a:
            trade_date = st.date_input("매수 일자", value=datetime.today())
        with col_b:
            ticker = st.text_input("종목명 (예: 삼성전자, 테슬라)")
        
        col1, col2 = st.columns(2)
        with col1:
            buy_price = st.number_input("매수가 (₩)", min_value=0, step=100)
        with col2:
            stop_loss = st.number_input("초기 손절가 (₩)", min_value=0, step=100)
            
        st.write("### ✅ 핵심 돌파 조건 체크")
        vcp_check = st.checkbox("VCP (변동성 축소 패턴) 완성되었는가?")
        darvas_check = st.checkbox("다바스 박스 상단 돌파 (거래량 동반)인가?")
        
        memo = st.text_area("매매 반성 및 코멘트 (심리 상태, 주도주 여부 등)")
        
        submit_button = st.form_submit_button("구글 시트에 일지 저장하기")

    if submit_button:
        if ticker:
            try:
                # 시트에 기록할 데이터 행 구성
                row_data = [
                    str(trade_date),
                    ticker,
                    buy_price,
                    stop_loss,
                    "O" if vcp_check else "X",
                    "O" if darvas_check else "X",
                    memo
                ]
                sheet.append_row(row_data)
                st.success(f"[{ticker}] 매매일지가 구글 시트에 안전하게 박제되었습니다! 🫡")
            except Exception as e:
                st.error(f"저장 중 오류 발생: {e}")
        else:
            st.warning("대표님, 종목명을 입력해 주십시오!")

    # 3. 기존에 기록된 매매일지 불러와서 화면에 띄우기
    st.divider()
    st.write("### 📊 나의 최근 매매일지 아카이브")
    try:
        data = sheet.get_all_records()
        if data:
            st.dataframe(data)
        else:
            st.info("아직 기록된 매매일지가 없습니다. 첫 타점을 기록해 보십시오!")
    except Exception as e:
        st.write("시트 데이터를 불러오는 중입니다...")
