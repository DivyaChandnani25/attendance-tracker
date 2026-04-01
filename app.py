import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import json
import pdfplumber
import pandas as pd
from datetime import datetime
import re

# --- 1. SETUP ---
st.set_page_config(page_title="EduTrack Pro", layout="wide")

try:
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds_dict = json.loads(st.secrets["google_credentials"])
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    client = gspread.authorize(creds)
    
    SHEET_ID = "1hVorDloheqOk5BL-6_JDOGHWZkHQeSUlhyoN_ou3UJQ" 
    ss = client.open_by_key(SHEET_ID)
    dump_sheet = ss.worksheet("Attendance Raw Dump")
    config_df = pd.DataFrame(ss.worksheet("Config").get_all_records())
except Exception as e:
    st.error(f"Connection Error: {e}")
    st.stop()

# --- 2. SIDEBAR ---
st.sidebar.title("Navigation")
menu = st.sidebar.radio("Go to:", ["📤 Upload Data", "📊 Attendance Dashboard"])

# --- 3. UPLOAD PAGE ---
if menu == "📤 Upload Data":
    st.title("📤 Attendance Upload")
    
    with st.container(border=True):
        col1, col2 = st.columns(2)
        with col1:
            sp = st.selectbox("Study Period", config_df['Study Period'].unique())
            program = st.selectbox("Program Name", config_df['Program Name'].dropna().unique())
            session_type = st.selectbox("Session Type", ["Webinar", "Tutorial", "Workshop", "Viva"])
        with col2:
            unit = st.selectbox("Unit Name", config_df['Unit Name'].dropna().unique())
            facilitator = st.selectbox("Facilitator Name", config_df['Facilitator Name'].dropna().unique())

    uploaded_file = st.file_uploader("Upload Google Meet PDF", type="pdf")

    if st.button("Submit to Database", type="primary"):
        if uploaded_file:
            with st.spinner("Extracting date and attendance..."):
                all_text = ""
                all_rows = []
                with pdfplumber.open(uploaded_file) as pdf:
                    for page in pdf.pages:
                        all_text += page.extract_text() or ""
                        table = page.extract_table()
                        if table: all_rows.extend(table)
                
                # --- DATE EXTRACTION ---
                # Search for "Meeting Date" followed by a date pattern
                date_match = re.search(r"Meeting Date\s+(\d{1,2}-[A-Za-z]{3}-\d{4})", all_text)
                if date_match:
                    pdf_date_str = date_match.group(1)
                    meeting_date = datetime.strptime(pdf_date_str, "%d-%b-%Y")
                else:
                    st.warning("Could not find 'Meeting Date' in PDF. Using today's date instead.")
                    meeting_date = datetime.now()

                # --- WEEK CALCULATION ---
                sp_start = pd.to_datetime(config_df[config_df['Study Period'] == sp]['SP Start Date'].iloc[0])
                week_num = ((meeting_date - sp_start).days // 7) + 1
                
                # --- TABLE PROCESSING ---
                df = pd.DataFrame(all_rows)
                header_idx = df[df.apply(lambda r: r.astype(str).str.contains('Participant name', case=False).any(), axis=1)].index[0]
                df.columns = df.iloc[header_idx].str.replace('\n', ' ').str.strip()
                df = df[header_idx + 1:].dropna(subset=['Participant name'])

                final_data = []
                for _, row in df.iterrows():
                    final_data.append([
                        meeting_date.strftime("%Y-%m-%d"), # Using PDF Date
                        sp, max(1, week_num), program, unit, 
                        facilitator, session_type, row['Participant name'], row['Attended duration']
                    ])
                
                dump_sheet.append_rows(final_data)
                st.success(f"Success! Processed session from {pdf_date_str} as Week {max(1, week_num)}.")
                st.balloons()

# --- 4. DASHBOARD PAGE ---
elif menu == "📊 Attendance Dashboard":
    st.title("📊 Attendance Dashboard")
    raw_df = pd.DataFrame(dump_sheet.get_all_records())
    
    if not raw_df.empty:
        # Filters
        f1, f2 = st.columns(2)
        with f1: view_sp = st.selectbox("Select Study Period", raw_df['Study Period'].unique())
        with f2: view_unit = st.selectbox("Select Unit", raw_df[raw_df['Study Period']==view_sp]['Unit Name'].unique())
        
        view_weeks = st.multiselect("Filter by Weeks", sorted(raw_df['Week Number'].unique()), default=raw_df['Week Number'].unique())

        filtered = raw_df[(raw_df['Study Period'] == view_sp) & 
                          (raw_df['Unit Name'] == view_unit) & 
                          (raw_df['Week Number'].isin(view_weeks))]

        # Simple Viz: Attendance Frequency
        st.subheader(f"Total Sessions per Student ({view_unit})")
        chart_data = filtered.groupby('Student Name').size().reset_index(name='Sessions')
        st.bar_chart(chart_data, x="Student Name", y="Sessions")

        st.subheader("Data Overview")
        # Fix: Convert all data to strings to prevent the TypeError in the table display
        clean_df = filtered.astype(str)
        st.dataframe(clean_df, use_container_layout=True)
    else:
        st.info("No data found. Upload a PDF to get started!")
