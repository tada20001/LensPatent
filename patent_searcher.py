import requests
import json
from datetime import datetime
import os
import csv
import time
import tempfile

# ==============================================================================
#  1. 최종 데이터 파싱 함수 (parse_patent)
# ==============================================================================
def parse_patent(patent_json):
    """(No More Hiding - Final) 모든 분석 지표와 그 근거 데이터를 함께 저장합니다."""

    # --- 원본 객체 선언 ---
    biblio = patent_json.get('biblio', {})
    legal = patent_json.get('legal_status', {})
    parties = biblio.get('parties', {})
    application_ref = biblio.get('application_reference', {})
    families = patent_json.get('families', {})

    # --- 원본 데이터 추출 ---
    applicants_list = parties.get('applicants', [])
    inventors_list = parties.get('inventors', [])
    ipc_list = biblio.get('classifications_ipcr', {}).get('classifications', [])
    cpc_list = biblio.get('classifications_cpc', {}).get('classifications', [])
    priority_claims = biblio.get('priority_claims', {}).get('claims', [])
    references_cited = biblio.get('references_cited', {})
    cited_by = biblio.get('cited_by', {})

    application_date_str = application_ref.get('date')
    publication_date_str = patent_json.get('date_published')
    grant_date_str = legal.get('grant_date')
    abstract_list = patent_json.get('abstract', [])
    abstract_text = abstract_list[0].get('text') if abstract_list else None

    original_applicant_residence = applicants_list[0].get('residence') if applicants_list else None
    original_priority_country = priority_claims[0].get('jurisdiction') if priority_claims else None

    # --- 가공된 분석 지표 생성 ---
    final_applicant_nationality = original_applicant_residence or original_priority_country or 'N/A'
    application_year = application_date_str[:4] if application_date_str else 'N/A'
    main_ipc_field = ipc_list[0].get('symbol')[:4] if ipc_list else 'N/A'
    num_applicants = len(applicants_list)
    is_co_owned = num_applicants > 1

    time_to_grant_days = None
    if grant_date_str and application_date_str:
        try:
            time_to_grant_days = (datetime.strptime(grant_date_str, "%Y-%m-%d") - datetime.strptime(application_date_str, "%Y-%m-%d")).days
        except: pass

    cited_by_patent_count = cited_by.get('patent_count', 0)
    citations_per_year = 0.0
    if cited_by_patent_count > 0 and publication_date_str:
        try:
            citations_per_year = cited_by_patent_count / (datetime.now().year - int(publication_date_str[:4]) + 1)
        except: pass

    citation_patent_count = references_cited.get('patent_count', 0)
    citation_npl_count = references_cited.get('npl_count', 0)
    total_citations = citation_patent_count + citation_npl_count
    science_linkage_ratio = (citation_npl_count / total_citations) if total_citations > 0 else 0.0

    # --- 최종 반환 딕셔너리 (모든 정보 포함 및 순서 재정렬) ---
    return {
        # === 1. 핵심 내용 ===
        'title': biblio.get('invention_title', [{}])[0].get('text'),
        'abstract': abstract_text,
        'applicants': '; '.join([p.get('extracted_name', {}).get('value', '') for p in applicants_list]),
        'inventors': '; '.join([p.get('extracted_name', {}).get('value', '') for p in inventors_list]),

        # === 2. 주요 날짜 및 연도 ===
        'application_date': application_date_str,
        'publication_date': publication_date_str,
        'grant_date': grant_date_str,
        'application_year': application_year,

        # === 3. 식별 번호 및 국가/분류 ===
        'publication_number': patent_json.get('doc_number'),
        'application_number': application_ref.get('doc_number'),
        'jurisdiction': patent_json.get('jurisdiction'),
        'applicant_nationality': final_applicant_nationality,
        'SOURCE_applicant_residence': original_applicant_residence,
        'SOURCE_priority_country': original_priority_country,
        'main_ipc_field': main_ipc_field,
        'ipc_classifications': '; '.join([c.get('symbol') for c in ipc_list]),
        'cpc_classifications': '; '.join([c.get('symbol') for c in cpc_list]),
        'lens_id': patent_json.get('lens_id'),

        # === 4. 상태 및 품질 지표 ===
        'is_granted': legal.get('granted'),
        'patent_status': legal.get('patent_status'),
        'cited_by_patent_count': cited_by_patent_count,
        'citation_patent_count': citation_patent_count,
        'citation_npl_count': citation_npl_count,
        'total_citations': total_citations,
        'citations_per_year': round(citations_per_year, 2),
        'science_linkage_ratio': round(science_linkage_ratio, 2),
        'time_to_grant_days': time_to_grant_days,
        'num_applicants': num_applicants,
        'is_co_owned': is_co_owned,
        'simple_family_size': families.get('simple_family', {}).get('size'),

        # === 5. 원본 데이터 ===
        'raw_json': json.dumps(patent_json, ensure_ascii=False)
    }
# ==============================================================================
#  2. 최종 검색 엔진 함수 (build_query)
# ==============================================================================
def build_query(search_params):
    query_type = search_params.get("query_type", "simple")
    search_term = search_params.get("search_term", "").strip()

    if query_type == 'advanced' and search_term:
        return {"query_string": {"query": search_term}}

    must_clauses = []

    if search_term and search_params.get('search_fields'):
        processed_term = " OR ".join(f'"{p}"' if ' ' in p else p for p in search_term.split())
        must_clauses.append({"query_string": {"query": f"({processed_term})", "fields": search_params['search_fields']}})
    if search_params.get("applicant"):
        must_clauses.append({"match": {"applicant.name": search_params["applicant"]}})
    if search_params.get("ipc_cpc"):
        codes = search_params["ipc_cpc"].upper().split()
        codes_query = " OR ".join(codes)
        must_clauses.append({"query_string": {"query": f"({codes_query})", "fields": ["class_cpc.symbol", "class_ipcr.symbol"]}})
    start_year, end_year = search_params.get("start_year"), search_params.get("end_year")
    if (start_year and start_year.isdigit()) or (end_year and end_year.isdigit()):
        date_type = search_params.get("date_type", "application")
        api_date_field = "legal_status.grant_date" if date_type == 'grant' else "application_reference.date"
        date_range_query = {}
        if start_year and start_year.isdigit(): date_range_query["gte"] = f"{start_year}-01-01"
        if end_year and end_year.isdigit(): date_range_query["lte"] = f"{end_year}-12-31"
        if date_range_query:
            must_clauses.append({"range": {api_date_field: date_range_query}})
    if search_params.get("status_filter") == "granted":
        must_clauses.append({"term": {"legal_status.granted": True}})

    return {"bool": {"must": must_clauses}} if must_clauses else {"match_all": {}}


# ==============================================================================
#  3. API 호출 함수 (기존 함수는 첫 페이지만 가져오는 용도로 유지)
# ==============================================================================
def search_first_page(api_key, search_params, size):
    """(수정 완료) 검색 조건과 사용자가 지정한 'size'를 받아 첫 페이지만 가져옵니다."""

    query = build_query(search_params)
    API_URL = "https://api.lens.org/patent/search"
    headers = {'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'}

    # ★★★ 제 멋대로 넣었던 기본값을 삭제하고, 인자로 받은 size를 사용합니다 ★★★
    payload = {
        "query": query,
        "size": size,
        "include": ["lens_id", "jurisdiction", "doc_number", "date_published", "biblio", "legal_status", "families", "abstract"]
    }

    try:
        response = requests.post(API_URL, headers=headers, data=json.dumps(payload))
        response.raise_for_status()
        results_json = response.json()
        total_results = results_json.get('total', 0)
        parsed_data = [parse_patent(p) for p in results_json.get('data', [])]
        return parsed_data, total_results, None

    except requests.exceptions.HTTPError as e:
        try:
            error_details = e.response.json()
            error_message = f"API 에러 ({e.response.status_code}): {error_details.get('message', e.response.text)}"
        except json.JSONDecodeError:
            error_message = f"API 에러 ({e.response.status_code}): {e.response.text}"
        return None, 0, error_message

    except Exception as e:
        return None, 0, f"예상치 못한 에러 발생: {str(e)}"

# ==============================================================================
#  새로운 함수: 총 건수만 확인하는 기능
# ==============================================================================
def get_total_hits(api_key, search_params):
    """(size=0) 검색 조건에 해당하는 총 결과 건수만 빠르게 확인합니다."""

    query = build_query(search_params)
    API_URL = "https://api.lens.org/patent/search"
    headers = {'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'}

    # ★★★ size를 0으로 설정하여, 데이터 본문 없이 total 값만 요청 ★★★
    payload = {
        "query": query,
        "size": 0
    }

    try:
        response = requests.post(API_URL, headers=headers, data=json.dumps(payload))
        response.raise_for_status()

        total_hits = response.json().get('total', 0)
        return total_hits, None # 성공: (총 건수, 에러 없음)

    except requests.exceptions.HTTPError as e:
        try:
            error_details = e.response.json()
            error_message = f"API 에러 ({e.response.status_code}): {error_details.get('message', e.response.text)}"
        except json.JSONDecodeError:
            error_message = f"API 에러 ({e.response.status_code}): {e.response.text}"
        return None, error_message # 실패: (총 건수 없음, 에러 메시지)

    except Exception as e:
        return None, f"예상치 못한 에러 발생: {str(e)}"


# ==============================================================================
#  4. ★★★ 전체 결과를 임시 CSV 파일에 저장하는 단 하나의 메인 함수 ★★★
# ==============================================================================
# ==============================================================================
#  전체 결과를 임시 CSV 파일에 저장하는 함수 (Rate Limit 준수)
# ==============================================================================
def save_all_patents_to_csv(api_key, search_params, progress_callback=None):
    """(최종 수정) 안정성과 효율성을 개선한 전체 결과 저장 함수입니다."""

    query = build_query(search_params)
    API_URL = "https://api.lens.org/patent/search"
    headers = {'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'}

    temp_file = tempfile.NamedTemporaryFile(mode='w+', delete=False, newline='', encoding='utf-8-sig')
    temp_filename = temp_file.name

    # 첫 번째 요청 페이로드
    payload = {
        "query": query, "size": 100, "scroll": "1m",
        "include": ["lens_id", "jurisdiction", "doc_number", "date_published", "biblio", "legal_status", "families", "abstract"]
    }

    start_time = time.time()
    csv_writer = None
    num_processed = 0
    limit = 50000

    try:
        # 1. 첫 번째 요청
        response = requests.post(API_URL, headers=headers, data=json.dumps(payload), timeout=30)
        response.raise_for_status()
        data = response.json()

        total_hits = data.get('total', 0)
        scroll_id = data.get('scroll_id')
        patents = data.get('data', [])

        if not patents:
            temp_file.close(); os.remove(temp_filename)
            return None, 0, "검색 결과가 없습니다."

        # --- while 루프로 모든 로직 통합 ---
        while True:
            # 2. 데이터 처리 및 CSV 쓰기
            if patents:
                # 첫 번째 데이터 묶음일 때만 헤더를 씀
                if csv_writer is None:
                    first_patent_parsed = parse_patent(patents[0])
                    csv_writer = csv.DictWriter(temp_file, fieldnames=first_patent_parsed.keys())
                    csv_writer.writeheader()
                    csv_writer.writerow(first_patent_parsed)
                    # 이미 쓴 첫 번째 데이터를 제외하고 나머지 처리
                    for p in patents[1:]:
                        csv_writer.writerow(parse_patent(p))
                else: # 두 번째 묶음부터는 데이터만 씀
                    for p in patents:
                        csv_writer.writerow(parse_patent(p))

                num_processed += len(patents)

            # 3. 진행 상황 업데이트
            if progress_callback:
                elapsed_time = time.time() - start_time
                total_to_download = min(total_hits, limit)
                progress_callback(num_processed, total_to_download, elapsed_time)

            # 4. 종료 조건 확인
            if not patents or not scroll_id or num_processed >= limit:
                break

            # 5. 다음 페이지 요청 (속도 조절 및 재시도 포함)
            time.sleep(1)
            scroll_payload = {"scroll_id": scroll_id, "scroll": "1m"}

            try:
                response = requests.post(API_URL, headers=headers, data=json.dumps(scroll_payload), timeout=30)
                if response.status_code == 204: break # 정상 종료
                response.raise_for_status()
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 429:
                    print("Warning: 429 Rate Limit. 10초간 대기 후 재시도...")
                    time.sleep(10)
                    # 다음 루프에서 같은 scroll_id로 다시 시도하게 됨
                    # patents는 비어있지 않으므로 루프는 계속됨
                    continue
                else:
                    raise e # 다른 HTTP 에러는 바깥의 except로 던짐

            data = response.json()
            scroll_id = data.get('scroll_id')
            patents = data.get('data', [])

        temp_file.close()
        return temp_filename, total_hits, None

    except Exception as e:
        if 'temp_file' in locals() and not temp_file.closed:
            temp_file.close()
        if 'temp_filename' in locals() and os.path.exists(temp_filename):
            os.remove(temp_filename)
        return None, 0, f"Error: {e}"