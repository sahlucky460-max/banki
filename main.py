import streamlit as st
import sqlite3
import nepali_datetime
import pandas as pd
import io
from PIL import Image
import plotly.express as px
from datetime import date

# --- 1. DATABASE CONNECTION & INITIALIZATION ---
conn = sqlite3.connect('jewelry_ultimate_vault.db', check_same_thread=False)
c = conn.cursor()

# Create tables if they don't exist
c.execute('''CREATE TABLE IF NOT EXISTS loans 
             (loan_id INTEGER PRIMARY KEY, name TEXT, phone TEXT, address TEXT,
              total_principal REAL, nepali_date TEXT, status TEXT,
              interest_collected REAL, closing_date TEXT)''')

c.execute('''CREATE TABLE IF NOT EXISTS items 
             (item_id INTEGER PRIMARY KEY, loan_id INTEGER, description TEXT, 
              metal TEXT, weight REAL, photo BLOB)''')
conn.commit()

# --- 2. DATABASE REPAIR LOGIC (Handles Updates/Missing Columns) ---
def upgrade_database():
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(loans)")
    columns_info = cursor.fetchall()
    existing_columns = [info[1] for info in columns_info]
    
    if 'interest_collected' not in existing_columns:
        cursor.execute("ALTER TABLE loans ADD COLUMN interest_collected REAL DEFAULT 0.0")
    if 'closing_date' not in existing_columns:
        cursor.execute("ALTER TABLE loans ADD COLUMN closing_date TEXT")
    conn.commit()

upgrade_database()

# --- 3. LOGIC FUNCTIONS ---
def calculate_compound_interest(principal, rate_yearly, start_date_str):
    try:
        d1 = nepali_datetime.datetime.strptime(start_date_str, '%Y-%m-%d').date()
        d2 = nepali_datetime.date.today()
        total_days = (d2 - d1).days
        if total_days < 0: total_days = 0
        
        years = total_days // 365
        months = (total_days % 365) // 30
        days = (total_days % 365) % 30
        
        t_years = total_days / 365
        total_amount = principal * (1 + (rate_yearly / 100)) ** t_years
        interest = total_amount - principal
        
        return round(total_amount, 2), round(interest, 2), f"{years}Y, {months}M, {days}D"
    except:
        return principal, 0.0, "Date Error"

# --- 4. UI SETUP ---
st.set_page_config(page_title="Jewelry Business Suite", layout="wide")

# Session state to handle dynamic item adding
if 'item_count' not in st.session_state:
    st.session_state.item_count = 1

st.title("💎 Jewelry Retail & Loan Management System")
st.caption(f"Current Nepali Date: {nepali_datetime.date.today().strftime('%Y-%m-%d')}")

tab1, tab2, tab3, tab4 = st.tabs(["📥 New Entry", "📊 Dashboard", "🔓 Settlement", "📈 Accountancy Review"])

# --- TAB 1: NEW ENTRY (Dynamic & No Forms) ---
with tab1:
    st.subheader("Customer & Collateral Registration")
    
    col_cust_1, col_cust_2, col_cust_3 = st.columns(3)
    name = col_cust_1.text_input("Customer Name")
    phone = col_cust_2.text_input("Phone Number")
    address = col_cust_3.text_input("Address")
    
    col_loan_1, col_loan_2 = st.columns(2)
    principal = col_loan_1.number_input("Principal Amount (Rs.)", min_value=0.0, step=1000.0)
    loan_date = col_loan_2.text_input("Entry Date (BS)", value=nepali_datetime.date.today().strftime('%Y-%m-%d'))
    
    st.divider()
    st.session_state.item_count = st.number_input("Number of Collateral Items", min_value=1, step=1, value=st.session_state.item_count)
    
    all_items_data = []
    for i in range(st.session_state.item_count):
        with st.expander(f"Collateral Item #{i+1}", expanded=True):
            i1, i2, i3, i4 = st.columns([3, 2, 2, 3])
            d = i1.text_input("Item Description", key=f"desc_{i}", placeholder="e.g., Gold Chain")
            m = i2.selectbox("Metal Type", ["Gold", "Silver"], key=f"met_{i}")
            w = i3.number_input("Weight (grams)", min_value=0.0, key=f"wgt_{i}")
            p = i4.file_uploader("Upload Photo", type=['jpg', 'png', 'jpeg'], key=f"pic_{i}")
            all_items_data.append({"desc": d, "metal": m, "weight": w, "photo": p})

    if st.button("SAVE COMPLETE ENTRY", type="primary", use_container_width=True):
        if name and principal > 0:
            c.execute("INSERT INTO loans (name, phone, address, total_principal, nepali_date, status, interest_collected) VALUES (?,?,?,?,?,?,?)",
                      (name, phone, address, principal, loan_date, "Active", 0.0))
            last_id = c.lastrowid
            
            for item in all_items_data:
                img_bytes = None
                if item["photo"]:
                    img = Image.open(item["photo"])
                    buf = io.BytesIO()
                    img.save(buf, format='PNG')
                    img_bytes = buf.getvalue()
                
                c.execute("INSERT INTO items (loan_id, description, metal, weight, photo) VALUES (?,?,?,?,?)",
                          (last_id, item["desc"], item["metal"], item["weight"], img_bytes))
            
            conn.commit()
            st.success(f"SUCCESS: Loan ID {last_id} has been recorded in the vault.")
        else:
            st.error("Missing Info: Please ensure Name and Principal are filled.")

# --- TAB 2: DASHBOARD (Search & Filters) ---
with tab2:
    st.subheader("Vault Search & Inventory")
    f1, f2, f3 = st.columns(3)
    search_n = f1.text_input("Search by Name")
    search_a = f2.text_input("Search by Address")
    status_filter = f3.selectbox("Loan Status", ["Active", "Closed", "All"])
    
    query = "SELECT loan_id, name, address, total_principal, nepali_date, status FROM loans WHERE 1=1"
    if search_n: query += f" AND name LIKE '%{search_n}%'"
    if search_a: query += f" AND address LIKE '%{search_a}%'"
    if status_filter != "All": query += f" AND status = '{status_filter}'"
    
    df_display = pd.read_sql_query(query, conn)
    st.dataframe(df_display, use_container_width=True)

# --- TAB 3: SETTLEMENT (Compound Interest) ---
with tab3:
    st.subheader("Settlement & Interest Calculation")
    loan_id_to_settle = st.number_input("Enter Loan ID", min_value=0, step=1)
    # Global interest rate control in sidebar
    yearly_interest_rate = st.sidebar.number_input("Set Yearly Interest Rate (%)", value=24.0, help="2% per month = 24% per year")
    
    if loan_id_to_settle:
        loan_rec = c.execute("SELECT * FROM loans WHERE loan_id=?", (loan_id_to_settle,)).fetchone()
        
        if loan_rec:
            if loan_rec[6] == "Active":
                total_val, interest_val, time_str = calculate_compound_interest(loan_rec[4], yearly_interest_rate, loan_rec[5])
                
                st.info(f"**Customer:** {loan_rec[1]} | **Principal:** Rs. {loan_rec[4]} | **Date:** {loan_rec[5]}")
                
                m1, m2, m3 = st.columns(3)
                m1.metric("Time Duration", time_str)
                m2.metric("Interest Accrued", f"Rs. {interest_val}")
                m3.metric("Final Settlement", f"Rs. {total_val}")
                
                actual_collected = st.number_input("Actual Interest Collected (After Discounts)", value=interest_val)
                
                if st.button("CONFIRM PAYMENT & RELEASE COLLATERAL"):
                    today_bs = nepali_datetime.date.today().strftime('%Y-%m-%d')
                    c.execute("UPDATE loans SET status='Closed', interest_collected=?, closing_date=? WHERE loan_id=?",
                              (actual_collected, today_bs, loan_id_to_settle))
                    conn.commit()
                    st.success(f"Loan ID {loan_id_to_settle} is now CLOSED. Inventory released.")
            else:
                st.warning("This loan is already Closed/Settled.")
        else:
            st.error("Loan ID not found in database.")

# --- TAB 4: ACCOUNTANCY REVIEW (Analytics & Profit) ---
with tab4:
    st.header("📊 Business Analytics")
    
    all_loans_df = pd.read_sql_query("SELECT * FROM loans", conn)
    closed_loans_df = all_loans_df[all_loans_df['status'] == 'Closed']
    
    met1, met2, met3 = st.columns(3)
    met1.metric("Capital on Street (Active)", f"Rs. {all_loans_df[all_loans_df['status']=='Active']['total_principal'].sum():,.2f}")
    met2.metric("Total Profit Realized", f"Rs. {closed_loans_df['interest_collected'].sum():,.2f}")
    met3.metric("Closed Loan Count", len(closed_loans_df))

    st.divider()
    
    v1, v2 = st.columns(2)
    # Chart 1: Metal Distribution
    item_df = pd.read_sql_query("SELECT metal, weight FROM items", conn)
    if not item_df.empty:
        fig_p = px.pie(item_df, names='metal', values='weight', title="Vault Inventory Mix (Grams)", 
                       color_discrete_sequence=['#FFD700', '#C0C0C0'])
        v1.plotly_chart(fig_p, use_container_width=True)
    
    # Chart 2: Profit Timeline
    if not closed_loans_df.empty:
        fig_b = px.bar(closed_loans_df, x='closing_date', y='interest_collected', title="Profit History",
                       labels={'interest_collected': 'Interest (Rs)', 'closing_date': 'Date'})
        v2.plotly_chart(fig_b, use_container_width=True)

# Footer
st.sidebar.markdown("---")
st.sidebar.caption("Jewelry Management System v2.0 | Private Work Assistant")
