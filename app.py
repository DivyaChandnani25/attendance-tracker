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
# --- 4. DASHBOARD LOGIC (For Admin) ---
elif menu == "📊 Admin: Attendance Report":
    st.title("Holistic Attendance View")
    
    if roster_df.empty:
        st.warning("The 'Student Roster' tab is empty. Please add students.")
        st.stop()

    with st.expander("Filter Report", expanded=True):
        f1, f2, f3 = st.columns(3)
        with f1:
            sel_sp = st.selectbox("Study Period", config_df['Study Period'].unique() if not config_df.empty else ["N/A"])
            sel_prog = st.selectbox("Program", config_df['Program Name'].dropna().unique() if not config_df.empty else ["N/A"])
        with f2:
            sel_unit = st.selectbox("Unit", config_df['Unit Name'].dropna().unique() if not config_df.empty else ["N/A"])
            # Get weeks from dump_df if available, else default 1-20
            avail_weeks = sorted(dump_df['Week Number'].unique()) if not dump_df.empty else list(range(1, 21))
            sel_week = st.selectbox("Week Number", avail_weeks)
        with f3:
            sel_type = st.selectbox("Session Type", ["Webinar", "Tutorial", "Workshop", "Viva"])

    if st.button("Generate Holistic Report"):
        # 1. Filter Roster for specific Program/Unit
        # We use .iloc to ensure we aren't tripped up by column name strings
        expected = roster_df[(roster_df['Program Name'] == sel_prog) & (roster_df['Unit Name'] == sel_unit)].copy()
        
        if expected.empty:
            st.warning(f"No students found in roster for {sel_prog} - {sel_unit}.")
        else:
            # FIX: Instead of calling ['Student Name'], we call the 1st column by position
            # This bypasses any "KeyError" or "AttributeError" regarding the name
            std_col_name = expected.columns[0] 
            expected['NAME_CLEAN'] = expected[std_col_name].astype(str).str.strip().upper()

            # 2. Get Actual Attendance
            actual_data = pd.DataFrame(columns=['NAME_CLEAN', 'Duration'])
            if not dump_df.empty:
                # Filter dump
                actual_filtered = dump_df[
                    (dump_df['Study Period'] == sel_sp) & 
                    (dump_df['Unit Name'] == sel_unit) & 
                    (dump_df['Week Number'].astype(str) == str(sel_week)) &
                    (dump_df['Session Type'] == sel_type)
                ].copy()
                
                if not actual_filtered.empty:
                    # Again, use position [7] which is 'Student Name' in your dump sheet
                    actual_col_name = actual_filtered.columns[7] 
                    actual_filtered['NAME_CLEAN'] = actual_filtered[actual_col_name].astype(str).str.strip().upper()
                    actual_data = actual_filtered[['NAME_CLEAN', 'Duration']]

            # 3. Merge on our new 'NAME_CLEAN' column
            merged = pd.merge(
                expected[[std_col_name, 'NAME_CLEAN']], 
                actual_data, 
                on='NAME_CLEAN', 
                how='left'
            )
            
            # 4. Status Logic
            merged['Status'] = merged['Duration'].apply(
                lambda x: "✅ Present" if pd.notna(x) and str(x).strip() not in ["", "-", "None"] else "❌ Absent"
            )
            
            # Display
            st.divider()
            m1, m2 = st.columns(2)
            pres = (merged['Status'] == "✅ Present").sum()
            m1.metric("Present", pres)
            m2.metric("Absent", len(merged) - pres)

            # Final Table (Showing the original name from Roster)
            display_table = merged[[std_col_name, 'Status', 'Duration']].rename(columns={std_col_name: "Student Name"})
            st.dataframe(display_table.astype(str), use_container_layout=True)
