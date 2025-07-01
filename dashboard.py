import streamlit as st
import pandas as pd

def create_dashboard(df: pd.DataFrame):
    """
    주어진 데이터프레임을 사용하여 특허 분석 대시보드를 생성합니다.
    """
    st.header("📊 분석 대시보드")
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
        # 연도별 출원 동향
        st.subheader("📈 연도별 출원 동향")
        df['application_year'] = pd.to_numeric(df['application_year'], errors='coerce')
        yearly_counts = df['application_year'].value_counts().sort_index()
        st.bar_chart(yearly_counts)

        # 핵심 출원인 (Top 10)
        st.subheader("🏢 핵심 출원인 (Top 10)")
        main_applicant = df['applicants'].str.split(';').str[0].str.strip()
        applicant_counts = main_applicant.value_counts().nlargest(10)
        st.bar_chart(applicant_counts)

    with col_graph2:
        # 출원인 국적 분포
        st.subheader("🌍 출원인 국적 분포 (Top 15)")
        nationality_counts = df['applicant_nationality'].value_counts().nlargest(15)
        st.bar_chart(nationality_counts)

        # 주요 기술 분야 (IPC) 분포
        st.subheader("🔬 주요 기술 분야 분포 (Top 15)")
        ipc_counts = df['main_ipc_field'].value_counts().nlargest(15)
        st.bar_chart(ipc_counts)
        st.caption("IPC(국제특허분류) 코드 4단위 기준")

    st.markdown("---")

    # --- 3. 상세 데이터 ---
    st.subheader("⭐ 가장 많이 인용된 특허 Top 10")
    top_cited_patents = df.sort_values(by='cited_by_patent_count', ascending=False).head(10)
    st.dataframe(top_cited_patents[['title', 'applicants', 'application_date', 'cited_by_patent_count']])