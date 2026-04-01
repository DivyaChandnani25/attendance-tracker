import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import json
import pdfplumber
import pandas as pd
from datetime import datetime

# --- 1. SETUP ---
st.set_page_config(page_title="EduTrack Pro", layout="wide")

try:
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds_dict = json.loads(st.secrets["google_credentials"])
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    client = gspread.authorize(creds)
    
    # YOUR SPREADSHEET ID GOES HERE
    SHEET_ID = "YOUR_SPREADSHEET_ID_HERE" 
    ss = client.open_by_key(SHEET_ID)
    dump_sheet = ss.worksheet("Attendance Raw Dump")
    
    # Load Config Data
    config_df = pd.DataFrame(ss.worksheet("Config").get_all_records())
except Exception as e:
    st.error(f"Connection Error: {e}. Check Spreadsheet ID and Tab Names.")
    st.stop()

# --- 2. SIDEBAR NAVIGATION ---
st.sidebar.title("Navigation")
menu = st.sidebar.radio("Go to:", ["📤 Upload Data", "📊 Attendance Dashboard"])

# --- 3. UPLOAD PAGE ---
if menu == "📤 Upload Data":
    st.title("📤 Attendance Upload")
    
    with st.container(border=True):
        col1, col2 = st.columns(2)
        with col1:
            sp = st.selectbox("Study Period", config_df['Study Period'].unique())
            # Calculate Week Number based on Start Date in Config
            sp_data = config_df[config_df['Study Period'] == sp].iloc[0]
            start_date = pd.to_datetime(sp_data['SP Start Date'])
            week_num = ((datetime.now() - start_date).days // 7) + 1
            
            program = st.selectbox("Program Name", config_df['Program Name'].dropna().unique())
            session_type = st.selectbox("Session Type", ["Webinar", "Tutorial", "Workshop", "Viva"])
            
        with col2:
            unit = st.selectbox("Unit Name", config_df['Unit Name'].dropna().unique())
            facilitator = st.selectbox("Facilitator Name", config_df['Facilitator Name'].dropna().unique())
            st.info(f"Automatically assigning to: **Week {max(1, week_num)}**")

    uploaded_file = st.file_uploader("Upload Google Meet PDF", type="pdf")

    if st.button("Submit to Database", type="primary"):
        if uploaded_file:
            with st.spinner("Processing PDF..."):
                all_rows = []
                with pdfplumber.open(uploaded_file) as pdf:
                    for page in pdf.pages:
                        table = page.extract_table()
                        if table: all_rows.extend(table)
                
                df = pd.DataFrame(all_rows)
                # Find header row
                header_idx = df[df.apply(lambda r: r.astype(str).str.contains('Participant name', case=False).any(), axis=1)].index[0]
                df.columns = df.iloc[header_idx].str.replace('\n', ' ').str.strip()
                df = df[header_idx + 1:].dropna(subset=['Participant name'])

                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                final_data = []
                for _, row in df.iterrows():
                    final_data.append([
                        timestamp, sp, max(1, week_num), program, unit, 
                        facilitator, session_type, row['Participant name'], row['Attended duration']
                    ])
                
                dump_sheet.append_rows(final_data)
                st.success(f"Successfully uploaded {len(final_data)} records!")
                st.balloons()

# --- 4. DASHBOARD PAGE ---
elif menu == "📊 Attendance Dashboard":
    st.title("📊 Attendance Dashboard")
    
    # Load raw data from dump
    raw_df = pd.DataFrame(dump_sheet.get_all_records())
    
    if not raw_df.empty:
        # Filters
        f1, f2, f3 = st.columns(3)
        with f1: 
            view_sp = st.selectbox("Select Study Period", raw_df['Study Period'].unique())
        with f2: 
            view_unit = st.selectbox("Select Unit", raw_df[raw_df['Study Period']==view_sp]['Unit Name'].unique())
        with f3: 
            view_weeks = st.multiselect("Select Weeks", sorted(raw_df['Week Number'].unique()), default=raw_df['Week Number'].unique())

        filtered = raw_df[(raw_df['Study Period'] == view_sp) & 
                          (raw_df['Unit Name'] == view_unit) & 
                          (raw_df['Week Number'].isin(view_weeks))]

        # Metrics
        st.divider()
        m1, m2 = st.columns(2)
        total_sessions = len(filtered['Timestamp'].unique())
        m1.metric("Total Sessions Tracked", total_sessions)
        m2.metric("Unique Students Present", len(filtered['Student Name'].unique()))

        # Simple Viz
        st.subheader("Attendance Count by Student")
        chart_data = filtered.groupby('Student Name').size().reset_index(name='Attendance Count')
        st.bar_chart(chart_data, x="Student Name", y="Attendance Count")

        st.subheader("Raw Data View")
        st.dataframe(filtered, use_container_layout=True)
    else:
        st.info("No data found in the Raw Dump yet.")
