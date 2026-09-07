import streamlit as st
import pandas as pd
from datetime import datetime
import json
import gspread
from google.oauth2.service_account import Credentials

# 1. 어플 기본 설정
st.set_page_config(page_title="추세추종 매매일지", page_icon="📈", layout="wide")

# 2. 구글 시트 다이렉트 연결
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
    st.stop()

# 3. 데이터 불러오기 및 저장 함수
def load_journal_data():
    try:
        ws = doc.get_worksheet(0)
        data = ws.get_all_records()
        if not data:
            return pd.DataFrame(columns=[
                'Date', 'Ticker', 'Buy_Price', 'Stop_Loss', 'Target_Price', 
                'R_Multiple', 'VCP', 'Darvas', 'Volume_Surge', 'Emotion', 'Mistake', 'Reflection', 'Chart_Link'
            ])
        df = pd.DataFrame(data)
        # 구버전 시트에 Chart_Link 컬럼이 없을 경우를 대비한 방어막
        if 'Chart_Link' not in df.columns:
            df['Chart_Link'] = ""
        return df
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
# 4. 사이드바: 신규 타점 입력 폼
# ==========================================
st.sidebar.header("🎯 신규 타점 입력")
with st.sidebar.form("trend_journal_form", clear_on_submit=True):
    trade_date = st.date_input("매수 일자", datetime.today())
    ticker = st.text_input("종목명 (예: 한화에어로스페이스)").strip()
    
    st.markdown("---")
    buy_price = st.number_input("매수가 (원)", min_value=0.0, step=100.0)
    stop_loss = st.number_input("초기 손절가 (원) [필수]", min_value=0.0, step=100.0)
    target_price = st.number_input("1차 목표가 (원)", min_value=0.0, step=100.0)
    
    r_multiple = 0.0
    if buy_price > 0 and stop_loss > 0 and buy_price > stop_loss:
        risk = buy_price - stop_loss
        reward = target_price - buy_price if target_price > buy_price else 0
        if risk > 0:
            r_multiple = reward / risk
            if r_multiple >= 3.0:
                st.success(f"⚖️ 기대 R-배수: {r_multiple:.2f}R (🔥 통과)")
            else:
                st.warning(f"⚠️ 기대 R-배수: {r_multiple:.2f}R (미달)")

    st.markdown("---")
    vcp = st.checkbox("VCP (변동성 축소 패턴) 완성")
    darvas = st.checkbox("다바스 박스 상단 돌파")
    volume_surge = st.checkbox("기준 거래량 대폭 유입")
    
    st.markdown("---")
    emotion = st.selectbox("진입 심리", ["차분함 / 원칙 준수", "조급함 / FOMO", "불안함", "확신에 찬 상태"])
    mistake = st.selectbox("실수 여부", ["없음 (원칙 매매)", "손절가 이탈 늦음", "뇌동매매 / 조급한 진입", "비중 조절 실패", "추세 오판"])
    
    submitted = st.form_submit_button("신규 타점 기록하기")
    
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
                'Reflection': "", # 복기는 나중에 상세 페이지에서!
                'Chart_Link': ""
            }])
            
            if not df.empty:
                updated_df = pd.concat([df, new_row], ignore_index=True)
            else:
                updated_df = new_row
                
            save_journal_data(updated_df)
            st.success(f"[{ticker}] 타점이 전송되었습니다! 복기룸에서 차트와 반성문을 추가하세요. 🫡")
            st.rerun()
        else:
            st.error("종목명, 매수가, 손절가는 필수입니다.")

# ==========================================
# 5. 메인 화면: 탭 분리 (아카이브 vs 상세 복기룸)
# ==========================================
st.title("📈 제이슨 대표님의 추세추종 센터")

tab1, tab2 = st.tabs(["📋 전체 일지 아카이브", "🔍 개별 종목 상세 복기룸"])

# --- TAB 1: 전체 아카이브 ---
with tab1:
    if not df.empty:
        st.subheader("모든 매매 기록 (최신순)")
        df_sorted = df.sort_values('Date', ascending=False)
        st.dataframe(df_sorted, use_container_width=True, hide_index=True)
        
        st.divider()
        col1, col2, col3 = st.columns(3)
        col1.metric("기록된 총 타점 수", f"{len(df):,}개")
        avg_r = df['R_Multiple'].mean() if 'R_Multiple' in df.columns else 0
        col2.metric("평균 기대 R-배수", f"{avg_r:.2f}R")
        vcp_count = len(df[df['VCP'] == 'O']) if 'VCP' in df.columns else 0
        col3.metric("VCP 원칙 준수 횟수", f"{vcp_count}회")
    else:
        st.info("기록된 일지가 없습니다. 사이드바에서 첫 매매를 기록해 주십시오.")

# --- TAB 2: 개별 종목 상세 복기룸 ---
with tab2:
    st.subheader("💡 뼈저린 반성과 차트 복기")
    if not df.empty:
        # 선택하기 쉽게 날짜+종목명으로 리스트 생성
        df['Select_Label'] = df['Date'] + " | " + df['Ticker']
        trade_list = df['Select_Label'].tolist()
        trade_list.reverse() # 최신순으로 정렬
        
        selected_trade = st.selectbox("👇 복기할 종목을 선택해 주십시오", trade_list)
        
        if selected_trade:
            # 선택한 종목의 데이터 뽑아오기
            sel_date, sel_ticker = selected_trade.split(" | ")
            target_idx = df[(df['Date'] == sel_date) & (df['Ticker'] == sel_ticker)].index[0]
            row_data = df.iloc[target_idx]
            
            st.markdown(f"### [{row_data['Ticker']}] 진입 타점 분석")
            
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("매수가", f"{row_data['Buy_Price']:,.0f}원")
            c2.metric("손절가", f"{row_data['Stop_Loss']:,.0f}원")
            c3.metric("기대 R-배수", f"{row_data['R_Multiple']}R")
            c4.metric("주요 실수", f"{row_data['Mistake']}")
            
            st.divider()
            
            # --- 상세 복기 폼 (구글 시트 업데이트 기능) ---
            with st.form("update_reflection_form"):
                st.write("##### 📝 차트 링크 및 상세 반성문 추가")
                
                # 기존에 적어둔 내용이 있으면 불러옴
                current_link = row_data.get('Chart_Link', '')
                current_reflection = row_data.get('Reflection', '')
                
                new_chart_link = st.text_input("🔗 차트 이미지 링크 (TradingView, MTS 공유 링크 등)", value=current_link)
                new_reflection = st.text_area("✍️ 상세 복기 노트 (진입 근거, 감정선, 아쉬운 점 딥다이브)", value=current_reflection, height=200)
                
                update_btn = st.form_submit_button("복기 내용 덮어쓰기 (업데이트)")
                
                if update_btn:
                    with st.spinner("구글 시트에 복기 내용을 안전하게 업데이트 중입니다..."):
                        try:
                            # 구글 시트는 1번부터 시작하고 헤더가 있으므로 인덱스 보정 (+2)
                            sheet_row_num = int(target_idx) + 2 
                            ws = doc.get_worksheet(0)
                            
                            # Reflection은 12번째 컬럼, Chart_Link는 13번째 컬럼 (A=1, L=12, M=13)
                            ws.update_cell(sheet_row_num, 12, new_reflection)
                            ws.update_cell(sheet_row_num, 13, new_chart_link)
                            
                            st.success("✅ 상세 복기가 완벽하게 업데이트되었습니다! (새로고침을 누르시면 반영됩니다)")
                        except Exception as e:
                            st.error(f"업데이트 중 오류 발생: {e}")
                            
            # 링크가 있으면 바로 누를 수 있게 버튼 제공
            if pd.notna(current_link) and current_link.strip() != "":
                st.markdown(f"**[차트 확인하기]({current_link})** 👈 (터치 시 새 창으로 차트가 열립니다)")
    else:
        st.info("기록된 타점이 있어야 복기를 진행할 수 있습니다.")
