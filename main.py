import streamlit as st
import time
import datetime
import json

# 페이지 기본 설정
st.set_page_config(
    page_title="고교 모의고사 OMR & 타이머 웹앱",
    page_icon="📝",
    layout="wide"
)

# 세션 상태 초기화
if "notes" not in st.session_state:
    st.session_state.notes = {}  # 생성된 노트 저장소
if "current_note_id" not in st.session_state:
    st.session_state.current_note_id = None
if "test_status" not in st.session_state:
    st.session_state.test_status = "idle"  # idle, running, paused, finished
if "start_time" not in st.session_state:
    st.session_state.start_time = None
if "elapsed_time" not in st.session_state:
    st.session_state.elapsed_time = 0
if "user_answers" not in st.session_state:
    st.session_state.user_answers = {}

# 시험 프리셋 정의
PRESETS = {
    "국어": {"num_questions": 45, "time_limit": 80},
    "수학": {"num_questions": 30, "time_limit": 100},
    "영어": {"num_questions": 45, "time_limit": 70},
    "한국사/탐구": {"num_questions": 20, "time_limit": 30},
    "직접 설정": {"num_questions": 20, "time_limit": 30}
}

# -----------------------------------------------------------------------------
# 사이드바: 노트 관리 (새 노트 생성 / 기존 노트 선택)
# -----------------------------------------------------------------------------
st.sidebar.title("📚 시험 노트 관리")

menu = st.sidebar.radio("메뉴 선택", ["새 노트 생성", "기존 노트 열기"])

if menu == "새 노트 생성":
    st.sidebar.subheader("➕ 새 시험 노트")
    note_name = st.sidebar.text_input("노트 이름 (예: 2026학년도 6월 모의고사 국어)")
    
    if st.sidebar.button("노트 생성 시작"):
        if note_name:
            st.session_state.notes[note_name] = {
                "name": note_name,
                "pdf_file": None,
                "subject": "국어",
                "num_questions": 45,
                "time_limit": 80,
                "created_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
                "answers": {},
                "scores": {},
                "result": None
            }
            st.session_state.current_note_id = note_name
            st.success(f"'{note_name}' 노트를 생성했습니다!")
            st.rerun()
        else:
            st.sidebar.warning("노트 이름을 입력해주세요.")

elif menu == "기존 노트 열기":
    st.sidebar.subheader("📂 저장된 노트 목록")
    if len(st.session_state.notes) == 0:
        st.sidebar.info("저장된 노트가 없습니다.")
    else:
        selected_note = st.sidebar.selectbox("노트 선택", list(st.session_state.notes.keys()))
        if st.sidebar.button("노트 불러오기"):
            st.session_state.current_note_id = selected_note
            st.session_state.test_status = "idle"
            st.rerun()

st.sidebar.divider()

# -----------------------------------------------------------------------------
# 메인 화면
# -----------------------------------------------------------------------------
st.title("⏱️ 실제와 같은 고교 모의고사 시험장")

current_id = st.session_state.current_note_id

if not current_id or current_id not in st.session_state.notes:
    # 생성된 노트가 없을 때 화면 중심에 파일 업로드 안내
    st.markdown("### 📄 시작하려면 새 노트를 생성하고 시험지를 업로드하세요.")
    st.info("왼쪽 사이드바에서 '새 노트 생성'을 눌러 새로운 시험을 등록해 주세요.")
    
else:
    note_data = st.session_state.notes[current_id]
    st.subheader(f"📌 현재 노트: **{note_data['name']}**")

    # 1. 시험지 업로드 및 시험 정보 설정
    if note_data["pdf_file"] is None:
        st.markdown("---")
        st.write("#### 1. 시험지 PDF 파일 업로드")
        uploaded_file = st.file_uploader("PDF 파일만 업로드 가능합니다.", type=["pdf"])
        
        if uploaded_file is not None:
            note_data["pdf_file"] = uploaded_file
            st.success("PDF 파일이 올바르게 업로드되었습니다!")
            st.rerun()
            
    else:
        # 시험 상세 설정 (설정 전 단계)
        if st.session_state.test_status == "idle":
            with st.expander("⚙️ 시험 형식 및 시간 설정", expanded=True):
                preset_choice = st.selectbox("과목 프리셋 선택", list(PRESETS.keys()))
                
                col1, col2 = st.columns(2)
                with col1:
                    if preset_choice != "직접 설정":
                        num_q = st.number_input("문항 수", value=PRESETS[preset_choice]["num_questions"], min_value=1)
                        time_l = st.number_input("시험 시간 (분)", value=PRESETS[preset_choice]["time_limit"], min_value=1)
                    else:
                        num_q = st.number_input("문항 수", value=20, min_value=1)
                        time_l = st.number_input("시험 시간 (분)", value=30, min_value=1)
                
                with col2:
                    st.write("📄 **업로드된 파일**: ", note_data["pdf_file"].name)
                
                if st.button("🚀 시험 시작하기", type="primary"):
                    note_data["num_questions"] = num_q
                    note_data["time_limit"] = time_l
                    st.session_state.test_status = "running"
                    st.session_state.start_time = time.time()
                    st.session_state.elapsed_time = 0
                    st.rerun()

        # -----------------------------------------------------------------------------
        # 2. 시험 진행 중 (타이머, PDF 보기, OMR 카드)
        # -----------------------------------------------------------------------------
        if st.session_state.test_status in ["running", "paused"]:
            # 상단 우측 타이머 및 제어 버튼
            timer_col1, timer_col2, timer_col3 = st.columns([3, 2, 2])
            
            # 남은 시간 계산
            total_seconds = note_data["time_limit"] * 60
            remaining_seconds = max(0, int(total_seconds - st.session_state.elapsed_time))
            
            mins, secs = divmod(remaining_seconds, 60)
            hrs, mins = divmod(mins, 60)
            time_str = f"{hrs:02d}:{mins:02d}:{secs:02d}" if hrs > 0 else f"{mins:02d}:{secs:02d}"
            
            with timer_col1:
                st.metric(label="⏱️ 남은 시간", value=time_str)
            
            with timer_col2:
                if st.session_state.test_status == "running":
                    if st.button("⏸️ 일시 정지"):
                        st.session_state.test_status = "paused"
                        st.rerun()
                else:
                    if st.button("▶️ 다시 시작"):
                        st.session_state.test_status = "running"
                        st.rerun()
            
            with timer_col3:
                if st.button("🏁 시험 종료 및 제출", type="primary"):
                    st.session_state.test_status = "finished"
                    st.rerun()

            st.divider()

            # 레이아웃 분할: 왼쪽(시험지 PDF), 오른쪽(OMR 카드 토글)
            left_col, right_col = st.columns([3, 2])

            with left_col:
                st.subheader("📖 시험지")
                # PDF 미리보기 (브라우저 기본 PDF 뷰어 사용)
                pdf_bytes = note_data["pdf_file"].getvalue()
                st.download_button("💾 PDF 파일 다운로드", data=pdf_bytes, file_name=note_data["pdf_file"].name)
                
                # HTML embed 태그로 PDF 표시
                import base64
                base64_pdf = base64.b64encode(pdf_bytes).decode('utf-8')
                pdf_display = f'<iframe src="data:application/pdf;base64,{base64_pdf}" width="100%" height="700" type="application/pdf"></iframe>'
                st.markdown(pdf_display, unsafe_allow_html=True)

            with right_col:
                show_omr = st.toggle("📝 OMR 카드 펼치기/접기", value=True)
                
                if show_omr:
                    st.subheader("📋 OMR 마킹")
                    st.caption("객관식 답안을 입력하세요.")
                    
                    with st.form("omr_form"):
                        for q in range(1, note_data["num_questions"] + 1):
                            q_key = f"q_{q}"
                            st.session_state.user_answers[q] = st.radio(
                                f"{q}번 문항",
                                [1, 2, 3, 4, 5],
                                key=q_key,
                                horizontal=True,
                                index=st.session_state.user_answers.get(q, 1) - 1
                            )
                        st.form_submit_button("답안 임시 저장")

        # -----------------------------------------------------------------------------
        # 3. 시험 종료 후 (정답 입력, 채점, 오답노트 작성)
        # -----------------------------------------------------------------------------
        if st.session_state.test_status == "finished":
            st.success("🎉 시험이 종료되었습니다! 정답과 배점을 입력하여 채점하세요.")
            
            st.subheader("✏️ 정답 및 배점 입력 (자동 채점)")
            
            with st.form("grading_form"):
                grading_cols = st.columns(3)
                official_answers = {}
                question_scores = {}
                
                for q in range(1, note_data["num_questions"] + 1):
                    col_idx = (q - 1) % 3
                    with grading_cols[col_idx]:
                        st.write(f"**{q}번 문항** (제출한 답: {st.session_state.user_answers.get(q, '미제출')})")
                        ans = st.number_input(f"{q}번 정답", min_value=1, max_value=5, value=1, key=f"ans_{q}")
                        score = st.number_input(f"{q}번 배점", min_value=1, max_value=10, value=2, key=f"score_{q}")
                        official_answers[q] = ans
                        question_scores[q] = score
                
                submit_grade = st.form_submit_button("📊 채점하기")
            
            if submit_grade:
                # 채점 로직
                total_possible = sum(question_scores.values())
                user_score = 0
                wrong_questions = []

                for q in range(1, note_data["num_questions"] + 1):
                    u_ans = st.session_state.user_answers.get(q)
                    o_ans = official_answers[q]
                    if u_ans == o_ans:
                        user_score += question_scores[q]
                    else:
                        wrong_questions.append({
                            "no": q,
                            "user_ans": u_ans,
                            "correct_ans": o_ans,
                            "score": question_scores[q]
                        })

                note_data["result"] = {
                    "total_score": user_score,
                    "max_score": total_possible,
                    "wrong_questions": wrong_questions
                }
                st.rerun()

            # 채점 결과 출력
            if note_data["result"] is not None:
                res = note_data["result"]
                st.divider()
                st.header("📊 최종 결과")
                st.subheader(f"🎯 점수: **{res['total_score']} / {res['max_score']} 점**")
                
                res_col1, res_col2 = st.columns([2, 3])
                
                with res_col1:
                    st.subheader("❌ 틀린 문항 리스트")
                    if not res["wrong_questions"]:
                        st.balloons()
                        st.success("만점입니다! 틀린 문항이 없습니다.")
                    else:
                        for w in res["wrong_questions"]:
                            st.error(f"**{w['no']}번** (내 답: {w['user_ans']} / 정답: {w['correct_ans']}) - {w['score']}점")

                with res_col2:
                    st.subheader("📷 오답노트 작성 & 문항별 사진 캡처")
                    st.caption("틀린 문제 사진을 찍거나 첨부하여 오답노트로 모아보세요.")
                    
                    wrong_no = st.selectbox("오답 노트할 문항 선택", [w["no"] for w in res["wrong_questions"]] if res["wrong_questions"] else [1])
                    
                    img_file = st.file_uploader(f"{wrong_no}번 문제 이미지/사진 업로드", type=["png", "jpg", "jpeg"], key=f"img_{wrong_no}")
                    wrong_memo = st.text_area(f"{wrong_no}번 문제 오답 및 풀이 메모", key=f"memo_{wrong_no}")
                    
                    if st.button("오답노트에 저장"):
                        st.success(f"{wrong_no}번 문항 오답 노트가 저장되었습니다!")
