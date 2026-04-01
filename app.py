import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import json

# --- 1. SETUP & AUTHENTICATION ---
st.set_page_config(page_title="Attendance Tracker", page_icon="📝")

# Connect to Google Sheets using the secret key we hid in Streamlit
try:
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds_dict = json.loads(st.secrets["google_credentials"])
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    client = gspread.authorize(creds)
    
    # Open the Google Sheet
    SHEET_NAME = "Attendance Raw Dump"
    sheet = client.open(SHEET_NAME).sheet1
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

# --- 3. THE UPLOADER ---
uploaded_file = st.file_uploader("Upload Attendance PDF", type="pdf")

if st.button("Submit Attendance", type="primary"):
    if uploaded_file is not None and unit_name and facilitator_name:
        st.success("File received! The UI is working perfectly.")
        st.info("Next up: Phase 4! We will teach this button how to read the PDF and send it to Google Sheets.")
    else:
        st.warning("Please fill out all fields and upload a PDF.")
