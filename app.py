import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import json
import pdfplumber
import pandas as pd
from datetime import datetime

# --- 1. SETUP & AUTHENTICATION ---
st.set_page_config(page_title="Attendance Tracker", page_icon="📝")

try:
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds_dict = json.loads(st.secrets["google_credentials"])
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    client = gspread.authorize(creds)
    
    # Open the first tab of the Google Sheet
    SHEET_NAME = "Attendance Raw Dump"  
    dump_sheet = client.open(SHEET_NAME).sheet1
except Exception as e:
    st.error("Could not connect to Google Sheets. Check your Secret Key and Sheet Name!")
    st.stop()

# --- 2. THE APP INTERFACE ---
st.title("📝 Attendance PDF Tracker")
st.write("Fill out the details below and upload the Google Meet PDF.")

col1, col2 = st.columns(2)
with col1:
    study_period = st.selectbox("Study Period", ["Term 1", "Term 2", "Term 3", "Term 4", "Other"])
    program_name = st.selectbox("Program Name", ["Program A", "Program B", "Program C", "Other"])
with col2:
    unit_name = st.text_input("Unit Name (e.g., Math 101)")
    facilitator_name = st.text_input("Facilitator Name")

st.divider()

# --- 3. THE UPLOADER & PDF EXTRACTOR ---
uploaded_file = st.file_uploader("Upload Google Meet Attendance PDF", type="pdf")

if st.button("Submit Attendance", type="primary"):
    if uploaded_file is not None and unit_name and facilitator_name:
        with st.spinner("Extracting PDF data..."):
            try:
                # 1. Read the PDF Table
                all_rows = []
                with pdfplumber.open(uploaded_file) as pdf:
                    for page in pdf.pages:
                        table = page.extract_table()
                        if table:
                            all_rows.extend(table)

                if not all_rows:
                    st.error("Could not find a grid/table in this PDF.")
                    st.stop()

                # 2. Convert to Data Format and find the headers
                df = pd.DataFrame(all_rows)
                
                # Look for the row that contains 'Participant name'
                header_idx = df[df.apply(lambda row: row.astype(str).str.contains('Participant name', case=False, na=False).any(), axis=1)].index
                if len(header_idx) > 0:
                    df.columns = df.iloc[header_idx[0]].str.replace('\n', ' ').str.strip()
                    df = df[header_idx[0] + 1:] # Keep everything below the header
                else:
                    st.error("Could not find the 'Participant name' column in this PDF.")
                    st.stop()

                # 3. Format the final rows for the Raw Dump tab
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                final_rows = []
                
                for index, row in df.iterrows():
                    student_name = row.get('Participant name', '')
                    duration = row.get('Attended duration', '')
                    
                    # Only append if a student name actually exists in that row
                    if pd.notna(student_name) and str(student_name).strip() != "":
                        final_rows.append([
                            timestamp,
                            study_period,
                            program_name,
                            unit_name,
                            facilitator_name,
                            student_name,
                            duration
                        ])

                # 4. Send to Google Sheets
                if final_rows:
                    dump_sheet.append_rows(final_rows)
                    st.success(f"Success! {len(final_rows)} attendance records sent to your Google Sheet.")
                    st.balloons()
                else:
                    st.warning("No valid student names found in the table.")

            except Exception as e:
                st.error(f"An error occurred while reading the PDF: {e}")
    else:
        st.warning("Please fill out all text fields and upload a PDF before submitting.")
