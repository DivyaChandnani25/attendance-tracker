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
    
    # Load all 3 tabs as lists of dictionaries (The most stable method)
    config_data = ss.worksheet("Config").get_all_records()
    roster_data = ss.worksheet("Student Roster").get_all_records()
    dump_data = ss.worksheet("Attendance Raw Dump").get_all_records()
except Exception as e:
    st.error(f"Connection Error: {e}")
    st.stop()

st.sidebar.title("Menu")
menu = st.sidebar.radio("Select Task:", ["📤 Upload", "📊 Report"])

# --- 2. UPLOAD LOGIC ---
if menu == "📤 Upload":
    st.title("Upload Attendance")
    
    sps = sorted(list(set([str(r.get('Study Period', '')) for r in config_data if r.get('Study Period')])))
    progs = sorted(list(set([str(r.get('Program Name', '')) for r in config_data if r.get('Program Name')])))
    units = sorted(list(set([str(r.get('Unit Name', '')) for r in config_data if r.get('Unit Name')])))
    facs = sorted(list(set([str(r.get('Facilitator Name', '')) for r in config_data if r.get('Facilitator Name')])))

    with st.container(border=True):
        c1, c2 = st.columns(2)
        with c1:
            sel_sp = st.selectbox("Study Period", sps)
            sel_prog = st.selectbox("Program", progs)
            sel_type = st.selectbox("Type", ["Webinar", "Tutorial", "Workshop", "Viva"])
        with c2:
            sel_unit = st.selectbox("Unit", units)
            sel_fac = st.selectbox("Facilitator", facs)

    uploaded_file = st.file_uploader("Upload PDF", type="pdf")
    if st.button("Submit Attendance", type="primary"):
        if uploaded_file:
            with st.spinner("Processing..."):
                with pdfplumber.open(uploaded_file) as pdf:
                    text = "".join([p.extract_text() or "" for p in pdf.pages])
                    tables = []
                    for p in pdf.pages:
                        if p.extract_table(): tables.extend(p.extract_table())
                
                date_m = re.search(r"Meeting Date\s+(\d{1,2}-[A-Za-z]{3}-\d{4})", text)
                pdf_date = datetime.strptime(date_m.group(1), "%d-%b-%Y") if date_m else datetime.now()
                
                start_date_str = next((r.get('SP Start Date') for r in config_data if str(r.get('Study Period')) == sel_sp), None)
                sp_start = pd.to_datetime(start_date_str) if start_date_str else datetime.now()
                week_num = max(1, ((pdf_date - sp_start).days // 7) + 1)

                df = pd.DataFrame(tables)
                h_idx = df[df.apply(lambda r: r.astype(str).str.contains('Participant name', case=False).any(), axis=1)].index[0]
                df.columns = df.iloc[h_idx]
                df = df[h_idx+1:].dropna(subset=[df.columns[1]])

                rows_to_upload = []
                for _, r in df.iterrows():
                    rows_to_upload.append([
                        pdf_date.strftime("%Y-%m-%d"), sel_sp, week_num, sel_prog, sel_unit, 
                        sel_fac, sel_type, str(r.iloc[1]).strip().upper(), r.iloc[3]
                    ])
                
                ss.worksheet("Attendance Raw Dump").append_rows(rows_to_upload)
                st.success(f"Success! Uploaded {len(rows_to_upload)} records.")
                st.balloons()

# --- 3. REPORT LOGIC ---
elif menu == "📊 Report":
    st.title("Holistic Attendance Report")
    
    if not roster_data:
        st.warning("Please add data to your 'Student Roster' tab first.")
        st.stop()

    with st.container(border=True):
        f1, f2, f3 = st.columns(3)
        with f1:
            u_progs = sorted(list(set([str(r.get('Program Name', '')) for r in roster_data if r.get('Program Name')])))
            s_prog = st.selectbox("Program", u_progs)
            s_type = st.selectbox("Session Type", ["Webinar", "Tutorial", "Workshop", "Viva"])
        with f2:
            u_units = sorted(list(set([str(r.get('Unit Name', '')) for r in roster_data if str(r.get('Program Name')) == s_prog])))
            s_unit = st.selectbox("Unit", u_units)
        with f3:
            s_week = st.number_input("Week Number", 1, 20, 1)

    if st.button("Generate Report", type="primary"):
        # 1. Get Expected List from Roster
        expected = [str(r.get('Student Name', '')).strip().upper() for r in roster_data 
                    if str(r.get('Program Name')) == s_prog and str(r.get('Unit Name')) == s_unit]
        
        # 2. Get Actual Attendance from Dump
        actual_map = {}
        for row in dump_data:
            if (str(row.get('Unit Name')) == s_unit and 
                str(row.get('Week Number')) == str(s_week) and 
                str(row.get('Program Name')) == s_prog and
                str(row.get('Session Type')) == s_type):
                
                name_key = str(row.get('Student Name', '')).strip().upper()
                actual_map[name_key] = row.get('Duration', '-')

        # 3. Build Results
        results = []
        for name in expected:
            duration = actual_map.get(name)
            results.append({
                "Student Name": name,
                "Status": "✅ Present" if duration else "❌ Absent",
                "Duration": str(duration) if duration else "-"
            })

        if not results:
            st.error("No students found for this combination. Check your Student Roster tab.")
        else:
            # Create the DataFrame
            final_df = pd.DataFrame(results)
            
            # 1. Show Metrics
            st.divider()
            c1, c2 = st.columns(2)
            present_count = len([r for r in results if r["Status"] == "✅ Present"])
            absent_count = len(results) - present_count
            
            c1.metric("Present", int(present_count))
            c2.metric("Absent", int(absent_count))
            
            st.subheader(f"Attendance: {s_unit} (Week {s_week} - {s_type})")
            
            # 2. THE FINAL SAFETY FIX: Use st.table instead of st.dataframe
            # This renders as a simple HTML table which avoids the JavaScript TypeError
            try:
                st.table(final_df.astype(str))
            except Exception as e:
                # If even that fails (unlikely), show as raw text so you still see the data
                st.write("Displaying raw data due to a rendering error:")
                st.write(results)
