import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import json
import pdfplumber
import pandas as pd
from datetime import datetime
import re

# --- 1. SETUP & AUTH ---
st.set_page_config(page_title="EduTrack Master", layout="wide")

try:
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds_dict = json.loads(st.secrets["google_credentials"])
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    client = gspread.authorize(creds)
    
    # RE-ENTER YOUR SHEET ID HERE
    SHEET_ID = "1hVorDloheqOk5BL-6_JDOGHWZkHQeSUlhyoN_ou3UJQ" 
    ss = client.open_by_key(SHEET_ID)
    
    # Load all 3 tabs
    dump_sheet = ss.worksheet("Attendance Raw Dump")
    config_df = pd.DataFrame(ss.worksheet("Config").get_all_records())
    roster_df = pd.DataFrame(ss.worksheet("Student Roster").get_all_records())
    dump_df = pd.DataFrame(dump_sheet.get_all_records())
except Exception as e:
    st.error(f"Connection Error: {e}")
    st.stop()

# --- 2. SIDEBAR NAVIGATION ---
st.sidebar.title("EduTrack Menu")
menu = st.sidebar.radio("Select Task:", ["📤 Teacher: Upload PDF", "📊 Admin: Attendance Report"])

# --- 3. UPLOAD LOGIC (For Teachers) ---
if menu == "📤 Teacher: Upload PDF":
    st.title("Upload Google Meet Attendance")
    st.info("Teachers: Select your session details and upload the Meet PDF.")
    
    with st.container(border=True):
        c1, c2 = st.columns(2)
        with c1:
            sp = st.selectbox("Study Period", config_df['Study Period'].unique())
            prog = st.selectbox("Program", config_df['Program Name'].dropna().unique())
            sess_type = st.selectbox("Session Type", ["Webinar", "Tutorial", "Workshop", "Viva"])
        with c2:
            unit = st.selectbox("Unit", config_df['Unit Name'].dropna().unique())
            fac = st.selectbox("Facilitator", config_df['Facilitator Name'].dropna().unique())

    uploaded_file = st.file_uploader("Drag and drop Google Meet PDF here", type="pdf")

    if st.button("Submit Attendance", type="primary"):
        if uploaded_file:
            with st.spinner("Processing PDF..."):
                all_text = ""
                all_rows = []
                with pdfplumber.open(uploaded_file) as pdf:
                    for page in pdf.pages:
                        all_text += page.extract_text() or ""
                        table = page.extract_table()
                        if table: all_rows.extend(table)
                
                # Extract Meeting Date from PDF [cite: 17]
                date_match = re.search(r"Meeting Date\s+(\d{1,2}-[A-Za-z]{3}-\d{4})", all_text)
                pdf_date = datetime.strptime(date_match.group(1), "%d-%b-%Y") if date_match else datetime.now()
                
                # Calculate Week Number
                sp_start = pd.to_datetime(config_df[config_df['Study Period'] == sp]['SP Start Date'].iloc[0])
                week_num = max(1, ((pdf_date - sp_start).days // 7) + 1)

                # Process Table Data [cite: 18]
                df = pd.DataFrame(all_rows)
                header_idx = df[df.apply(lambda r: r.astype(str).str.contains('Participant name', case=False).any(), axis=1)].index[0]
                df.columns = df.iloc[header_idx].str.replace('\n', ' ').str.strip()
                df = df[header_idx + 1:].dropna(subset=['Participant name'])

                # Save to "Attendance Raw Dump"
                final_rows = []
                for _, row in df.iterrows():
                    final_rows.append([
                        pdf_date.strftime("%Y-%m-%d"), sp, week_num, prog, unit, fac, sess_type, 
                        row['Participant name'].strip().upper(), row['Attended duration']
                    ])
                
                dump_sheet.append_rows(final_rows)
                st.success(f"Uploaded {len(final_rows)} students for Week {week_num}!")
                st.balloons()

# --- 4. DASHBOARD LOGIC (For Admin) ---
elif menu == "📊 Admin: Attendance Report":
    st.title("Holistic Attendance View")
    st.write("This view compares the **Student Roster** against the **Uploaded Data**.")

    with st.expander("Filter Report", expanded=True):
        f1, f2, f3 = st.columns(3)
        with f1:
            sel_sp = st.selectbox("Study Period", config_df['Study Period'].unique() if not config_df.empty else ["N/A"])
            sel_prog = st.selectbox("Program", config_df['Program Name'].dropna().unique() if not config_df.empty else ["N/A"])
        with f2:
            sel_unit = st.selectbox("Unit", config_df['Unit Name'].dropna().unique() if not config_df.empty else ["N/A"])
            sel_week = st.number_input("Week Number", min_value=1, max_value=20, value=1)
        with f3:
            sel_type = st.selectbox("Session Type", ["Webinar", "Tutorial", "Workshop", "Viva"])

    if st.button("Generate Holistic Report"):
        if 'Student Name' not in roster_df.columns:
            st.error("Error: Could not find 'Student Name' column in the 'Student Roster' tab. Please check your Google Sheet headers.")
        else:
            # 1. Get Expected Students from 'Student Roster'
            expected = roster_df[(roster_df['Program Name'] == sel_prog) & (roster_df['Unit Name'] == sel_unit)].copy()
            
            if expected.empty:
                st.warning(f"No students found in roster for {sel_prog} - {sel_unit}.")
            else:
                expected['Student Name'] = expected['Student Name'].astype(str).str.strip().upper()

                # 2. Get Actual Attendance from 'Raw Dump'
                if not dump_df.empty:
                    # Ensure column names match and types are consistent for filtering
                    actual = dump_df[
                        (dump_df['Study Period'] == sel_sp) & 
                        (dump_df['Unit Name'] == sel_unit) & 
                        (dump_df['Week Number'].astype(str) == str(sel_week)) &
                        (dump_df['Session Type'] == sel_type)
                    ].copy()
                    actual['Student Name'] = actual['Student Name'].astype(str).str.strip().upper()
                else:
                    actual = pd.DataFrame(columns=['Student Name', 'Duration'])

                # 3. Merge to find Absentees
                merged = pd.merge(expected[['Student Name']], actual[['Student Name', 'Duration']], on='Student Name', how='left')
                merged['Status'] = merged['Duration'].apply(lambda x: "✅ Present" if pd.notna(x) and str(x).strip() != "" and str(x) != "-" else "❌ Absent")
                
                # Display Metrics
                st.divider()
                m1, m2 = st.columns(2)
                pres = (merged['Status'] == "✅ Present").sum()
                m1.metric("Present", pres)
                m2.metric("Absent", len(merged) - pres)

                st.dataframe(merged[['Student Name', 'Status', 'Duration']].astype(str), use_container_layout=True)
