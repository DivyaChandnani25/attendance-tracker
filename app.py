import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import json
import pandas as pd

# --- 1. SETUP ---
st.set_page_config(page_title="EduTrack Analytics", layout="wide")

try:
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds_dict = json.loads(st.secrets["google_credentials"])
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    client = gspread.authorize(creds)
    
    # RE-ENTER YOUR SHEET ID HERE
    SHEET_ID = "1hVorDloheqOk5BL-6_JDOGHWZkHQeSUlhyoN_ou3UJQ" 
    ss = client.open_by_key(SHEET_ID)
    
    # Load all tabs
    config_df = pd.DataFrame(ss.worksheet("Config").get_all_records())
    roster_df = pd.DataFrame(ss.worksheet("Student Roster").get_all_records())
    dump_df = pd.DataFrame(ss.worksheet("Attendance Raw Dump").get_all_records())
except Exception as e:
    st.error(f"Connection Error: {e}")
    st.stop()

st.title("📊 Attendance Monitoring Dashboard")

# --- 2. FILTERS (DROPDOWNS) ---
with st.expander("Filter Options", expanded=True):
    c1, c2, c3 = st.columns(3)
    with c1:
        sel_sp = st.selectbox("Study Period", config_df['Study Period'].unique())
        sel_prog = st.selectbox("Program", config_df['Program Name'].dropna().unique())
    with c2:
        sel_unit = st.selectbox("Unit", config_df['Unit Name'].dropna().unique())
        sel_fac = st.selectbox("Facilitator", config_df['Facilitator Name'].dropna().unique())
    with c3:
        sel_type = st.selectbox("Session Type", ["Webinar", "Tutorial", "Workshop", "Viva"])
        # Get available weeks from the data
        weeks = sorted(dump_df['Week Number'].unique()) if not dump_df.empty else [1]
        sel_week = st.selectbox("Week", weeks)

# --- 3. DATA LOGIC ---
if st.button("Generate Attendance View"):
    # 1. Get the expected students for this Unit/Program
    expected_students = roster_df[
        (roster_df['Unit Name'] == sel_unit) & 
        (roster_df['Program Name'] == sel_prog)
    ].copy()

    if expected_students.empty:
        st.warning(f"No students found in 'Student Roster' for {sel_unit} / {sel_prog}")
    else:
        # 2. Get actual attendance from the Dump
        actual_att = dump_df[
            (dump_df['Study Period'] == sel_sp) &
            (dump_df['Unit Name'] == sel_unit) &
            (dump_df['Week Number'].astype(str) == str(sel_week)) &
            (dump_df['Session Type'] == sel_type)
        ]

        # 3. Merge Expected with Actual
        # We join on Student Name
        merged = pd.merge(
            expected_students[['Student Name']], 
            actual_att[['Student Name', 'Duration']], 
            on='Student Name', 
            how='left'
        )

        # 4. Create Status Column
        merged['Status'] = merged['Duration'].apply(lambda x: "✅ Present" if pd.notna(x) and x != "" else "❌ Absent")
        merged['Duration'] = merged['Duration'].fillna("-")

        # --- 4. DISPLAY ---
        st.divider()
        col_m1, col_m2 = st.columns(2)
        present_count = (merged['Status'] == "✅ Present").sum()
        col_m1.metric("Students Present", present_count)
        col_m2.metric("Students Absent", len(merged) - present_count)

        # Clean Table Output
        final_table = merged[['Student Name', 'Status', 'Duration']]
        
        # UI Styling for the table
        def color_status(val):
            color = 'red' if "Absent" in val else 'green'
            return f'color: {color}'

        st.dataframe(
            final_table.style.applymap(color_status, subset=['Status']),
            use_container_layout=True,
            height=500
        )
