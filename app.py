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

# 3. 데이터 불러오기 및 저장 함수 (🚨 중복 열 이름 해결 특효약 투여)
def load_journal_data():
    try:
        ws = doc.get_worksheet(0)
        list_of_lists = ws.get_all_values() 
        
        expected_cols = [
            'Date', 'Ticker', 'Buy_Price', 'Stop_Loss', 'Target_Price', 
            'R_Multiple', 'VCP', 'Darvas', 'Volume_Surge', 'Emotion', 'Mistake', 'Reflection', 'Chart_Link'
        ]
        
        if not list_of_lists or len(list_of_lists) < 2:
            return pd.DataFrame(columns=expected_cols)
            
        # [핵심 수술 부위] 중복된 헤더 이름이 있으면 뒤에 숫자를 붙여 강제로 중복을 없앰
        raw_headers = list_of_lists[0]
        safe_headers = []
        for i, h in enumerate(raw_headers):
            h_str = str(h).strip() if h else f"Unnamed_{i}" # 빈칸은 Unnamed로 대체
            if h_str in safe_headers:
                h_str = f"{h_str}_{i}" # 중복되면 숫자를 붙임
            safe_headers.append(h_str)

        data = list_of_lists[1:]
        
        max_len = len(safe_headers)
        clean_data = []
        for row in data:
            if len(row) < max_len:
                row.extend([""] * (max_len - len(row)))
            elif len(row) > max_len:
                row = row[:max_len]
            clean_data.append(row)
            
        # 중복 없는 안전한 헤더로 데이터프레임 생성
        df = pd.DataFrame(clean_data, columns=safe_headers)
        
        for col in expected_cols:
            if col not in df.columns:
                df[col] = ""
                
        num_cols = ['Buy_Price', 'Stop_Loss', 'Target_Price', 'R_Multiple']
        for col in num_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
            
        return df
    except Exception as e:
        st.error(f"🚨 데이터 로딩 중 문제가 발생했습니다: {e}")
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
            new_row_data = {
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
                'Reflection': "", 
                'Chart_Link': ""
            }
            
            if not df.empty:
                for col in df.columns:
                    if col not in new_row_data:
                        new_row_data[col] = "" 
                new_row = pd.DataFrame([new_row_data])
                updated_df = pd.concat([df, new_row], ignore_index=True)
            else:
                new_row = pd.DataFrame([new_row_data])
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
        if 'Date' in df.columns:
            df_sorted = df.sort_values('Date', ascending=False)
        else:
            df_sorted = df
            
        # 오류 방지를 위해 인덱스 리셋 후 표출
        st.dataframe(df_sorted.reset_index(drop=True), use_container_width=True)
        
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
    if not df.empty and 'Date' in df.columns and 'Ticker' in df.columns:
        df['Select_Label'] = df['Date'].astype(str) + " | " + df['Ticker'].astype(str)
        trade_list = df['Select_Label'].tolist()
        trade_list.reverse() 
        
        selected_trade = st.selectbox("👇 복기할 종목을 선택해 주십시오", trade_list)
        
        if selected_trade:
            sel_date, sel_ticker = selected_trade.split(" | ", 1)
            target_idx = df[(df['Date'].astype(str) == sel_date) & (df['Ticker'].astype(str) == sel_ticker)].index[0]
            row_data = df.iloc[target_idx]
            
            st.markdown(f"### [{row_data.get('Ticker', '')}] 진입 타점 분석")
            
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("매수가", f"{row_data.get('Buy_Price', 0):,.0f}원")
            c2.metric("손절가", f"{row_data.get('Stop_Loss', 0):,.0f}원")
            c3.metric("기대 R-배수", f"{row_data.get('R_Multiple', 0)}R")
            c4.metric("주요 실수", f"{row_data.get('Mistake', '')}")
            
            st.divider()
            
            with st.form("update_reflection_form"):
                st.write("##### 📝 차트 링크 및 상세 반성문 추가")
                
                current_link = row_data.get('Chart_Link', '')
                current_reflection = row_data.get('Reflection', '')
                
                new_chart_link = st.text_input("🔗 차트 이미지 링크 (TradingView, MTS 등)", value=str(current_link) if pd.notna(current_link) else "")
                new_reflection = st.text_area("✍️ 상세 복기 노트 (진입 근거, 감정선 딥다이브)", value=str(current_reflection) if pd.notna(current_reflection) else "", height=200)
                
                update_btn = st.form_submit_button("복기 내용 덮어쓰기 (업데이트)")
                
                if update_btn:
                    with st.spinner("구글 시트에 복기 내용을 업데이트 중입니다..."):
                        try:
                            sheet_row_num = int(target_idx) + 2 
                            ws = doc.get_worksheet(0)
                            
                            col_idx_reflection = df.columns.get_loc('Reflection') + 1
                            col_idx_link = df.columns.get_loc('Chart_Link') + 1
                            
                            ws.update_cell(1, col_idx_reflection, 'Reflection')
                            ws.update_cell(1, col_idx_link, 'Chart_Link')
                            
                            ws.update_cell(sheet_row_num, col_idx_reflection, new_reflection)
                            ws.update_cell(sheet_row_num, col_idx_link, new_chart_link)
                            
                            st.success("✅ 상세 복기가 완벽하게 업데이트되었습니다! (새로고침을 누르시면 반영됩니다)")
                        except Exception as e:
                            st.error(f"업데이트 중 오류 발생: {e}")
                            
            if pd.notna(current_link) and str(current_link).strip() != "":
                st.markdown(f"**[차트 확인하기]({current_link})** 👈 (터치 시 새 창으로 차트가 열립니다)")
    else:
        st.info("표시할 수 있는 타점 데이터가 없습니다.")
