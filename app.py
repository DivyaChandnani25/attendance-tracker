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
    
    SHEET_ID = "1hVorDloheqOk5BL-6_JDOGHWZkHQeSUlhyoN_ou3UJQ" 
    ss = client.open_by_key(SHEET_ID)
    
    # Load all 3 tabs as lists of dictionaries (much more stable than DataFrames)
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
    if not config_data:
        st.error("Config tab is empty.")
        st.stop()
    
    # Simple dropdowns using Python lists
    sps = list(set([str(r.get('Study Period', '')) for r in config_data]))
    progs = list(set([str(r.get('Program Name', '')) for r in config_data]))
    units = list(set([str(r.get('Unit Name', '')) for r in config_data]))
    facs = list(set([str(r.get('Facilitator Name', '')) for r in config_data]))

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
    if st.button("Submit"):
        if uploaded_file:
            with pdfplumber.open(uploaded_file) as pdf:
                text = "".join([p.extract_text() or "" for p in pdf.pages])
                tables = []
                for p in pdf.pages:
                    if p.extract_table(): tables.extend(p.extract_table())
            
            # Extract Date
            date_m = re.search(r"Meeting Date\s+(\d{1,2}-[A-Za-z]{3}-\d{4})", text)
            pdf_date = datetime.strptime(date_m.group(1), "%d-%b-%Y") if date_m else datetime.now()
            
            # Week Calc
            start_date_str = next((r.get('SP Start Date') for r in config_data if str(r.get('Study Period')) == sel_sp), None)
            sp_start = pd.to_datetime(start_date_str) if start_date_str else datetime.now()
            week_num = max(1, ((pdf_date - sp_start).days // 7) + 1)

            # Process Table
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

# --- 3. REPORT LOGIC ---
elif menu == "📊 Report":
    st.title("Holistic Attendance Report")
    
    if not roster_data:
        st.warning("No data in Student Roster.")
        st.stop()

    f1, f2, f3 = st.columns(3)
    with f1:
        u_progs = sorted(list(set([str(r.get('Program Name', '')) for r in roster_data])))
        s_prog = st.selectbox("Select Program", u_progs)
    with f2:
        u_units = sorted(list(set([str(r.get('Unit Name', '')) for r in roster_data if str(r.get('Program Name')) == s_prog])))
        s_unit = st.selectbox("Select Unit", u_units)
    with f3:
        s_week = st.number_input("Week Number", 1, 20, 1)

    if st.button("Generate Report"):
        # 1. Get Expected List from Roster (Case Insensitive)
        expected = [str(r.get('Student Name', '')).strip().upper() for r in roster_data 
                    if str(r.get('Program Name')) == s_prog and str(r.get('Unit Name')) == s_unit]
        
        # 2. Get Actual Attendance from Dump
        actual_map = {}
        for row in dump_data:
            # Check match for Unit, Week, and Program
            if (str(row.get('Unit Name')) == s_unit and 
                str(row.get('Week Number')) == str(s_week) and 
                str(row.get('Program Name')) == s_prog):
                
                name_key = str(row.get('Student Name', '')).strip().upper()
                actual_map[name_key] = row.get('Duration', '-')

        # 3. Build Results
        results = []
        for name in expected:
            duration = actual_map.get(name)
            results.append({
                "Student Name": name,
                "Status": "✅ Present" if duration else "❌ Absent",
                "Duration": duration if duration else "-"
            })

        if not results:
            st.error("No students found in roster matching these filters.")
        else:
            final_df = pd.DataFrame(results)
            st.divider()
            
            # 1. Show Metrics
            c1, c2 = st.columns(2)
            present_count = (final_df["Status"] == "✅ Present").sum()
            c1.metric("Present", int(present_count))
            c2.metric("Absent", int(len(final_df) - present_count))
            
            # 2. The "Safe" Table Display
            st.subheader("Attendance List")
            try:
                # Convert everything to string to prevent the TypeError
                display_df = final_df.astype(str)
                st.dataframe(display_df, use_container_layout=True)
            except:
                # If dataframe STILL fails, use the static table method
                st.table(final_df.astype(str))   
