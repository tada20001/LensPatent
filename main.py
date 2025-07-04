import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import io
import os
import time
from patent_searcher import get_total_hits, save_all_patents_to_csv
import plotly.express as px

# --- 1. 페이지 설정 ---
st.set_page_config(page_title="특허 검색 시스템", layout="wide")
st.title("🔬 특허 검색 및 분석 시스템")
st.caption("Lens.org API를 이용한 특허 정보 검색 및 시각화")

# --- 2. 세션 상태 초기화 ---
if 'api_key' not in st.session_state:
    st.session_state.api_key = ''
if 'params' not in st.session_state:
    st.session_state.params = {
        'search_term': '', 'search_fields': ['title', 'abstract'], 'applicant': '', 'ipc_cpc': '',
        'date_type': 'application', 'start_year': '', 'end_year': '', 'status_filter': 'all',
        'search_term_advanced': ''
    }
if 'search_result' not in st.session_state:
    st.session_state.search_result = None
# 대시보드용 데이터프레임을 저장할 공간을 만듭니다.
if 'df_for_dashboard' not in st.session_state:
    st.session_state.df_for_dashboard = None

# --- 3. 사이드바 (API 키 입력) ---
with st.sidebar:
    st.header("API 설정")
    st.session_state.api_key = st.text_input(
        "Lens.org API 키", type="password", value=st.session_state.api_key
    )
    st.markdown("---")

if not st.session_state.api_key:
    st.info("👈 사이드바에 Lens.org API 키를 입력하고 Enter를 누르세요.")
    st.stop()

# --- 4. 메인 UI 탭 구성 ---
main_tab_search, main_tab_dashboard = st.tabs(["**🔍 특허 검색 및 다운로드**", "**📊 분석 대시보드**"])


# ==========================================================================================
#  첫 번째 탭: 기존의 모든 검색 기능
# ==========================================================================================
with main_tab_search:
    # --- 기존 검색 UI 구성 (일반/고급 탭) ---
    tab1, tab2 = st.tabs(["**일반 검색**", "**고급 검색 (검색식 직접 입력)**"])

    with tab1:
        st.subheader("1. 검색어 및 검색 범위")
        col1, col2 = st.columns([3, 2])
        with col1:
            st.session_state.params['search_term'] = st.text_input("검색어", value=st.session_state.params['search_term'], placeholder='예: "lithium-ion battery" solid-state electrolyte')
        with col2:
            st.session_state.params['search_fields'] = st.multiselect("검색 대상 필드", options=['title', 'abstract', 'claim'], default=st.session_state.params['search_fields'])

        st.markdown("---")
        st.subheader("2. 상세 조건 (선택 사항)")
        col_detail1, col_detail2 = st.columns(2)
        with col_detail1:
            st.session_state.params['applicant'] = st.text_input("출원인 이름", value=st.session_state.params['applicant'], placeholder="예: SAMSUNG, GOOGLE")
        with col_detail2:
            st.session_state.params['ipc_cpc'] = st.text_input("분류 코드 (IPC/CPC)", value=st.session_state.params['ipc_cpc'], placeholder="예: H01M, G06N 3/04")

        st.markdown("---")
        st.subheader("3. 기간 및 상태")
        col_date1, col_date2 = st.columns(2)
        with col_date1:
            st.session_state.params['date_type'] = st.radio("날짜 기준", options=['application', 'grant'], index=0 if st.session_state.params['date_type'] == 'application' else 1, format_func=lambda x: {'application': '출원일', 'grant': '등록일'}[x])
            sub_col1, sub_col2 = st.columns(2)
            with sub_col1:
                st.session_state.params['start_year'] = st.text_input("시작 연도", value=st.session_state.params['start_year'], placeholder="예: 2020")
            with sub_col2:
                st.session_state.params['end_year'] = st.text_input("종료 연도", value=st.session_state.params['end_year'], placeholder="예: 2023")
        with col_date2:
            st.session_state.params['status_filter'] = st.radio("등록 상태", options=['all', 'granted'], index=0 if st.session_state.params['status_filter'] == 'all' else 1, format_func=lambda x: {'all': '모든 특허', 'granted': '등록된 특허만'}[x])

    with tab2:
        with st.expander("ℹ️ 고급 검색식 작성 방법 보기"):
            st.markdown("""
            - **기본 형식**: `필드이름:검색어`
            - **연산자**: `AND`, `OR`, `NOT`
            - **구문**: 큰따옴표 `"` 사용 (예: `title:"solid-state battery"`)
            - **범위**: `필드이름:[시작 TO 종료]` (예: `year_published:[2020 TO 2023]`)
            """)
            st.link_button("Lens.org 공식 필드 정의 문서 보기", "https://support.lens.org/knowledge-base/patent-field-definition/")
        st.session_state.params['search_term_advanced'] = st.text_area("**Lens API 검색식 직접 입력**", value=st.session_state.params['search_term_advanced'], height=200, placeholder='(title:("machine learning" OR "deep learning") AND abstract:(semiconductor AND manufacturing))')

    # --- 기존 검색 버튼 및 로직 ---
    st.markdown("---")

    def get_search_params():
        search_params = {}
        if st.session_state.params.get('search_term_advanced', '').strip():
            search_params['query_type'] = 'advanced'
            search_params['search_term'] = st.session_state.params['search_term_advanced']
        else:
            search_params['query_type'] = 'simple'
            keys_to_copy = ['search_term', 'search_fields', 'applicant', 'ipc_cpc', 'date_type', 'start_year', 'end_year', 'status_filter']
            for key in keys_to_copy:
                search_params[key] = st.session_state.params.get(key)
        return search_params

    col_run, col_reset = st.columns([4, 1])

    with col_run:
        if st.button("🚀 검색 결과 확인", use_container_width=True, type="primary"):
            search_params = get_search_params()
            if search_params.get('query_type') == 'simple' and (not search_params.get('search_term') or not search_params.get('search_fields')):
                st.warning("일반 검색: '검색어'와 '검색 대상 필드'는 필수입니다.")
                st.session_state.search_result = None
            else:
                start_time = time.time()
                with st.spinner("총 검색 건수를 확인 중입니다..."):
                    total_hits, error = get_total_hits(st.session_state.api_key, search_params)
                end_time = time.time()
                if error:
                    st.error(f"오류: {error}")
                    st.session_state.search_result = None
                else:
                    search_time = end_time - start_time
                    st.session_state.search_result = {"total_hits": total_hits, "search_params": search_params, "search_time": search_time}

    with col_reset:
        if st.button("🔄 조건 초기화", use_container_width=True):
            st.session_state.params = {
                'search_term': '', 'search_fields': ['title', 'abstract'], 'applicant': '', 'ipc_cpc': '',
                'date_type': 'application', 'start_year': '', 'end_year': '', 'status_filter': 'all',
                'search_term_advanced': ''
            }
            st.session_state.search_result = None
            st.session_state.df_for_dashboard = None
            st.rerun()

    # --- 기존 결과 표시 및 다운로드 ---
    if 'search_result' in st.session_state and st.session_state.search_result:
        total_hits = st.session_state.search_result["total_hits"]
        search_params = st.session_state.search_result["search_params"]
        search_time = st.session_state.search_result["search_time"]

        st.info(f"검색에 소요된 시간: {search_time:.2f}초")

        if total_hits > 0:
            st.success(f"총 {total_hits:,} 건의 특허가 검색되었습니다.")
            limit = 50000
            download_count = min(total_hits, limit)
            if total_hits > limit: st.warning(f"검색 결과가 많아, 다운로드는 최대 {limit:,}건으로 제한됩니다.")

            if st.button(f"엑셀 다운로드 및 대시보드 생성 ({download_count:,} 건)", use_container_width=True):
                placeholder = st.empty(); placeholder.info("전체 데이터 수집을 시작합니다...")
                progress_bar = st.progress(0, text="데이터 수집 준비 중...")
                time_placeholder = st.empty()

                def format_time(s): return str(timedelta(seconds=int(s)))
                def update_progress(processed, total_to_download, elapsed):
                    progress_value = min(processed / total_to_download if total_to_download > 0 else 0, 1.0)
                    progress_text = f"총 {total_to_download:,}건 중 {processed:,}건 수집 완료..."
                    progress_bar.progress(progress_value, text=progress_text)
                    time_placeholder.metric(label="⏰ 경과 시간", value=format_time(elapsed))

                temp_csv_path, _, error = save_all_patents_to_csv(st.session_state.api_key, search_params, progress_callback=update_progress)

                placeholder.empty(); time_placeholder.empty()
                if error: st.error(f"다운로드 중 오류 발생: {error}")
                elif temp_csv_path:
                    progress_bar.success("데이터 수집 완료! 파일 생성 및 대시보드 데이터 준비 중...")

                    with st.spinner("파일 변환 및 대시보드 데이터 로딩 중..."):
                        try:
                            df_all = pd.read_csv(temp_csv_path)
                            df_all.drop_duplicates(subset=['lens_id'], keep='first', inplace=True)
                        except Exception as e:
                            st.error(f"파일 변환 중 오류 발생: {e}")
                            df_all = pd.DataFrame()

                        # ★★★ 핵심: 수집된 데이터를 대시보드 탭을 위해 세션 상태에 저장 ★★★
                        st.session_state.df_for_dashboard = df_all.copy()

                        output = io.BytesIO()
                        with pd.ExcelWriter(output, engine='openpyxl') as writer: df_all.to_excel(writer, index=False, sheet_name='Sheet1')
                        excel_data = output.getvalue()

                    st.download_button(label="✅ 엑셀 파일 다운로드", data=excel_data, file_name="patent_results.xlsx", mime="application/vnd.ms-excel", use_container_width=True)
                    st.info("💡 데이터 준비 완료! 상단의 '📊 분석 대시보드' 탭에서 시각화 자료를 확인하세요.")
                    os.remove(temp_csv_path)
        else:
            st.info("검색 결과가 없습니다.")


# ==========================================================================================
#  두 번째 탭: 새로 추가된 분석 대시보드 기능
# ==========================================================================================
with main_tab_dashboard:
    st.header("📊 분석 대시보드")

    if st.session_state.df_for_dashboard is not None:
        df = st.session_state.df_for_dashboard

        st.success(f"**총 {len(df):,}건**의 특허 데이터를 기반으로 분석합니다.")
        st.markdown("---")

        # --- 1. 핵심 요약 ---
        st.subheader("🔢 한눈에 보는 핵심 요약")
        col1, col2, col3 = st.columns(3)
        unique_applicants = df['applicants'].str.split(';').str[0].str.strip().nunique()
        avg_citations = df['cited_by_patent_count'].mean()

        with col1:
            st.metric(label="총 특허 수", value=f"{len(df):,} 건")
        with col2:
            st.metric(label="핵심 출원인 수", value=f"{unique_applicants:,} 곳")
        with col3:
            st.metric(label="평균 피인용 수", value=f"{avg_citations:.1f} 회")

        st.markdown("---")

        # --- 2. 주요 그래프 ---
        col_graph1, col_graph2 = st.columns(2)

        with col_graph1:
            # 1. 연도별 출원 동향
            st.subheader("📈 연도별 출원 동향")
            df['application_year'] = pd.to_numeric(df['application_year'], errors='coerce')
            yearly_counts = df['application_year'].value_counts().sort_index()
            st.bar_chart(yearly_counts)

            # 2. 핵심 출원인
            st.subheader("🏢 핵심 출원인 (Top 10)")
            main_applicant = df['applicants'].str.split(';').str[0].str.strip()
            applicant_counts = main_applicant.value_counts().nlargest(10)
            st.bar_chart(applicant_counts)

        with col_graph2:
            # 3. 출원인 국적 분포
            st.subheader("🌍 출원인 국적 분포 (Top 15)")
            nationality_counts = df['applicant_nationality'].value_counts().nlargest(15)
            st.bar_chart(nationality_counts)

            # 4. 주요 기술 분야 분포
            st.subheader("🔬 주요 기술 분야 분포 (Top 15)")
            ipc_counts = df['main_ipc_field'].value_counts().nlargest(15)
            st.bar_chart(ipc_counts)
            st.caption("IPC(국제특허분류) 코드 4단위 기준")
        st.markdown("---")

        # --- 3. 상세 데이터 ---
        st.subheader("⭐ 가장 많이 인용된 특허 Top 10")
        top_cited_patents = df.sort_values(by='cited_by_patent_count', ascending=False).head(10)
        st.dataframe(top_cited_patents[['title', 'applicants', 'application_date', 'cited_by_patent_count']])

    else:
        # 데이터가 없을 경우 안내 메시지
        st.info("👈 먼저 '🔍 특허 검색 및 다운로드' 탭에서 데이터를 다운로드하고 대시보드를 생성해주세요.")