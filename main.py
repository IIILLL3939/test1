import streamlit as st
import time
import datetime
import fitz  # PyMuPDF: PDF를 이미지로 변환하여 학교 차단 방지
from PIL import Image
import io

# 페이지 기본 설정
st.set_page_config(
    page_title="고교 모의고사 OMR & 타이머 웹앱",
    page_icon="📝",
    layout="wide"
)

# 세션 상태 초기화
if "notes" not in st.session_state:
    st.session_state.notes = {}
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

# 과목별 기본 프레임워크 (문항 수, 시험 시간)
PRESETS = {
    "국어": {"num_questions": 45, "time_limit": 80},
    "수학": {"num_questions": 30, "time_limit": 100},
    "영어": {"num_questions": 45, "time_limit": 70},
    "한국사/탐구": {"num_questions": 20, "time_limit": 30},
    "직접 설정": {"num_questions": 20, "time_limit": 30}
}

# 과목별 수능 표준 기본 배점 생성 함수
def get_default_scores(subject, num_questions):
    scores = {}
    if subject == "수학" and num_questions == 30:
        # 수학 수능 표준 배점 (2점, 3점, 4점 자동 배치)
        for q in range(1, 31):
            if q in [1, 2, 23]:
                scores[q] = 2
            elif q in [3, 4, 5, 6, 7, 8, 16, 17, 18, 19, 24, 25, 26, 27]:
                scores[q] = 3
            else:  # 9~15, 20~22, 28~30 (킬러/준킬러 문항)
                scores[q] = 4
    elif subject == "국어" and num_questions == 45:
        # 국어 기본 2점 (일부 3점 문항은 채점 시 변경 가능)
        for q in range(1, 46):
            scores[q] = 3 if q in [5, 11, 17, 20, 25, 28, 33, 38, 41, 45] else 2
    else:
        # 기타 과목 기본 2점 균일 배점
        for q in range(1, num_questions + 1):
            scores[q] = 2
    return scores

# PDF 파일을 PNG 이미지 리스트로 변환 (학교 크롬 네트워크 차단 회피)
def convert_pdf_to_images(pdf_bytes):
    images = []
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    for page in doc:
        pix = page.get_pixmap(dpi=150)
        img_data = pix.tobytes("png")
        img = Image.open(io.BytesIO(img_data))
        images.append(img)
    return images

# -----------------------------------------------------------------------------
# 사이드바: 노트 관리
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
                "pdf_bytes": None,
                "pdf_name": "",
                "pdf_images": [],
                "subject": "국어",
                "num_questions": 45,
                "time_limit": 80,
                "created_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
                "result": None
            }
            st.session_state.current_note_id = note_name
            st.session_state.test_status = "idle"
            st.session_state.user_answers = {}
            st.session_state.elapsed_time = 0
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
            st.session_state.user_answers = {}
            st.session_state.elapsed_time = 0
            st.rerun()

st.sidebar.divider()

# -----------------------------------------------------------------------------
# 메인 화면
# -----------------------------------------------------------------------------
st.title("⏱️ 실제와 같은 고교 모의고사 시험장")

current_id = st.session_state.current_note_id

if not current_id or current_id not in st.session_state.notes:
    st.markdown("---")
    st.info("👈 왼쪽 사이드바에서 **'새 노트 생성'** 버튼을 눌러 새 모의고사를 시작하세요.")
else:
    note_data = st.session_state.notes[current_id]
    st.subheader(f"📌 현재 노트: **{note_data['name']}**")

    # 1. 파일 업로드 단계
    if note_data["pdf_bytes"] is None:
        st.markdown("---")
        st.write("### 📄 시험지 PDF 업로드")
        uploaded_file = st.file_uploader("PDF 파일만 업로드할 수 있습니다.", type=["pdf"])
        
        if uploaded_file is not None:
            with st.spinner("학교 차단 방지를 위해 PDF를 이미지로 변환 중입니다..."):
                pdf_bytes = uploaded_file.getvalue()
                images = convert_pdf_to_images(pdf_bytes)
                
                note_data["pdf_bytes"] = pdf_bytes
                note_data["pdf_name"] = uploaded_file.name
                note_data["pdf_images"] = images
                
            st.success("PDF 업로드 및 이미지 변환이 완료되었습니다!")
            st.rerun()

    else:
        # 2. 과목 선택 및 시험 상세 설정 단계
        if st.session_state.test_status == "idle":
            with st.expander("⚙️ 시험 과목/배점 프리셋 설정", expanded=True):
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
                    st.write("📄 **업로드된 파일**: ", note_data["pdf_name"])
                    st.write("📑 **총 페이지 수**: ", len(note_data["pdf_images"]), "페이지")
                    st.info("💡 선택한 과목의 수능 표준 문항별 배점(2점, 3점, 4점)이 자동 설정됩니다.")
                
                if st.button("🚀 시험 시작하기", type="primary", use_container_width=True):
                    note_data["subject"] = preset_choice
                    note_data["num_questions"] = num_q
                    note_data["time_limit"] = time_l
                    st.session_state.test_status = "running"
                    st.session_state.start_time = time.time()
                    st.session_state.elapsed_time = 0
                    st.session_state.user_answers = {q: 1 for q in range(1, num_q + 1)}
                    st.rerun()

        # -----------------------------------------------------------------------------
        # 3. 시험 진행 중 (타이머, 시험지, OMR)
        # -----------------------------------------------------------------------------
        if st.session_state.test_status in ["running", "paused"]:
            timer_col, btn_col1, btn_col2 = st.columns([3, 2, 2])
            
            total_seconds = note_data["time_limit"] * 60
            remaining_seconds = max(0, int(total_seconds - st.session_state.elapsed_time))
            
            mins, secs = divmod(remaining_seconds, 60)
            hrs, mins = divmod(mins, 60)
            time_str = f"{hrs:02d}:{mins:02d}:{secs:02d}" if hrs > 0 else f"{mins:02d}:{secs:02d}"
            
            with timer_col:
                st.metric(label="⏱️ 남은 시간", value=time_str)
            
            with btn_col1:
                if st.session_state.test_status == "running":
                    if st.button("⏸️ 일시 정지", use_container_width=True):
                        st.session_state.test_status = "paused"
                        st.rerun()
                else:
                    if st.button("▶️ 다시 시작", use_container_width=True):
                        st.session_state.test_status = "running"
                        st.rerun()
            
            with btn_col2:
                if st.button("🏁 시험 종료 및 제출", type="primary", use_container_width=True):
                    st.session_state.test_status = "finished"
                    st.rerun()

            st.divider()

            left_col, right_col = st.columns([3, 2])

            with left_col:
                st.subheader("📖 시험지")
                for idx, img in enumerate(note_data["pdf_images"]):
                    st.image(img, caption=f"페이지 {idx + 1}", use_container_width=True)

            with right_col:
                show_omr = st.toggle("📝 OMR 카드 펼치기/접기", value=True)
                
                if show_omr:
                    st.subheader("📋 OMR 답안지")
                    st.caption("답안을 선택하세요 (자동 저장됨)")
                    
                    with st.container(height=600):
                        for q in range(1, note_data["num_questions"] + 1):
                            st.session_state.user_answers[q] = st.radio(
                                f"**{q}번 문항**",
                                [1, 2, 3, 4, 5],
                                key=f"omr_q_{q}",
                                horizontal=True,
                                index=st.session_state.user_answers.get(q, 1) - 1
                            )

            if remaining_seconds <= 0 and st.session_state.test_status == "running":
                st.session_state.test_status = "finished"
                st.toast("⏰ 시험 시간이 종료되었습니다!")
                st.rerun()

            if st.session_state.test_status == "running":
                time.sleep(1)
                st.session_state.elapsed_time += 1
                st.rerun()

        # -----------------------------------------------------------------------------
        # 4. 시험 종료 및 자동 채점 (기본 배점 자동 적용)
        # -----------------------------------------------------------------------------
        if st.session_state.test_status == "finished":
            st.success("🎉 시험이 완료되었습니다! 선택한 과목의 **기본 배점이 자동 설정**되었습니다. 필요 시 수정 후 채점하세요.")
            
            # 과목별 기본 배점 자동 로드
            default_scores = get_default_scores(note_data["subject"], note_data["num_questions"])
            
            st.subheader("✏️ 정답 및 배점 확인/수정")
            
            with st.form("grading_form"):
                grading_cols = st.columns(3)
                official_answers = {}
                question_scores = {}
                
                for q in range(1, note_data["num_questions"] + 1):
                    col_idx = (q - 1) % 3
                    with grading_cols[col_idx]:
                        st.write(f"**{q}번 문항** (마킹 답: **{st.session_state.user_answers.get(q, '미제출')}**)")
                        ans = st.number_input(f"{q}번 정답", min_value=1, max_value=5, value=1, key=f"ans_{q}")
                        
                        # 자동 설정된 기본 배점값을 value로 들어감
                        score = st.number_input(
                            f"{q}번 배점", 
                            min_value=1, 
                            max_value=10, 
                            value=default_scores.get(q, 2), 
                            key=f"score_{q}"
                        )
                        
                        official_answers[q] = ans
                        question_scores[q] = score
                
                submit_grade = st.form_submit_button("📊 채점하기", type="primary", use_container_width=True)
            
            if submit_grade:
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
                st.header("📊 최종 채점 결과")
                st.metric(label="🎯 최종 점수", value=f"{res['total_score']} / {res['max_score']} 점")
                
                res_col1, res_col2 = st.columns([1, 1])
                
                with res_col1:
                    st.subheader("❌ 틀린 문항 분석")
                    if not res["wrong_questions"]:
                        st.balloons()
                        st.success("👏 축하합니다! 만점입니다.")
                    else:
                        for w in res["wrong_questions"]:
                            st.error(f"**{w['no']}번** (내가 찍은 답: {w['user_ans']} / 정답: {w['correct_ans']}) - [{w['score']}점 차감]")

                with res_col2:
                    st.subheader("📷 오답 노트 및 문제 캡처")
                    if res["wrong_questions"]:
                        wrong_no = st.selectbox(
                            "오답 메모를 작성할 문항 선택",
                            [w["no"] for w in res["wrong_questions"]]
                        )
                        
                        img_file = st.file_uploader(f"{wrong_no}번 문제 사진 업로드", type=["png", "jpg", "jpeg"], key=f"img_{wrong_no}")
                        if img_file:
                            st.image(img_file, caption=f"{wrong_no}번 문제 캡처", width=300)
                            
                        wrong_memo = st.text_area(f"{wrong_no}번 오답 메모 및 풀이 분석", key=f"memo_{wrong_no}")
                        
                        if st.button("💾 해당 오답 저장"):
                            st.success(f"{wrong_no}번 문항의 오답 노트 저장이 완료되었습니다!")
                    else:
                        st.info("틀린 문항이 없어 오답 노트를 작성할 필요가 없습니다.")
