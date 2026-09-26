import io
import hashlib
import pandas as pd
import streamlit as st
from supabase import create_client, Client

# --- SUPABASE CONNECTION SETUP ---
SUPABASE_URL = st.secrets.get("supabase_url", "")
SUPABASE_KEY = st.secrets.get("supabase_key", "")

@st.cache_resource
def get_supabase_client() -> Client:
    if not SUPABASE_URL or not SUPABASE_KEY:
        st.error("❌ Supabase secrets are missing! Check your secrets.toml file.")
        st.stop()
    return create_client(SUPABASE_URL, SUPABASE_KEY)

# Prevent crashing if secrets aren't set during initial staging
try:
    supabase = get_supabase_client()
except SystemExit:
    st.warning("⚠️ Application is running in unconfigured mode. Please add Supabase secrets to proceed.")

REQUIRED_COLUMNS = ["id", "class", "subject", "period", "semester", "grade", "password_hash"]

def hash_password(password: str) -> str:
    """Hash password string using SHA-256."""
    return hashlib.sha256(password.encode()).hexdigest()

# --- STREAMLIT UI SETUP ---
st.set_page_config(page_title="Academic Records Portal", layout="wide")
st.title("🏫 Academic Records Portal")
st.write("Welcome to the Student and Admin Grades Management System.")

tab_student, tab_admin = st.tabs(["🎓 Student Portal", "🔐 Admin Dashboard"])

# --- STUDENT PORTAL ---
with tab_student:
    st.header("Student Grade Inquiry")
    
    col_input1, col_input2 = st.columns(2)
    with col_input1:
        student_id = st.text_input("Enter Student ID:", key="stu_id_input").strip()
    with col_input2:
        student_pass = st.text_input("Enter Password:", type="password", key="stu_pass_input").strip()
    
    auth_key = f"authenticated_{student_id}"
    
    if st.button("Access Dashboard", key="btn_student_login"):
        if student_id and student_pass:
            hashed_input = hash_password(student_pass)
            
            try:
                response = supabase.table("reportcard") \
                    .select("id") \
                    .eq("id", student_id) \
                    .eq("password_hash", hashed_input) \
                    .execute()
                
                if response.data:
                    st.success(f"✅ Welcome Back, Student ID: {student_id}")
                    st.session_state[auth_key] = True
                else:
                    st.error("❌ Invalid Student ID or Password.")
                    st.session_state[auth_key] = False
            except Exception as e:
                st.error(f"❌ Database error: {str(e)}")
        else:
            st.warning("⚠️ Both Student ID and Password are required.")

    if st.session_state.get(auth_key, False):
        try:
            student_data = supabase.table("reportcard").select("*").eq("id", student_id).execute()
            student_rows = pd.DataFrame(student_data.data)
            
            if not student_rows.empty:
                student_rows['grade'] = pd.to_numeric(student_rows['grade'], errors='coerce')
                
                col_f1, col_f2 = st.columns(2)
                with col_f1:
                    semesters = ["All Semesters"] + sorted(student_rows['semester'].dropna().astype(str).unique().tolist())
                    selected_semester = st.selectbox("Filter by Semester", semesters, key="student_sem_filter")
                with col_f2:
                    periods = ["All Periods"] + sorted(student_rows['period'].dropna().astype(str).unique().tolist())
                    selected_period = st.selectbox("Filter by Period", periods, key="student_per_filter")
                
                filtered_df = student_rows.copy()
                if selected_semester != "All Semesters":
                    filtered_df = filtered_df[filtered_df['semester'].astype(str) == selected_semester]
                if selected_period != "All Periods":
                    filtered_df = filtered_df[filtered_df['period'].astype(str) == selected_period]
                    
                st.subheader("📊 Academic Performance Summary")
                metric_col1, metric_col2, metric_col3 = st.columns(3)
                
                current_avg = filtered_df['grade'].mean()
                with metric_col1:
                    if pd.isna(current_avg):
                        st.metric(label="Current Filtered Average", value="N/A")
                    else:
                        st.metric(label="Current Filtered Average", value=f"{current_avg:.2f}%")
                        
                with metric_col2:
                    st.markdown("**Average by Semester**")
                    sem_avg = student_rows.groupby('semester')['grade'].mean().reset_index()
                    for _, row in sem_avg.iterrows():
                        st.write(f"• **{row['semester']}**: {row['grade']:.2f}%")
                        
                with metric_col3:
                    st.markdown("**Average by Period**")
                    per_avg = student_rows.groupby('period')['grade'].mean().reset_index()
                    for _, row in per_avg.iterrows():
                        st.write(f"• **{row['period']}**: {row['grade']:.2f}%")
                
                st.divider()
                st.subheader("Your Academic Record Matrix")
                
                display_df = filtered_df.drop(columns=['password_hash', 'created_at'], errors='ignore')
                cls_val = display_df['class'].iloc[0] if not display_df.empty and 'class' in display_df.columns else "N/A"
                avg_str = f"{current_avg:.2f}%" if not pd.isna(current_avg) else "N/A"
                
                if not display_df.empty:
                    try:
                        pivot_df = display_df.pivot_table(
                            index='subject',
                            columns=['semester', 'period'],
                            values='grade',
                            aggfunc='mean'
                        )
                        pivot_df['Subject Average'] = pivot_df.mean(axis=1)
                        
                        st.dataframe(
                            pivot_df.style.format("{:.2f}%", na_rep="-"),
                            use_container_width=True
                        )
                        
                    except Exception as pivot_err:
                        st.error(f"❌ Could not build matrix layout: {str(pivot_err)}")
                        st.dataframe(display_df, use_container_width=True)
                        pivot_df = None
                else:
                    st.info("💡 No records match the selected filters.")
                    pivot_df = None
                
                # --- EXPORT & DOWNLOAD ---
                st.divider()
                st.subheader("📥 Download Clean Report Documents")
                dl_col1, dl_col2, dl_col3 = st.columns(3)
                
                # 1. DOWNLOAD DATA (CSV)
                with dl_col1:
                    csv_buffer = io.StringIO()
                    if pivot_df is not None:
                        pivot_df.to_csv(csv_buffer)
                    else:
                        display_df.to_csv(csv_buffer, index=False)
                        
                    st.download_button(
                        label="📊 Download CSV Dataset",
                        data=csv_buffer.getvalue(),
                        file_name=f"Transcript_Matrix_{student_id}.csv",
                        mime="text/csv",
                        key="dl_student_csv"
                    )
                    
                # 2. EXPORT TO OFFICIAL DESIGNER PDF (ReportLab)
                with dl_col2:
                    from reportlab.lib.pagesizes import letter
                    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
                    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
                    from reportlab.lib import colors

                    pdf_buffer = io.BytesIO()
                    doc = SimpleDocTemplate(pdf_buffer, pagesize=letter, title="Official Transcript")
                    story = []
                    styles = getSampleStyleSheet()

                    title_style = ParagraphStyle(
                        'ReportTitle',
                        parent=styles['Heading1'],
                        fontSize=22,
                        leading=26,
                        alignment=1,
                        textColor=colors.HexColor('#1A365D'),
                        spaceAfter=15
                    )
                    meta_style = ParagraphStyle(
                        'MetaText',
                        parent=styles['Normal'],
                        fontSize=11,
                        leading=16,
                        textColor=colors.HexColor('#2D3748')
                    )

                    story.append(Paragraph("OFFICIAL TRANSCRIPT REPORT", title_style))
                    story.append(Spacer(1, 10))

                    story.append(Paragraph(f"<b>Student ID:</b> {student_id}", meta_style))
                    story.append(Paragraph(f"<b>Class:</b> {cls_val}", meta_style))
                    story.append(Paragraph(f"<b>Filters:</b> {selected_semester} | {selected_period}", meta_style))
                    story.append(Paragraph(f"<b>Overall Filtered Average:</b> {avg_str}", meta_style))
                    story.append(Spacer(1, 20))

                    if pivot_df is not None:
                        matrix_data = [["Subject"] + [f"{col[0]} - {col[1]}" if isinstance(col, tuple) else str(col) for col in pivot_df.columns]]
                        for idx, row in pivot_df.iterrows():
                            formatted_row = [str(idx)] + [f"{val:.2f}%" if pd.notna(val) else "-" for val in row]
                            matrix_data.append(formatted_row)
                        
                        t = Table(matrix_data, hAlign='LEFT')
                        t.setStyle(TableStyle([
                            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1A365D')),
                            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                            ('ALIGN', (0, 0), (0, -1), 'LEFT'),
                            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                            ('FONTSIZE', (0, 0), (-1, 0), 10),
                            ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
                            ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#F7FAFC')),
                            ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#E2E8F0')),
                            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                            ('FONTSIZE', (0, 1), (-1, -1), 9),
                            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F7FAFC')])
                        ]))
                        story.append(t)
                    else:
                        story.append(Paragraph("No academic record matrix available.", meta_style))

                    doc.build(story)
                    pdf_buffer.seek(0)

                    st.download_button(
                        label="📄 Download Official PDF Report",
                        data=pdf_buffer,
                        file_name=f"Official_Transcript_{student_id}.pdf",
                        mime="application/pdf",
                        key="dl_student_pdf"
                    )

            else:
                st.info("💡 No grade records found for this student ID.")
        except Exception as err:
            st.error(f"❌ Error fetching student details: {str(err)}")

# --- ADMIN DASHBOARD ---
with tab_admin:
    st.header("Admin Control Dashboard")
    
    admin_password = st.secrets.get("ADMIN_PASSWORD", "admin123")
    entered_admin_pass = st.text_input("Enter Admin Password:", type="password", key="admin_pass_input")
    
    if entered_admin_pass == admin_password:
        st.success("🔓 Authenticated as Administrator.")
        
        st.subheader("📤 Bulk Upload Grade Records")
        st.markdown(
            "Upload a CSV file containing student records. "
            f"Required columns: `{', '.join(REQUIRED_COLUMNS)}`"
        )
        
        uploaded_file = st.file_uploader("Choose a CSV file", type=["csv"], key="admin_csv_uploader")
        
        if uploaded_file is not None:
            try:
                upload_df = pd.read_csv(uploaded_file)
                missing_cols = [col for col in REQUIRED_COLUMNS if col not in upload_df.columns]
                
                if missing_cols:
                    st.error(f"❌ Missing required columns: {', '.join(missing_cols)}")
                else:
                    st.write("📋 Preview Upload Data:")
                    st.dataframe(upload_df.head(), use_container_width=True)
                    
                    if st.button("🚀 Push Data to Supabase", key="btn_push_data"):
                        records = upload_df.to_dict(orient="records")
                        
                        # Process records to hash plain-text passwords if provided
                        for rec in records:
                            if "password_hash" in rec and rec["password_hash"]:
                                pass_val = str(rec["password_hash"])
                                # Hash if input doesn't already appear to be a 64-char SHA-256 hash
                                if len(pass_val) != 64:
                                    rec["password_hash"] = hash_password(pass_val)
                        
                        supabase.table("reportcard").upsert(records).execute()
                        st.success("✅ Records successfully uploaded/updated in Supabase!")
            except Exception as upload_err:
                st.error(f"❌ Failed to process upload file: {str(upload_err)}")
                
        st.divider()
        st.subheader("📂 All Database Records")
        if st.button("Fetch All Records", key="btn_fetch_all"):
            try:
                all_data = supabase.table("reportcard").select("*").execute()
                all_df = pd.DataFrame(all_data.data)
                
                if not all_df.empty:
                    st.dataframe(all_df, use_container_width=True)
                else:
                    st.info("Database is currently empty.")
            except Exception as fetch_err:
                st.error(f"❌ Failed to retrieve records: {str(fetch_err)}")
    elif entered_admin_pass:
        st.error("❌ Incorrect Admin Password.")