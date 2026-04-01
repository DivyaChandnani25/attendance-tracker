import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import json
import pdfplumber
import pandas as pd
from datetime import datetime
import re

# --- 1. SETUP ---
st.set_page_config(page_title="EduTrack Master", layout="wide")

try:
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds_dict = json.loads(st.secrets["google_credentials"])
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    client = gspread.authorize(creds)
    
    # RE-ENTER YOUR SHEET ID HERE
    SHEET_ID = "1hVorDloheqOk5BL-6_JDOGHWZkHQeSUlhyoN_ou3UJQ" 
    ss = client.open_by_key(SHEET_ID)
    
    # Force refresh data from all 3 tabs
    dump_sheet = ss.worksheet("Attendance Raw Dump")
    config_df = pd.DataFrame(ss.worksheet("Config").get_all_records())
    roster_df = pd.DataFrame(ss.worksheet("Student Roster").get_all_records())
    dump_df = pd.DataFrame(dump_sheet.get_all_records())
except Exception as e:
    st.error(f"Connection Error: {e}")
    st.stop()

st.sidebar.title("Menu")
menu = st.sidebar.radio("Select Task:", ["📤 Upload", "📊 Report"])

# --- 3. UPLOAD ---
if menu == "📤 Upload":
    st.title("Upload Attendance")
    # (Existing Upload Logic remains the same as previous stable version)
    with st.container(border=True):
        c1, c2 = st.columns(2)
        with c1:
            sp = st.selectbox("Study Period", config_df.iloc[:, 0].unique())
            prog = st.selectbox("Program", config_df.iloc[:, 2].dropna().unique())
            sess_type = st.selectbox("Type", ["Webinar", "Tutorial", "Workshop", "Viva"])
        with c2:
            unit = st.selectbox("Unit", config_df.iloc[:, 3].dropna().unique())
            fac = st.selectbox("Facilitator", config_df.iloc[:, 4].dropna().unique())

    uploaded_file = st.file_uploader("Upload PDF", type="pdf")
    if st.button("Submit"):
        if uploaded_file:
            with pdfplumber.open(uploaded_file) as pdf:
                text = "".join([p.extract_text() for p in pdf.pages])
                tables = []
                for p in pdf.pages:
                    if p.extract_table(): tables.extend(p.extract_table())
            
            date_m = re.search(r"Meeting Date\s+(\d{1,2}-[A-Za-z]{3}-\d{4})", text)
            pdf_date = datetime.strptime(date_m.group(1), "%d-%b-%Y") if date_m else datetime.now()
            
            # Find Start Date from Config (Column B)
            sp_row = config_df[config_df.iloc[:, 0] == sp]
            sp_start = pd.to_datetime(sp_row.iloc[0, 1])
            week_num = max(1, ((pdf_date - sp_start).days // 7) + 1)

            df = pd.DataFrame(tables)
            h_idx = df[df.apply(lambda r: r.astype(str).str.contains('Participant name', case=False).any(), axis=1)].index[0]
            df.columns = df.iloc[h_idx]
            df = df[h_idx+1:].dropna(subset=[df.columns[1]])

            rows = []
            for _, r in df.iterrows():
                rows.append([pdf_date.strftime("%Y-%m-%d"), sp, week_num, prog, unit, fac, sess_type, str(r.iloc[1]).strip().upper(), r.iloc[3]])
            
            dump_sheet.append_rows(rows)
            st.success("Uploaded!")

# --- 4. REPORT ---
elif menu == "📊 Report":
    st.title("Holistic Report")
    
    if roster_df.empty:
        st.error("Roster is empty.")
        st.stop()

    f1, f2, f3 = st.columns(3)
    with f1:
        sel_prog = st.selectbox("Program", roster_df.iloc[:, 1].unique())
    with f2:
        sel_unit = st.selectbox("Unit", roster_df.iloc[:, 2].unique())
    with f3:
        sel_week = st.number_input("Week", 1, 20, 1)

    if st.button("Generate"):
        # 1. Filter Roster (Column B for Program, Column C for Unit)
        # We use .values to keep it as a simple list to avoid index errors
        expected_names = roster_df[
            (roster_df.iloc[:, 1].astype(str) == str(sel_prog)) & 
            (roster_df.iloc[:, 2].astype(str) == str(sel_unit))
        ].iloc[:, 0].astype(str).str.strip().upper().tolist()

        if not expected_names:
            st.warning("No students found for this selection.")
        else:
            # 2. Filter Dump (Column D=Prog, E=Unit, C=Week)
            actual_map = {}
            if not dump_df.empty:
                attendance = dump_df[
                    (dump_df.iloc[:, 3].astype(str) == str(sel_prog)) &
                    (dump_df.iloc[:, 4].astype(str) == str(sel_unit)) &
                    (dump_df.iloc[:, 2].astype(str) == str(sel_week))
                ]
                # Map Name -> Duration
                for _, row in attendance.iterrows():
                    actual_map[str(row.iloc[7]).strip().upper()] = row.iloc[8]

            # 3. Build Final Display List
            final_list = []
            for name in expected_names:
                duration = actual_map.get(name, None)
                status = "✅ Present" if duration else "❌ Absent"
                final_list.append({"Student Name": name, "Status": status, "Duration": duration or "-"})

            report_df = pd.DataFrame(final_list)
            
            st.divider()
            pres = (report_df["Status"] == "✅ Present").sum()
            st.metric("Total Present", pres)
            st.dataframe(report_df, use_container_layout=True)
