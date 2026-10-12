import sqlite3
from datetime import date, datetime, timezone
import streamlit as st
import pandas as pd
import math
DB = "today_nurse_demo.db"
PATIENTS = {
    "DEMO-001": {"name": "Baby A (fictional)", "gestation": "32 weeks", "weight_g": 1650},
    "DEMO-002": {"name": "Baby B (fictional)", "gestation": "35 weeks", "weight_g": 2200},
} 
st.set_page_config(page_title="Today Nurse | Daily NICU Monitoring", page_icon="🩺", layout="wide")

def connect():
    return sqlite3.connect(DB)

def init_db():
    with connect() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS daily_observations (
            id INTEGER PRIMARY KEY AUTOINCREMENT, patient_id TEXT NOT NULL,
            monitor_date TEXT NOT NULL, saved_utc TEXT NOT NULL, obs_time TEXT NOT NULL,
            hr INTEGER NOT NULL, rr INTEGER NOT NULL, temp_c REAL NOT NULL,
            spo2 INTEGER NOT NULL, fio2 INTEGER NOT NULL, support TEXT NOT NULL, note TEXT)""")
        c.execute("""CREATE TABLE IF NOT EXISTS daily_fluids (
            id INTEGER PRIMARY KEY AUTOINCREMENT, patient_id TEXT NOT NULL,
            monitor_date TEXT NOT NULL, saved_utc TEXT NOT NULL, iv_ml REAL NOT NULL,
            feeds_ml REAL NOT NULL, meds_ml REAL NOT NULL, other_in_ml REAL NOT NULL,
            urine_ml REAL NOT NULL, stool_count INTEGER NOT NULL, other_out_ml REAL NOT NULL,
            hours REAL NOT NULL, total_in REAL NOT NULL, total_out REAL NOT NULL,
            net_ml REAL NOT NULL, urine_ml_kg_hr REAL NOT NULL)""")

def timestamp():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def add_observation(pid, day, t, hr, rr, temp, spo2, fio2, support, note):
    with connect() as c:
        c.execute("""INSERT INTO daily_observations
        (patient_id, monitor_date, saved_utc, obs_time, hr, rr, temp_c, spo2, fio2, support, note)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (pid, day.isoformat(), timestamp(), t.strftime("%H:%M"), hr, rr, temp, spo2, fio2, support, note))

def add_fluids(pid, day, iv, feeds, meds, other_in, urine, stools, other_out, hours, weight_g):

    # LESSON 9: Input validation
    numeric_inputs = {
        "IV fluids": iv,
        "Feeds": feeds,
        "Medication fluids": meds,
        "Other intake": other_in,
        "Urine": urine,
        "Stool count": stools,
        "Other output": other_out,
        "Monitoring hours": hours,
        "Weight": weight_g,
    }

    for label, value in numeric_inputs.items():
        if not isinstance(value, (int, float)):
            raise ValueError(f"{label} must be numeric.")
        if not math.isfinite(value):
            raise ValueError(f"{label} must be a finite number.")

    if any(value < 0 for value in [
        iv, feeds, meds, other_in, urine, stools, other_out
    ]):
        raise ValueError(
            "Fluid volumes and stool count cannot be negative."
        )

    if not float(stools).is_integer():
        raise ValueError("Stool count must be a whole number.")

    if hours <= 0:
        raise ValueError(
            "Monitoring hours must be greater than zero."
        )

    if weight_g <= 0:
        raise ValueError("Weight must be greater than zero.")

    # Existing calculations: keep these
    total_in = iv + feeds + meds + other_in
    total_out = urine + other_out
    net = total_in - total_out
    urine_rate = urine / (weight_g / 1000) / hours

    
    with connect() as c:
        c.execute(
            """INSERT INTO daily_fluids (
                patient_id, monitor_date, saved_utc,
                iv_ml, feeds_ml, meds_ml, other_in_ml,
                urine_ml, stool_count, other_out_ml,
                hours, total_in, total_out, net_ml,
                urine_ml_kg_hr
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                pid, day.isoformat(),
                datetime.now(timezone.utc).isoformat(),
                iv, feeds, meds, other_in,
                urine, int(stools), other_out,
                hours, total_in, total_out, net, urine_rate
            )
        )

    return total_in, total_out, net, urine_rate



init_db()
st.title("🩺 Today Nurse")
st.subheader("NICU Digital Monitoring System · Lesson 3")
st.warning("PUBLIC EDUCATIONAL DEMO ONLY. Fictional data only. No login/access controls. Never enter real patient information. Not for clinical care.")

# LESSON 8: Dashboard overview
st.caption("Educational NICU monitoring prototype | Version 0.8")

st.info(
    "DEMO ONLY: Use fictional data. "
    "This prototype is not validated for clinical decisions."
)

with st.sidebar:
    pid = st.selectbox("Fictional patient", list(PATIENTS))
    patient = PATIENTS[pid]
    day = st.date_input("Monitoring sheet date", value=date.today())
    st.caption("Select the date once. Entries below are linked to this patient and date.")

# LESSON 8: Live dashboard summary cards

with connect() as c:
    latest_obs = c.execute(
        """
        SELECT obs_time, hr, rr, temp_c, spo2
        FROM daily_observations
        WHERE patient_id = ? AND monitor_date = ?
        ORDER BY obs_time DESC, id DESC
        LIMIT 1
        """,
        (pid, day.isoformat())
    ).fetchone()

    observation_count = c.execute(
        """
        SELECT COUNT(*)
        FROM daily_observations
        WHERE patient_id = ? AND monitor_date = ?
        """,
        (pid, day.isoformat())
    ).fetchone()[0]

    fluid_totals = c.execute(
        """
        SELECT
            COALESCE(SUM(total_in), 0),
            COALESCE(SUM(total_out), 0)
        FROM daily_fluids
        WHERE patient_id = ? AND monitor_date = ?
        """,
        (pid, day.isoformat())
    ).fetchone()

st.subheader("Dashboard overview")

if latest_obs:
    st.caption(f"Latest observation recorded at {latest_obs[0]}")

    cols = st.columns(4)

    cols[0].metric(
        "Heart rate",
        f"{latest_obs[1]} bpm" if latest_obs[1] is not None else "N/A"
    )
    cols[1].metric(
        "Respiratory rate",
        f"{latest_obs[2]} /min" if latest_obs[2] is not None else "N/A"
    )
    cols[2].metric(
        "Temperature",
        f"{latest_obs[3]} °C" if latest_obs[3] is not None else "N/A"
    )
    cols[3].metric(
        "SpO₂",
        f"{latest_obs[4]}%" if latest_obs[4] is not None else "N/A"
    )
else:
    st.info("No vital-sign observations are saved for this patient and date.")

col_a, col_b, col_c = st.columns(3)

col_a.metric("Observations recorded", observation_count)
col_b.metric("Total fluid intake", f"{fluid_totals[0]:.1f} mL")
col_c.metric("Total fluid output", f"{fluid_totals[1]:.1f} mL")

st.caption(
    "Values reflect saved fictional records only. "
    "They are not clinical alerts or treatment recommendations."
)

a, b, c = st.columns(3)
a.metric("Demo ID", pid)
b.metric("Gestational age", patient["gestation"])
c.metric("Weight", f'{patient["weight_g"]:,} g')
st.write(f'**Display name:** {patient["name"]}  |  **Monitoring date:** {day.strftime("%d %b %Y")}')
st.divider()

st.markdown("### 1. Add a timed vital-sign observation")
with st.form("obs_form"):
    x, y = st.columns(2)
    with x:
        obs_time = st.time_input("Observation time", value=datetime.now().time().replace(second=0, microsecond=0))
        hr = st.number_input("Heart rate (bpm)", 0, 300, 140)
        rr = st.number_input("Respiratory rate (/min)", 0, 150, 45)
        temp = st.number_input("Temperature (°C)", 25.0, 45.0, 36.7, step=0.1)
    with y:
        spo2 = st.number_input("SpO₂ (%)", 0, 100, 96)
        fio2 = st.number_input("FiO₂ (%)", 21, 100, 21)
        support = st.selectbox("Respiratory support", ["Room air", "Oxygen", "CPAP", "Other / not specified"])
    note = st.text_input("Fictional nursing note (no identifiers)")
    save_obs = st.form_submit_button("Save observation to daily sheet")
if save_obs:
    add_observation(pid, day, obs_time, hr, rr, temp, spo2, fio2, support, note)
    st.success(f"Saved for {pid} on {day.isoformat()} at {obs_time.strftime('%H:%M')}.")

st.divider()
st.markdown("### 2. Add an intake/output record")
with st.form("fluid_form"):
    x, y = st.columns(2)
    with x:
        iv = st.number_input("IV fluids (mL)", 0.0, 5000.0, 120.0, step=1.0)
        feeds = st.number_input("Feeds (mL)", 0.0, 2000.0, 80.0, step=1.0)
        meds = st.number_input("Medication fluid volume (mL)", 0.0, 2000.0, 0.0, step=1.0)
        other_in = st.number_input("Other intake (mL)", 0.0, 2000.0, 0.0, step=1.0)
    with y:
        urine = st.number_input("Urine (mL)", 0.0, 5000.0, 90.0, step=1.0)
        stools = st.number_input("Stool count", 0, 50, 1)
        other_out = st.number_input("Other measured output (mL)", 0.0, 5000.0, 5.0, step=1.0)
        hours = st.number_input("Monitoring interval (hours)", 1.0, 24.0, 24.0, step=1.0)
    save_fluid = st.form_submit_button("Calculate and save fluid record")

if save_fluid:
    weight_g = patient["weight_g"]

    if hours <= 0:
        st.error("Monitoring interval must be greater than zero.")
    elif weight_g is None or weight_g <= 0:
        st.error("A valid patient weight is required.")
    elif any(v < 0 for v in [
        iv, feeds, meds, other_in, urine, stools, other_out
    ]):
        st.error("Fluid inputs cannot be negative.")
    elif not float(stools).is_integer():
        st.error("Stool count must be a whole number.")
    else:
        try:
            totals = add_fluids(
                pid, day, iv, feeds, meds, other_in,
                urine, int(stools), other_out, hours, weight_g
            )

            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Total intake", f"{totals[0]:.1f} mL")
            m2.metric("Total output", f"{totals[1]:.1f} mL")
            m3.metric("Net balance", f"{totals[2]:+.1f} mL")
            m4.metric("Urine output", f"{totals[3]:.2f} mL/kg/hr")

            st.success("Fluid record saved.")
        except (ValueError, TypeError, ZeroDivisionError) as exc:
            st.error(f"Unable to save fluid record: {exc}")
        except sqlite3.Error:
            st.error(
                "The fluid record could not be saved because of a "
                "database error. Please try again."
            )

st.caption("Calculations are for software-learning only. Verify definitions and methods against approved local protocols before any clinical use.")
st.divider()
st.markdown("### 3. Records for this patient and date")
tab1, tab2 = st.tabs(["Vital-sign observations", "Intake/output records"])
with tab1:
    with connect() as c:
        rows = c.execute("""SELECT obs_time, hr, rr, temp_c, spo2, fio2, support, note, saved_utc
        FROM daily_observations WHERE patient_id=? AND monitor_date=? ORDER BY obs_time, id""",
        (pid, day.isoformat())).fetchall()
    if rows:
        st.dataframe([{"Time":r[0],"HR":r[1],"RR":r[2],"Temp °C":r[3],"SpO₂ %":r[4],
                       "FiO₂ %":r[5],"Support":r[6],"Note":r[7],"Saved UTC":r[8]} for r in rows],
                     use_container_width=True, hide_index=True)
    else:
        st.info("No observations saved for this patient and date.")
with tab2:
    with connect() as c:
        rows = c.execute("""SELECT saved_utc, iv_ml, feeds_ml, meds_ml, other_in_ml, urine_ml,
        stool_count, other_out_ml, hours, total_in, total_out, net_ml, urine_ml_kg_hr
        FROM daily_fluids WHERE patient_id=? AND monitor_date=? ORDER BY id DESC""",
        (pid, day.isoformat())).fetchall()
    if rows:
        st.dataframe([{"Saved UTC":r[0],"IV mL":r[1],"Feeds mL":r[2],"Medication fluids mL":r[3],
                       "Other intake mL":r[4],"Urine mL":r[5],"Stools":r[6],"Other output mL":r[7],
                       "Interval h":r[8],"Total intake mL":r[9],"Total output mL":r[10],
                       "Net mL":r[11],"Urine mL/kg/hr":round(r[12],3)} for r in rows],
                     use_container_width=True, hide_index=True)
    else:
        st.info("No fluid records saved for this patient and date.")

# LESSON 4: Daily summary and vital-sign trends
st.divider()
st.subheader("4. Daily summary and vital-sign trends")

with connect() as c:
    trend_rows = c.execute(
        """
        SELECT obs_time, hr, rr, temp_c
        FROM daily_observations
        WHERE patient_id = ? AND monitor_date = ?
        ORDER BY obs_time ASC, id ASC
        """,
        (pid, day.isoformat())
    ).fetchall()

if trend_rows:
    latest = trend_rows[-1]

    st.caption(
        "Summary of saved observations for the selected "
        "fictional patient and monitoring date."
    )

    m1, m2, m3 = st.columns(3)
    m1.metric("Observations", len(trend_rows))
    m2.metric("Latest HR", f"{latest[1]} bpm")
    m3.metric("Latest RR", f"{latest[2]} /min")

    st.write(
        f"Latest temperature: **{latest[3]:.1f} °C** "
        f"at **{latest[0]}**"
    )

    chart_tab1, chart_tab2, chart_tab3 = st.tabs(
        ["Heart rate", "Respiratory rate", "Temperature"]
    )

    times = [row[0] for row in trend_rows]

    with chart_tab1:
        df = pd.DataFrame({
            "Time": times,
            "Heart rate (bpm)": [row[1] for row in trend_rows]
        }).set_index("Time")
        st.line_chart(df)

    with chart_tab2:
        df = pd.DataFrame({
            "Time": times,
            "Respiratory rate (/min)": [
                row[2] for row in trend_rows
            ]
        }).set_index("Time")
        st.line_chart(df)

    with chart_tab3:
        df = pd.DataFrame({
            "Time": times,
            "Temperature (°C)": [
                row[3] for row in trend_rows
            ]
        }).set_index("Time")
        st.line_chart(df)

else:
    st.info(
        "No saved observations for this patient and date. "
        "Save a fictional observation to display the summary."
    )

st.caption(
    "Educational demonstration only. Charts and summaries "
    "are not validated clinical decision-support tools."
)
 
# LESSON 6: Daily fluid balance summary
st.divider()
st.subheader("6. Daily fluid balance summary")

with connect() as c:
    fluid_summary = c.execute(
        """
        SELECT
            COALESCE(SUM(total_in), 0),
            COALESCE(SUM(total_out), 0),
            COALESCE(SUM(net_ml), 0),
            COALESCE(SUM(urine_ml), 0),
            COALESCE(SUM(hours), 0),
            COALESCE(SUM(stool_count), 0),
            CASE
                WHEN COALESCE(SUM(hours), 0) > 0
                THEN SUM(
                    COALESCE(urine_ml_kg_hr, 0) * COALESCE(hours, 0)
                ) / SUM(hours)
                ELSE NULL
            END
        FROM daily_fluids
        WHERE patient_id = ? AND monitor_date = ?
        """,
        (pid, day.isoformat())
    ).fetchone()

total_in, total_out, net_balance, urine_total, total_hours, stools, urine_rate = fluid_summary

st.write(f"**Patient:** {pid}  |  **Date:** {day.strftime('%d %b %Y')}")

if total_hours > 0:
    col1, col2 = st.columns(2)

    with col1:
        st.metric("Total intake", f"{total_in:.1f} mL")
        st.metric("Total output", f"{total_out:.1f} mL")
    
    with col2:
        st.metric("Net fluid balance", f"{net_balance:+.1f} mL")
        st.metric("Urine output", f"{urine_rate:.2f} mL/kg/hr"
                  if urine_rate is not None else "Not available")

    st.write(f"**Total recorded urine:** {urine_total:.1f} mL")
    st.write(f"**Recorded monitoring hours:** {total_hours:.1f}")
    st.write(f"**Recorded stool count:** {int(stools or 0)}")

    st.caption(
        "Educational summary of recorded fictional data only. "
        "Verify calculations before any clinical use."
    )
else:
    st.info(
        "No fluid records with recorded monitoring hours exist "
        "for this patient and date."
    )

# LESSON 7: Fluid records table and CSV export
st.divider()
st.subheader("7. Fluid records and CSV export")

with connect() as c:
    fluid_rows = c.execute(
        """
        SELECT
            saved_utc, iv_ml, feeds_ml, meds_ml, other_in_ml,
            urine_ml, stool_count, other_out_ml, hours,
            total_in, total_out, net_ml, urine_ml_kg_hr
        FROM daily_fluids
        WHERE patient_id = ? AND monitor_date = ?
        ORDER BY saved_utc ASC, id ASC
        """,
        (pid, day.isoformat())
    ).fetchall()

if fluid_rows:
    fluid_df = pd.DataFrame(
        fluid_rows,
        columns=[
            "Saved at (UTC)", "IV fluids (mL)", "Feeds (mL)",
            "Medications (mL)", "Other intake (mL)", "Urine (mL)",
            "Stool count", "Other output (mL)", "Hours",
            "Total intake (mL)", "Total output (mL)",
            "Net balance (mL)", "Urine output (mL/kg/hr)"
        ]
    )

    st.write(f"**Patient:** {pid}  |  **Date:** {day.strftime('%d %b %Y')}")
    st.dataframe(fluid_df, use_container_width=True, hide_index=True)

    fluid_csv = fluid_df.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        label="Download fluid records (CSV)",
        data=fluid_csv,
        file_name=f"{pid}_{day.isoformat()}_fluid_records.csv",
        mime="text/csv",
        key="fluid_records_csv"
    )
else:
    st.info("No fluid records are available for this patient and date.")

st.caption(
    "Educational export using fictional data only. "
    "Not validated for clinical decision-making."
)

with st.expander("Dates with saved records"):
    with connect() as c:
        dates = c.execute("""SELECT DISTINCT monitor_date FROM (
            SELECT monitor_date FROM daily_observations WHERE patient_id=?
            UNION SELECT monitor_date FROM daily_fluids WHERE patient_id=?
        ) ORDER BY monitor_date DESC""", (pid, pid)).fetchall()
    st.write(", ".join(r[0] for r in dates) if dates else "No saved dates yet.")

with st.expander("Lesson 3: what changed?"):
    st.markdown("""
    - Select a patient and monitoring date once.
    - Each vital-sign entry is linked to that patient, date, and observation time.
    - Fluid records are also linked to the selected patient and date.
    - The screen filters records by patient and date.
    - This remains a public demo using local SQLite storage, which may be reset by the host.
    """)
st.caption("Today Nurse · Educational prototype · Version 0.3 · Not for clinical use")
