import streamlit as st
import time
import datetime
import fitz  # PyMuPDF
from PIL import Image
import io
import json
import tempfile
import os
from streamlit_drawable_canvas import st_canvas
from google import genai

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
    st.session_state.test_status = "idle"
if "start_time" not in st.session_state:
    st.session_state.start_time = None
if "elapsed_time" not in st.session_state:
    st.session_state.elapsed_time = 0
if "user_answers" not in st.session_state:
    st.session_state.user_answers = {}

PRESETS = {
    "국어": {"num_questions": 45, "time_limit": 80},
    "수학": {"num_questions": 30, "time_limit": 100},
    "영어": {"num_questions": 45, "time_limit": 70},
    "한국사/탐구": {"num_questions": 20, "time_limit": 30},
    "직접 설정": {"num_questions": 20, "time_limit": 30}
}

def get_default_scores(subject, num_questions):
    scores = {}
    if subject == "수학" and num_questions == 30:
        for q in range(1, 31):
            if q in [1, 2, 23]:
                scores[q] = 2
            elif q in [3, 4, 5, 6, 7, 8, 16, 17, 18, 19, 24, 25, 26, 27]:
                scores[q] = 3
            else:
                scores[q] = 4
    elif subject == "국어" and num_questions == 45:
        for q in range(1, 46):
            scores[q] = 3 if q in [5, 11, 17, 20, 25, 28, 33, 38, 41, 45] else 2
    else:
        for q in range(1, num_questions + 1):
            scores[q] = 2
    return scores

def get_default_q_types(subject, num_questions):
    q_types = {}
    for q in range(1, num_questions + 1):
        if subject == "수학" and q in [16, 17, 18, 19, 20, 21, 29, 30]:
            q_types[q] = "주관식"
        else:
            q_types[q] = "객관식"
    return q_types

def convert_pdf_to_images(pdf_bytes):
    images = []
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    for page in doc:
        pix = page.get_pixmap(dpi=150)
        img_data = pix.tobytes("png")
        img = Image.open(io.BytesIO(img_data))
        images.append(img)
    return images

# ✨ Gemini PDF / 이미지 겸용 답안 추출 함수
def extract_answers_from_file(file_bytes, file_name, num_questions, api_key):
    try:
        client = genai.Client(api_key=api_key)
        
        # 임시 파일로 저장 후 Gemini Files API로 업로드
        ext = os.path.splitext(file_name)[1].lower()
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as temp_file:
            temp_file.write(file_bytes)
            temp_path = temp_file.name

        # Gemini 서버에 파일 업로드 (PDF, PNG, JPG 모두 지원)
        uploaded_file = client.files.upload(file=temp_path)
        
        prompt = f"""
        이 문서/이미지에서 모의고사 정답과 배점을 읽어서 JSON 형식으로만 응답해줘.
        1번부터 {num_questions}번까지의 문항 정답(answer)과 배점(score)을 추출해줘.
        정답이 주관식 숫자면 숫자로, 객관식이면 1~5 사이의 숫자로 적어줘.
        응답 형식 예시:
        {{
          "1": {{"answer": 3, "score": 2}},
          "2": {{"answer": 12, "score": 3}}
        }}
        다른 설명 없이 오직 JSON 텍스트만 출력해줘.
        """
        
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[uploaded_file, prompt]
        )
        
        # 임시 파일 삭제
        os.remove(temp_path)
        
        res_text = response.text.strip().replace("```json", "").replace("```", "")
        return json.loads(res_text)
    except Exception as e:
        st.error(f"GenAI 답안 추출 중 오류 발생: {e}")
        return None

# 사이드바
st.sidebar.title("📚 시험 노트 관리")
api_key = st.sidebar.text_input("🔑 Google Gemini API Key", type="password", help="답지 자동 추출 기능을 위해 필요합니다.")
menu = st.sidebar.radio("메뉴 선택", ["새 노트 생성", "기존 노트 열기"])

if menu == "새 노트 생성":
    st.sidebar.subheader("➕ 새 시험 노트")
    note_name = st.sidebar.text_input("노트 이름 (예: 2026학년도 6월 모의고사 수학)")
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
                "q_types": {},
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

# 메인 화면
st.title("⏱️ 실제와 같은 고교 모의고사 시험장")
current_id = st.session_state.current_note_id

if not current_id or current_id not in st.session_state.notes:
    st.markdown("---")
    st.info("👈 왼쪽 사이드바에서 **'새 노트 생성'** 버튼을 눌러 새 모의고사를 시작하세요.")
else:
    note_data = st.session_state.notes[current_id]
    st.subheader(f"📌 현재 노트: **{note_data['name']}**")

    if note_data["pdf_bytes"] is None:
        st.markdown("---")
        st.write("### 📄 시험지 PDF 업로드")
        uploaded_file = st.file_uploader("PDF 파일만 업로드할 수 있습니다.", type=["pdf"])
        if uploaded_file is not None:
            with st.spinner("PDF를 터치 필기용 이미지로 변환 중입니다..."):
                pdf_bytes = uploaded_file.getvalue()
                images = convert_pdf_to_images(pdf_bytes)
                note_data["pdf_bytes"] = pdf_bytes
                note_data["pdf_name"] = uploaded_file.name
                note_data["pdf_images"] = images
            st.success("PDF 업로드 및 필기 환경 준비가 완료되었습니다!")
            st.rerun()

    else:
        if st.session_state.test_status == "idle":
            with st.expander("⚙️ 시험 과목 및 문항 유형 설정", expanded=True):
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
                
                st.divider()
                st.write("📋 **문항별 유형 설정 (객관식 / 주관식)**")
                default_types = get_default_q_types(preset_choice, num_q)
                type_cols = st.columns(5)
                configured_types = {}
                for q in range(1, num_q + 1):
                    c_idx = (q - 1) % 5
                    with type_cols[c_idx]:
                        configured_types[q] = st.selectbox(
                            f"{q}번 유형",
                            ["객관식", "주관식"],
                            index=0 if default_types.get(q, "객관식") == "객관식" else 1,
                            key=f"type_select_{q}"
                        )
                
                if st.button("🚀 시험 시작하기", type="primary", use_container_width=True):
                    note_data["subject"] = preset_choice
                    note_data["num_questions"] = num_q
                    note_data["time_limit"] = time_l
                    note_data["q_types"] = configured_types
                    st.session_state.test_status = "running"
                    st.session_state.start_time = time.time()
                    st.session_state.elapsed_time = 0
                    st.session_state.user_answers = {}
                    st.rerun()

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
                st.subheader("📝 시험지 터치 필기 노트")
                tool_col1, tool_col2, tool_col3 = st.columns(3)
                with tool_col1:
                    drawing_mode = st.selectbox("도구 선택", ["freedraw", "transform"], format_func=lambda x: "🖊️ 펜 필기" if x == "freedraw" else "✋ 이동/선택")
                with tool_col2:
                    stroke_color = st.color_picker("펜 색상", "#FF0000")
                with tool_col3:
                    stroke_width = st.slider("펜 두께", 1, 10, 2)

                total_pages = len(note_data["pdf_images"])
                page_idx = st.number_input("페이지 선택", min_value=1, max_value=total_pages, value=1) - 1
                
                target_img = note_data["pdf_images"][page_idx]
                img_width, img_height = target_img.size
                canvas_width = min(700, img_width)
                aspect_ratio = img_height / img_width
                canvas_height = int(canvas_width * aspect_ratio)

                st_canvas(
                    fill_color="rgba(255, 165, 0, 0.3)",
                    stroke_width=stroke_width,
                    stroke_color=stroke_color,
                    background_image=target_img,
                    update_streamlit=True,
                    height=canvas_height,
                    width=canvas_width,
                    drawing_mode=drawing_mode,
                    key=f"canvas_p_{page_idx}_{current_id}"
                )

            with right_col:
                show_omr = st.toggle("📝 OMR 카드 펼치기/접기", value=True)
                if show_omr:
                    st.subheader("📋 OMR 답안지")
                    with st.container(height=600):
                        for q in range(1, note_data["num_questions"] + 1):
                            q_type = note_data["q_types"].get(q, "객관식")
                            if q_type == "객관식":
                                st.session_state.user_answers[q] = st.radio(
                                    f"**{q}번 문항 (객관식)**",
                                    [1, 2, 3, 4, 5],
                                    key=f"omr_q_{q}",
                                    horizontal=True,
                                    index=int(st.session_state.user_answers.get(q, 1)) - 1
                                )
                            else:
                                st.session_state.user_answers[q] = st.text_input(
                                    f"**{q}번 문항 (주관식 정수 입력)**",
                                    value=str(st.session_state.user_answers.get(q, "")),
                                    key=f"omr_q_{q}"
                                )

            if remaining_seconds <= 0 and st.session_state.test_status == "running":
                st.session_state.test_status = "finished"
                st.toast("⏰ 시험 시간이 종료되었습니다!")
                st.rerun()

            if st.session_state.test_status == "running":
                time.sleep(1)
                st.session_state.elapsed_time += 1
                st.rerun()

        # 채점 단계 (PDF 답지 파싱 지원)
        if st.session_state.test_status == "finished":
            st.success("🎉 시험이 완료되었습니다!")
            
            st.subheader("🤖 Google GenAI 답지 자동 추출 (PDF / 이미지 지원)")
            st.caption("답지 PDF 또는 이미지 파일(PNG, JPG)을 업로드하면 AI가 정답과 배점을 자동으로 추출합니다.")
            
            # PDF 및 이미지 확장자 모두 허용
            ans_file = st.file_uploader("답지 파일 업로드 (PDF, PNG, JPG)", type=["pdf", "png", "jpg", "jpeg"])
            extracted_data = None
            
            if ans_file is not None:
                if not api_key:
                    st.warning("⚠️ 왼쪽 사이드바에 Google Gemini API Key를 입력해 주세요.")
                else:
                    if st.button("✨ 답지 파일에서 정답 추출하기"):
                        with st.spinner("Gemini AI가 답지 문서를 분석 중입니다..."):
                            extracted_data = extract_answers_from_file(
                                ans_file.getvalue(),
                                ans_file.name,
                                note_data["num_questions"],
                                api_key
                            )
                            if extracted_data:
                                st.success("정답 추출 성공! 아래 입력 창에 자동 세팅되었습니다.")

            st.divider()
            st.subheader("✏️ 정답 및 배점 확인/입력")
            
            default_scores = get_default_scores(note_data["subject"], note_data["num_questions"])
            
            with st.form("grading_form"):
                grading_cols = st.columns(3)
                official_answers = {}
                question_scores = {}
                
                for q in range(1, note_data["num_questions"] + 1):
                    col_idx = (q - 1) % 3
                    
                    ai_ans = None
                    ai_score = None
                    if extracted_data and str(q) in extracted_data:
                        ai_ans = extracted_data[str(q)].get("answer")
                        ai_score = extracted_data[str(q)].get("score")
                    
                    with grading_cols[col_idx]:
                        u_ans_display = st.session_state.user_answers.get(q, '미제출')
                        st.write(f"**{q}번 ({note_data['q_types'].get(q, '객관식')})** [마킹: {u_ans_display}]")
                        
                        default_ans = str(ai_ans) if ai_ans is not None else ("1" if note_data['q_types'].get(q) == "객관식" else "")
                        ans_val = st.text_input(f"{q}번 정답", value=default_ans, key=f"ans_input_{q}")
                        
                        default_score = str(ai_score) if ai_score is not None else str(default_scores.get(q, 2))
                        score_val = st.text_input(f"{q}번 배점", value=default_score, key=f"score_input_{q}")
                        
                        official_answers[q] = ans_val.strip()
                        try:
                            question_scores[q] = int(score_val.strip())
                        except ValueError:
                            question_scores[q] = 2
                
                submit_grade = st.form_submit_button("📊 채점하기", type="primary", use_container_width=True)
            
            if submit_grade:
                total_possible = sum(question_scores.values())
                user_score = 0
                wrong_questions = []

                for q in range(1, note_data["num_questions"] + 1):
                    u_ans = str(st.session_state.user_answers.get(q, "")).strip()
                    o_ans = str(official_answers[q]).strip()
                    
                    if u_ans == o_ans and u_ans != "":
                        user_score += question_scores[q]
                    else:
                        wrong_questions.append({
                            "no": q,
                            "user_ans": u_ans if u_ans != "" else "미제출",
                            "correct_ans": o_ans,
                            "score": question_scores[q]
                        })

                note_data["result"] = {
                    "total_score": user_score,
                    "max_score": total_possible,
                    "wrong_questions": wrong_questions
                }
                st.rerun()

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
                            st.error(f"**{w['no']}번** (내 답: {w['user_ans']} / 정답: {w['correct_ans']}) - [{w['score']}점 차감]")

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
