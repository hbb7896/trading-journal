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
        list_of_lists = ws.get_all_values() 
        
        expected_cols = [
            'Date', 'Ticker', 'P_L_Amount', 'ROI_Percent', 
            'Memo', 'Mistake_Tags', 'Emotion', 'Discipline', 'Buy_Amount', 'Sell_Amount', 'Chart_Link'
        ]
        
        if not list_of_lists or len(list_of_lists) < 2:
            return pd.DataFrame(columns=expected_cols)
            
        raw_headers = list_of_lists[0]
        safe_headers = []
        for i, h in enumerate(raw_headers):
            h_str = str(h).strip() if h else f"Unnamed_{i}"
            if h_str in safe_headers:
                h_str = f"{h_str}_{i}"
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
            
        df = pd.DataFrame(clean_data, columns=safe_headers)
        
        for col in expected_cols:
            if col not in df.columns:
                df[col] = ""
                
        num_cols = ['P_L_Amount', 'ROI_Percent', 'Buy_Amount', 'Sell_Amount']
        for col in num_cols:
            if col in df.columns:
                df[col] = df[col].astype(str).str.replace(',', '').str.replace('%', '')
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
# 4. 사이드바: 신규 매매 기록 입력 폼 
# ==========================================
st.sidebar.header("📝 신규 매매 기록 입력")
with st.sidebar.form("trend_journal_form", clear_on_submit=True):
    trade_date = st.date_input("일자", datetime.today())
    ticker = st.text_input("종목명 (예: 유한양행)").strip()
    
    st.markdown("---")
    buy_amount = st.number_input("총 매수 금액 (원)", min_value=0.0, step=100000.0)
    roi_percent = st.number_input("수익률 (%)", value=0.0, format="%.2f")
    
    p_l_amount = 0.0
    sell_amount = 0.0
    if buy_amount > 0:
        p_l_amount = buy_amount * (roi_percent / 100)
        sell_amount = buy_amount + p_l_amount
        st.info(f"🧮 손익금액: {p_l_amount:+,.0f}원 / 매도금액: {sell_amount:,.0f}원")

    st.markdown("---")
    memo = st.text_input("메모")
    mistake_tags = st.selectbox("실수 태그", ["", "없음 (원칙 매매)", "손절가 이탈 늦음", "뇌동매매", "비중 조절 실패"])
    emotion = st.selectbox("심리 상태", ["", "차분함", "조급함 / FOMO", "불안함", "확신"])
    discipline = st.text_input("규율 준수 여부")
    
    submitted = st.form_submit_button("구글 시트에 기록 저장")
    
    if submitted:
        if ticker:
            new_row_data = {
                'Date': trade_date.strftime('%Y-%m-%d'),
                'Ticker': ticker,
                'P_L_Amount': round(p_l_amount, 2),
                'ROI_Percent': round(roi_percent, 2),
                'Memo': memo,
                'Mistake_Tags': mistake_tags,
                'Emotion': emotion,
                'Discipline': discipline,
                'Buy_Amount': round(buy_amount, 2),
                'Sell_Amount': round(sell_amount, 2),
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
            st.success(f"[{ticker}] 기록이 안전하게 저장되었습니다! 복기룸에서 차트를 추가해보세요. 🫡")
            st.rerun()
        else:
            st.error("종목명을 입력해주세요.")

# ==========================================
# 5. 메인 화면: 탭 분리 (아카이브 vs 개별 복기룸)
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
            
        st.dataframe(df_sorted.reset_index(drop=True), use_container_width=True)
        
        st.divider()
        col1, col2, col3 = st.columns(3)
        col1.metric("총 매매 횟수", f"{len(df):,}회")
        total_pl = df['P_L_Amount'].sum() if 'P_L_Amount' in df.columns else 0
        col2.metric("누적 총 손익", f"{total_pl:+,.0f}원")
        win_trades = len(df[df['ROI_Percent'] > 0]) if 'ROI_Percent' in df.columns else 0
        win_rate = (win_trades / len(df)) * 100 if len(df) > 0 else 0
        col3.metric("승률", f"{win_rate:.1f}%")
    else:
        st.info("기록된 일지가 없습니다.")

# --- TAB 2: 개별 종목 상세 복기룸 ---
with tab2:
    st.subheader("💡 개별 종목 상세 복기 및 차트 첨부")
    if not df.empty and 'Date' in df.columns and 'Ticker' in df.columns:
        df['Select_Label'] = df['Date'].astype(str) + " | " + df['Ticker'].astype(str)
        trade_list = df['Select_Label'].tolist()
        trade_list.reverse() 
        
        selected_trade = st.selectbox("👇 복기할 종목을 선택해 주십시오", trade_list)
        
        if selected_trade:
            sel_date, sel_ticker = selected_trade.split(" | ", 1)
            target_idx = df[(df['Date'].astype(str) == sel_date) & (df['Ticker'].astype(str) == sel_ticker)].index[0]
            row_data = df.iloc[target_idx]
            
            current_link = row_data.get('Chart_Link', '')
            current_memo = row_data.get('Memo', '')
            current_mistake = row_data.get('Mistake_Tags', '')
            current_emotion = row_data.get('Emotion', '')
            
            # 🚨 [위치 이동] 차트 이미지를 종목 선택 바로 밑으로 끌어올림!
            if pd.notna(current_link) and str(current_link).strip() != "":
                st.markdown("<br>", unsafe_allow_html=True) # 위아래 여백 살짝 줌
                try:
                    st.image(str(current_link), caption=f"📸 {row_data.get('Ticker', '')} 매매 차트", use_container_width=True)
                    st.markdown(f"**[🔗 차트 원본 크게 보기]({current_link})** 👈 (터치 시 확대)")
                except:
                    st.warning("⚠️ 차트 이미지를 불러올 수 없습니다. 링크가 올바른 이미지 주소(jpg, png 등)인지 확인해주세요.")
                st.divider()
            
            st.markdown(f"### [{row_data.get('Ticker', '')}] 거래 상세 분석")
            
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("거래 일자", f"{row_data.get('Date', '')}")
            c2.metric("수익률", f"{row_data.get('ROI_Percent', 0):+.2f}%")
            c3.metric("손익금액", f"{row_data.get('P_L_Amount', 0):+,.0f}원")
            c4.metric("매수금액", f"{row_data.get('Buy_Amount', 0):,.0f}원")
            
            st.divider()
            
            with st.form("update_memo_form"):
                st.write("##### 📝 메모 및 복기 차트 업데이트")
                
                new_chart_link = st.text_input("🔗 차트 이미지 링크 (Postimages 등에서 복사한 주소 붙여넣기)", value=str(current_link) if pd.notna(current_link) else "")
                new_memo = st.text_area("메모 및 상세 복기", value=str(current_memo) if pd.notna(current_memo) else "", height=150)
                
                col_left, col_right = st.columns(2)
                with col_left:
                    new_mistake = st.text_input("실수 태그", value=str(current_mistake) if pd.notna(current_mistake) else "")
                with col_right:
                    new_emotion = st.text_input("심리 상태", value=str(current_emotion) if pd.notna(current_emotion) else "")
                
                update_btn = st.form_submit_button("구글 시트에 내용 및 차트 저장")
                
                if update_btn:
                    with st.spinner("구글 시트에 전체 데이터를 안전하게 덮어쓰고 있습니다..."):
                        try:
                            df.at[target_idx, 'Memo'] = new_memo
                            df.at[target_idx, 'Mistake_Tags'] = new_mistake
                            df.at[target_idx, 'Emotion'] = new_emotion
                            df.at[target_idx, 'Chart_Link'] = new_chart_link
                            
                            save_journal_data(df)
                            
                            st.success("✅ 완벽하게 업데이트되었습니다! (새로고침을 눌러 확인하세요)")
                        except Exception as e:
                            st.error(f"업데이트 중 오류 발생: {e}")
    else:
        st.info("표시할 수 있는 타점 데이터가 없습니다.")
