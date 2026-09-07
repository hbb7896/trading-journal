import streamlit as st

st.title("📈 제이슨 대표님의 추세추종 매매일지")
st.subheader("마크 미너비니 & 윌리엄 오닐 트레이딩 시스템")

with st.form("trade_form"):
    st.write("### 🎯 신규 매수 타점 기록")
    ticker = st.text_input("종목명")
    
    col1, col2 = st.columns(2)
    with col1:
        buy_price = st.number_input("매수가 (₩)", min_value=0, step=100)
    with col2:
        stop_loss = st.number_input("초기 손절가 (₩)", min_value=0, step=100)
        
    st.write("### ✅ 핵심 돌파 조건 체크")
    vcp_check = st.checkbox("VCP (변동성 축소 패턴) 완성되었는가?")
    darvas_check = st.checkbox("다바스 박스 상단 돌파 (거래량 동반)인가?")
    
    submit_button = st.form_submit_button("일지 저장하기")

if submit_button:
    if ticker:
        st.success(f"[{ticker}] 타점 기록 완료! 리스크 관리 철저! 🫡")
    else:
        st.warning("대표님, 종목명을 입력해 주십시오!")
