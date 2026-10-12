import sqlite3
from datetime import datetime, timezone
import streamlit as st

DB_PATH = "today_nurse_demo.db"

st.set_page_config(page_title="Today Nurse | NICU Demo", page_icon="🩺", layout="wide")

# Educational prototype only. Never enter real patient information.
# Public visitors may add/read fictional records. Cloud local storage may reset.

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS observations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id TEXT NOT NULL, recorded_at TEXT NOT NULL,
            hr INTEGER NOT NULL, rr INTEGER NOT NULL, temp_c REAL NOT NULL,
            spo2 INTEGER NOT NULL, fio2 INTEGER NOT NULL, support TEXT NOT NULL
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS fluid_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id TEXT NOT NULL, recorded_at TEXT NOT NULL,
            iv_ml REAL NOT NULL, feeds_ml REAL NOT NULL, other_in_ml REAL NOT NULL,
            urine_ml REAL NOT NULL, other_out_ml REAL NOT NULL, hours REAL NOT NULL,
            total_in_ml REAL NOT NULL, total_out_ml REAL NOT NULL,
            net_ml REAL NOT NULL, urine_ml_kg_hr REAL NOT NULL
        )""")

def now_utc():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def save_observation(patient_id, hr, rr, temp, spo2, fio2, support):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""INSERT INTO observations
            (patient_id, recorded_at, hr, rr, temp_c, spo2, fio2, support)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (patient_id, now_utc(), hr, rr, temp, spo2, fio2, support))

def save_fluids(patient_id, values):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""INSERT INTO fluid_records
            (patient_id, recorded_at, iv_ml, feeds_ml, other_in_ml, urine_ml,
             other_out_ml, hours, total_in_ml, total_out_ml, net_ml, urine_ml_kg_hr)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (patient_id, now_utc(), *values))

def read_rows(table, patient_id):
    allowed = {"observations", "fluid_records"}
    if table not in allowed:
        raise ValueError("Unsupported table")
    with sqlite3.connect(DB_PATH) as conn:
        return conn.execute(
            f"SELECT * FROM {table} WHERE patient_id = ? ORDER BY id DESC LIMIT 20",
            (patient_id,)
        ).fetchall()

init_db()
st.title("🩺 Today Nurse")
st.subheader("NICU Digital Monitoring System · Lesson 2")
st.warning("PUBLIC EDUCATIONAL DEMO ONLY. Use fictional data only. Entries may be visible to other visitors and may be lost after hosting restarts. Never enter real patient information.")

with st.sidebar:
    patient_id = st.selectbox("Fictional patient", ["DEMO-001", "DEMO-002"])
    if patient_id == "DEMO-001":
        gestation, weight_g = "32 weeks", 1650
    else:
        gestation, weight_g = "35 weeks", 2200
    st.caption("All patient details are fictional.")

c1, c2, c3 = st.columns(3)
c1.metric("Demo ID", patient_id)
c2.metric("Gestational age", gestation)
c3.metric("Weight", f"{weight_g:,} g")

st.divider()
st.markdown("### 1. Save a practice vital-sign observation")
with st.form("obs_form"):
    a, b = st.columns(2)
    with a:
        hr = st.number_input("Heart rate (bpm)", 0, 300, 140)
        rr = st.number_input("Respiratory rate (/min)", 0, 150, 45)
        temp = st.number_input("Temperature (°C)", 25.0, 45.0, 36.7, step=0.1)
    with b:
        spo2 = st.number_input("SpO₂ (%)", 0, 100, 96)
        fio2 = st.number_input("FiO₂ (%)", 21, 100, 21)
        support = st.selectbox("Respiratory support", ["Room air", "Oxygen", "CPAP", "Other / not specified"])
    submit_obs = st.form_submit_button("Save observation")
if submit_obs:
    save_observation(patient_id, hr, rr, temp, spo2, fio2, support)
    st.success("Saved to the SQLite demo database.")

st.divider()
st.markdown("### 2. Calculate and save practice intake/output")
with st.form("fluid_form"):
    a, b = st.columns(2)
    with a:
        iv = st.number_input("IV fluid (mL)", 0.0, 5000.0, 120.0, step=1.0)
        feeds = st.number_input("Feeds (mL)", 0.0, 2000.0, 80.0, step=1.0)
        other_in = st.number_input("Other intake (mL)", 0.0, 2000.0, 0.0, step=1.0)
    with b:
        urine = st.number_input("Urine (mL)", 0.0, 5000.0, 90.0, step=1.0)
        other_out = st.number_input("Other output (mL)", 0.0, 5000.0, 5.0, step=1.0)
        hours = st.number_input("Monitoring interval (hours)", 1.0, 24.0, 24.0, step=1.0)
    submit_fluid = st.form_submit_button("Calculate and save fluid record")
if submit_fluid:
    total_in = iv + feeds + other_in
    total_out = urine + other_out
    net = total_in - total_out
    urine_rate = urine / (weight_g / 1000) / hours
    save_fluids(patient_id, [iv, feeds, other_in, urine, other_out, hours, total_in, total_out, net, urine_rate])
    x1, x2, x3, x4 = st.columns(4)
    x1.metric("Total intake", f"{total_in:.1f} mL")
    x2.metric("Total output", f"{total_out:.1f} mL")
    x3.metric("Net balance", f"{net:+.1f} mL")
    x4.metric("Urine output", f"{urine_rate:.2f} mL/kg/hr")
    st.success("Fluid record saved.")

st.divider()
st.markdown("### 3. Saved practice records")
tab1, tab2 = st.tabs(["Vital signs", "Fluid records"])
with tab1:
    rows = read_rows("observations", patient_id)
    if rows:
        st.dataframe([{"Recorded (UTC)": r[2], "HR": r[3], "RR": r[4], "Temp °C": r[5],
                       "SpO₂ %": r[6], "FiO₂ %": r[7], "Support": r[8]} for r in rows],
                     use_container_width=True, hide_index=True)
    else:
        st.info("No saved observations yet.")
with tab2:
    rows = read_rows("fluid_records", patient_id)
    if rows:
        st.dataframe([{"Recorded (UTC)": r[2], "Intake mL": r[9], "Output mL": r[10],
                       "Net mL": r[11], "Urine mL/kg/hr": r[12]} for r in rows],
                     use_container_width=True, hide_index=True)
    else:
        st.info("No saved fluid records yet.")

with st.expander("Lesson 2: what the new code does"):
    st.markdown("""
    - **SQLite** stores records in a database file.
    - `CREATE TABLE` defines the columns.
    - `INSERT` saves a new record.
    - `SELECT` retrieves saved records.
    - `?` placeholders keep user-entered values separate from SQL instructions.
    """)

st.caption("Today Nurse · Educational prototype · Version 0.2 · Not for clinical use")
