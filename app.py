import math
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timezone

import pandas as pd
import streamlit as st

DB = "today_nurse_demo.db"
APP_VERSION = "1.0"
PATIENTS = {
    "DEMO-001": {
        "name": "Baby A (fictional)",
        "gestation": "32 weeks",
        "weight_g": 1650,
    },
    "DEMO-002": {
        "name": "Baby B (fictional)",
        "gestation": "35 weeks",
        "weight_g": 2200,
    },
}

st.set_page_config(
    page_title="Today Nurse | NICU Nursing Documentation",
    page_icon="🩺",
    layout="wide",
)


@contextmanager
def connect():
    """Open a SQLite connection and always close it."""
    conn = sqlite3.connect(DB, timeout=10)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS daily_observations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                patient_id TEXT NOT NULL,
                monitor_date TEXT NOT NULL,
                saved_utc TEXT NOT NULL,
                obs_time TEXT NOT NULL,
                hr INTEGER NOT NULL,
                rr INTEGER NOT NULL,
                temp_c REAL NOT NULL,
                spo2 INTEGER NOT NULL,
                fio2 INTEGER NOT NULL,
                support TEXT NOT NULL,
                note TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS daily_fluids (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                patient_id TEXT NOT NULL,
                monitor_date TEXT NOT NULL,
                saved_utc TEXT NOT NULL,
                iv_ml REAL NOT NULL,
                feeds_ml REAL NOT NULL,
                meds_ml REAL NOT NULL,
                other_in_ml REAL NOT NULL,
                urine_ml REAL NOT NULL,
                stool_count INTEGER NOT NULL,
                other_out_ml REAL NOT NULL,
                hours REAL NOT NULL,
                weight_g REAL NOT NULL,
                total_in REAL NOT NULL,
                total_out REAL NOT NULL,
                net_ml REAL NOT NULL,
                urine_ml_kg_hr REAL NOT NULL
            )
            """
        )

        # Safe migration for databases created by the earlier app version.
        fluid_columns = {
            row[1] for row in conn.execute("PRAGMA table_info(daily_fluids)")
        }
        if "weight_g" not in fluid_columns:
            conn.execute(
                "ALTER TABLE daily_fluids "
                "ADD COLUMN weight_g REAL NOT NULL DEFAULT 1"
            )

        # Additional nursing-documentation modules. These store documentation only;
        # they do not prescribe, calculate, or authorize clinical treatment.
        conn.execute("""
            CREATE TABLE IF NOT EXISTS nicu_admissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT, patient_id TEXT NOT NULL,
                admission_date TEXT NOT NULL, admission_time TEXT NOT NULL,
                gestational_age TEXT, birth_weight_g REAL, current_weight_g REAL,
                sex TEXT, delivery_mode TEXT, apgar TEXT, admission_reason TEXT NOT NULL,
                maternal_perinatal_history TEXT, initial_condition TEXT,
                respiratory_support TEXT, lines_devices TEXT, initial_assessment TEXT,
                nursing_priorities TEXT, created_utc TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS medication_administration (
                id INTEGER PRIMARY KEY AUTOINCREMENT, patient_id TEXT NOT NULL,
                record_date TEXT NOT NULL, medication TEXT NOT NULL, prescribed_dose TEXT NOT NULL,
                route TEXT NOT NULL, scheduled_time TEXT, status TEXT NOT NULL,
                administration_time TEXT, weight_g REAL, allergy_check INTEGER NOT NULL,
                independent_double_check INTEGER NOT NULL, nurse_name TEXT,
                reason_or_indication TEXT, omission_reason TEXT, notes TEXT, created_utc TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS head_to_toe_assessments (
                id INTEGER PRIMARY KEY AUTOINCREMENT, patient_id TEXT NOT NULL,
                assessment_date TEXT NOT NULL, assessment_time TEXT NOT NULL,
                neuro TEXT, respiratory TEXT, cardiovascular TEXT, temperature_skin TEXT,
                gi_feeding TEXT, genitourinary TEXT, musculoskeletal TEXT,
                lines_tubes TEXT, pain_score TEXT, infection_risk TEXT,
                findings_interventions TEXT, escalation TEXT, nurse_name TEXT, created_utc TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS patient_handovers (
                id INTEGER PRIMARY KEY AUTOINCREMENT, patient_id TEXT NOT NULL,
                handover_date TEXT NOT NULL, handover_time TEXT NOT NULL,
                outgoing_nurse TEXT, incoming_nurse TEXT, situation TEXT NOT NULL,
                background TEXT, assessment TEXT, recommendation TEXT,
                pending_tasks TEXT, escalation_plan TEXT, acknowledgement TEXT, created_utc TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS equipment_handovers (
                id INTEGER PRIMARY KEY AUTOINCREMENT, patient_id TEXT NOT NULL,
                handover_date TEXT NOT NULL, handover_time TEXT NOT NULL,
                equipment_type TEXT NOT NULL, equipment_id TEXT, condition_status TEXT NOT NULL,
                function_check TEXT, alarm_check TEXT, power_gas_check TEXT,
                consumables_check TEXT, fault_or_issue TEXT, action_taken TEXT,
                outgoing_staff TEXT, incoming_staff TEXT, notes TEXT, created_utc TEXT NOT NULL
            )
        """)


def timestamp_utc():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def validate_observation(hr, rr, temp, spo2, fio2, note):
    values = {
        "Heart rate": hr,
        "Respiratory rate": rr,
        "Temperature": temp,
        "SpO₂": spo2,
        "FiO₂": fio2,
    }
    for label, value in values.items():
        if not math.isfinite(float(value)):
            raise ValueError(f"{label} must be a finite number.")

    if not 1 <= int(hr) <= 300:
        raise ValueError("Heart rate must be between 1 and 300 bpm.")
    if not 1 <= int(rr) <= 150:
        raise ValueError("Respiratory rate must be between 1 and 150/min.")
    if not 25.0 <= float(temp) <= 45.0:
        raise ValueError("Temperature must be between 25.0 and 45.0 °C.")
    if not 1 <= int(spo2) <= 100:
        raise ValueError("SpO₂ must be between 1 and 100%.")
    if not 21 <= int(fio2) <= 100:
        raise ValueError("FiO₂ must be between 21 and 100%.")
    if len(note) > 1000:
        raise ValueError("The note must be 1,000 characters or fewer.")


def add_observation(pid, day, obs_time, hr, rr, temp, spo2, fio2, support, note):
    validate_observation(hr, rr, temp, spo2, fio2, note)
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO daily_observations (
                patient_id, monitor_date, saved_utc, obs_time,
                hr, rr, temp_c, spo2, fio2, support, note
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                pid, day.isoformat(), timestamp_utc(),
                obs_time.strftime("%H:%M"), int(hr), int(rr),
                float(temp), int(spo2), int(fio2), support, note.strip(),
            ),
        )


def add_fluids(
    pid, day, iv, feeds, meds, other_in, urine, stools,
    other_out, hours, weight_g
):
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
        if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            raise ValueError(f"{label} must be a finite number.")

    volumes = [iv, feeds, meds, other_in, urine, other_out]
    if any(float(value) < 0 for value in volumes):
        raise ValueError("Fluid volumes cannot be negative.")
    if stools < 0 or not float(stools).is_integer():
        raise ValueError("Stool count must be a non-negative whole number.")
    if not 0 < float(hours) <= 24:
        raise ValueError("Monitoring interval must be greater than 0 and at most 24 hours.")
    if weight_g <= 0:
        raise ValueError("Weight must be greater than zero.")

    total_in = float(iv + feeds + meds + other_in)
    total_out = float(urine + other_out)
    net = total_in - total_out
    urine_rate = float(urine) / (float(weight_g) / 1000.0) / float(hours)

    with connect() as conn:
        conn.execute(
            """
            INSERT INTO daily_fluids (
                patient_id, monitor_date, saved_utc, iv_ml, feeds_ml,
                meds_ml, other_in_ml, urine_ml, stool_count, other_out_ml,
                hours, weight_g, total_in, total_out, net_ml, urine_ml_kg_hr
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                pid, day.isoformat(), timestamp_utc(),
                float(iv), float(feeds), float(meds), float(other_in),
                float(urine), int(stools), float(other_out),
                float(hours), float(weight_g), total_in, total_out,
                net, urine_rate,
            ),
        )

    return total_in, total_out, net, urine_rate


init_db()

st.title("🩺 Today Nurse")
st.subheader("NICU Monitoring & Nursing Documentation System · Version 1.0")
st.warning(
    "PUBLIC EDUCATIONAL DEMO ONLY. Use fictional data only. "
    "No authentication or access controls. Never enter real patient information. "
    "Not validated for clinical care."
)
st.caption("Educational NICU monitoring prototype")

with st.sidebar:
    st.header("Demo patient")
    pid = st.selectbox("Fictional patient", list(PATIENTS))
    patient = PATIENTS[pid]
    day = st.date_input("Monitoring sheet date", value=date.today())
    st.caption("Entries are filtered by the selected patient and date.")

# Dashboard summary: newest saved observation, not latest clock time.
with connect() as conn:
    latest_obs = conn.execute(
        """
        SELECT obs_time, hr, rr, temp_c, spo2, saved_utc
        FROM daily_observations
        WHERE patient_id = ? AND monitor_date = ?
        ORDER BY saved_utc DESC, id DESC
        LIMIT 1
        """,
        (pid, day.isoformat()),
    ).fetchone()

    observation_count = conn.execute(
        """
        SELECT COUNT(*) FROM daily_observations
        WHERE patient_id = ? AND monitor_date = ?
        """,
        (pid, day.isoformat()),
    ).fetchone()[0]

    fluid_totals = conn.execute(
        """
        SELECT COALESCE(SUM(total_in), 0), COALESCE(SUM(total_out), 0)
        FROM daily_fluids
        WHERE patient_id = ? AND monitor_date = ?
        """,
        (pid, day.isoformat()),
    ).fetchone()

st.subheader("Dashboard overview")
if latest_obs:
    st.caption(
        f"Most recently saved observation: measurement time {latest_obs[0]}, "
        f"saved UTC {latest_obs[5]}"
    )
    cols = st.columns(4)
    cols[0].metric("Heart rate", f"{latest_obs[1]} bpm")
    cols[1].metric("Respiratory rate", f"{latest_obs[2]} /min")
    cols[2].metric("Temperature", f"{latest_obs[3]:.1f} °C")
    cols[3].metric("SpO₂", f"{latest_obs[4]}%")
else:
    st.info("No vital-sign observations are saved for this patient and date.")

col_a, col_b, col_c = st.columns(3)
col_a.metric("Observations recorded", observation_count)
col_b.metric("Total recorded intake", f"{fluid_totals[0]:.1f} mL")
col_c.metric("Total recorded output", f"{fluid_totals[1]:.1f} mL")

a, b, c = st.columns(3)
a.metric("Demo ID", pid)
b.metric("Gestational age", patient["gestation"])
b.caption("Fictional demonstration value")
c.metric("Reference weight", f'{patient["weight_g"]:,} g')
st.write(
    f'**Display name:** {patient["name"]}  |  '
    f'**Monitoring date:** {day.strftime("%d %b %Y")}'
)
st.caption(
    "Summed fluid values are totals of saved records, not proof of complete "
    "24-hour intake or output. Ensure records represent separate intervals."
)
st.divider()

st.markdown("### 1. Add a timed vital-sign observation")
with st.form("obs_form"):
    x, y = st.columns(2)
    with x:
        obs_time = st.time_input(
            "Observation time",
            value=datetime.now().time().replace(second=0, microsecond=0),
        )
        hr = st.number_input("Heart rate (bpm)", min_value=1, max_value=300, value=140)
        rr = st.number_input("Respiratory rate (/min)", min_value=1, max_value=150, value=45)
        temp = st.number_input(
            "Temperature (°C)", min_value=25.0, max_value=45.0,
            value=36.7, step=0.1, format="%.1f"
        )
    with y:
        spo2 = st.number_input("SpO₂ (%)", min_value=1, max_value=100, value=96)
        fio2 = st.number_input("FiO₂ (%)", min_value=21, max_value=100, value=21)
        support = st.selectbox(
            "Respiratory support",
            ["Room air", "Oxygen", "CPAP", "Other / not specified"],
        )
    note = st.text_input("Fictional nursing note (no identifiers)", max_chars=1000)
    save_obs = st.form_submit_button("Save observation")

if save_obs:
    try:
        add_observation(pid, day, obs_time, hr, rr, temp, spo2, fio2, support, note)
        st.success(
            f"Saved for {pid} on {day.isoformat()} at {obs_time.strftime('%H:%M')}."
        )
    except ValueError as exc:
        st.error(str(exc))
    except sqlite3.Error:
        st.error("The observation could not be saved because of a database error.")

st.divider()
st.markdown("### 2. Add an intake/output record")
st.caption(
    "Enter values for one clearly defined monitoring interval only. "
    "Do not save overlapping intervals as if they were separate."
)
with st.form("fluid_form"):
    x, y = st.columns(2)
    with x:
        iv = st.number_input("IV fluids (mL)", min_value=0.0, max_value=5000.0, value=0.0, step=1.0)
        feeds = st.number_input("Feeds (mL)", min_value=0.0, max_value=2000.0, value=0.0, step=1.0)
        meds = st.number_input("Medication fluid volume (mL)", min_value=0.0, max_value=2000.0, value=0.0, step=1.0)
        other_in = st.number_input("Other intake (mL)", min_value=0.0, max_value=2000.0, value=0.0, step=1.0)
    with y:
        urine = st.number_input("Urine (mL)", min_value=0.0, max_value=5000.0, value=0.0, step=1.0)
        stools = st.number_input("Stool count", min_value=0, max_value=50, value=0)
        other_out = st.number_input("Other measured output (mL)", min_value=0.0, max_value=5000.0, value=0.0, step=1.0)
        hours = st.number_input(
            "Monitoring interval (hours)", min_value=0.25,
            max_value=24.0, value=1.0, step=0.25
        )
    confirm_fluid = st.checkbox("I have checked these fictional values and the interval.")
    save_fluid = st.form_submit_button("Calculate and save fluid record")

if save_fluid:
    if not confirm_fluid:
        st.error("Confirm the entered demonstration values before saving.")
    else:
        try:
            totals = add_fluids(
                pid, day, iv, feeds, meds, other_in,
                urine, stools, other_out, hours, patient["weight_g"]
            )
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Total intake", f"{totals[0]:.1f} mL")
            m2.metric("Total output", f"{totals[1]:.1f} mL")
            m3.metric("Net balance", f"{totals[2]:+.1f} mL")
            m4.metric("Urine output", f"{totals[3]:.2f} mL/kg/hr")
            st.success("Fictional fluid record saved.")
        except (ValueError, TypeError) as exc:
            st.error(f"Unable to save fluid record: {exc}")
        except sqlite3.Error:
            st.error("The fluid record could not be saved because of a database error.")

st.caption(
    "Calculations are for software-learning only. Verify definitions and "
    "methods against approved local protocols before any clinical use."
)
st.divider()

st.markdown("### 3. Records for this patient and date")
tab1, tab2 = st.tabs(["Vital-sign observations", "Intake/output records"])

with tab1:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT obs_time, hr, rr, temp_c, spo2, fio2, support, note, saved_utc
            FROM daily_observations
            WHERE patient_id = ? AND monitor_date = ?
            ORDER BY obs_time ASC, saved_utc ASC, id ASC
            """,
            (pid, day.isoformat()),
        ).fetchall()
    if rows:
        obs_df = pd.DataFrame(
            rows,
            columns=[
                "Time", "HR (bpm)", "RR (/min)", "Temp (°C)", "SpO₂ (%)",
                "FiO₂ (%)", "Support", "Note", "Saved at (UTC)",
            ],
        )
        st.dataframe(obs_df, use_container_width=True, hide_index=True)
        st.download_button(
            "Download vital-sign observations (CSV)",
            data=obs_df.to_csv(index=False).encode("utf-8-sig"),
            file_name=f"{pid}_{day.isoformat()}_observations.csv",
            mime="text/csv",
            key="observations_csv",
        )
    else:
        st.info("No observations saved for this patient and date.")

with tab2:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT saved_utc, iv_ml, feeds_ml, meds_ml, other_in_ml,
                   urine_ml, stool_count, other_out_ml, hours, weight_g,
                   total_in, total_out, net_ml, urine_ml_kg_hr
            FROM daily_fluids
            WHERE patient_id = ? AND monitor_date = ?
            ORDER BY saved_utc DESC, id DESC
            """,
            (pid, day.isoformat()),
        ).fetchall()
    if rows:
        fluid_history_df = pd.DataFrame(
            rows,
            columns=[
                "Saved at (UTC)", "IV (mL)", "Feeds (mL)", "Medication fluids (mL)",
                "Other intake (mL)", "Urine (mL)", "Stool count",
                "Other output (mL)", "Interval (h)", "Weight used (g)",
                "Total intake (mL)", "Total output (mL)", "Net balance (mL)",
                "Urine output (mL/kg/hr)",
            ],
        )
        st.dataframe(fluid_history_df, use_container_width=True, hide_index=True)
    else:
        st.info("No fluid records saved for this patient and date.")

st.divider()
st.subheader("4. Daily summary and vital-sign trends")

with connect() as conn:
    trend_rows = conn.execute(
        """
        SELECT obs_time, hr, rr, temp_c, saved_utc
        FROM daily_observations
        WHERE patient_id = ? AND monitor_date = ?
        ORDER BY obs_time ASC, saved_utc ASC, id ASC
        """,
        (pid, day.isoformat()),
    ).fetchall()

if trend_rows:
    trend_df = pd.DataFrame(
        trend_rows,
        columns=["Time", "Heart rate (bpm)", "Respiratory rate (/min)", "Temperature (°C)", "Saved at (UTC)"],
    )
    st.caption("Trends show saved fictional observations, ordered by entered measurement time.")
    chart_tab1, chart_tab2, chart_tab3 = st.tabs(
        ["Heart rate", "Respiratory rate", "Temperature"]
    )
    with chart_tab1:
        st.line_chart(trend_df.set_index("Time")[["Heart rate (bpm)"]])
    with chart_tab2:
        st.line_chart(trend_df.set_index("Time")[["Respiratory rate (/min)"]])
    with chart_tab3:
        st.line_chart(trend_df.set_index("Time")[["Temperature (°C)"]])
else:
    st.info("No saved observations for this patient and date.")

st.divider()
st.subheader("5. Daily fluid balance summary")

with connect() as conn:
    fluid_rows = conn.execute(
        """
        SELECT iv_ml, feeds_ml, meds_ml, other_in_ml, urine_ml, stool_count,
               other_out_ml, hours, weight_g, total_in, total_out, net_ml
        FROM daily_fluids
        WHERE patient_id = ? AND monitor_date = ?
        ORDER BY saved_utc ASC, id ASC
        """,
        (pid, day.isoformat()),
    ).fetchall()

if fluid_rows:
    fdf = pd.DataFrame(
        fluid_rows,
        columns=[
            "IV (mL)", "Feeds (mL)", "Medication fluids (mL)", "Other intake (mL)",
            "Urine (mL)", "Stool count", "Other output (mL)", "Interval (h)",
            "Weight used (g)", "Total intake (mL)", "Total output (mL)", "Net balance (mL)",
        ],
    )
    total_in = float(fdf["Total intake (mL)"].sum())
    total_out = float(fdf["Total output (mL)"].sum())
    net_balance = float(fdf["Net balance (mL)"].sum())
    urine_total = float(fdf["Urine (mL)"].sum())
    stool_total = int(fdf["Stool count"].sum())
    total_hours = float(fdf["Interval (h)"].sum())

    c1, c2, c3 = st.columns(3)
    c1.metric("Recorded intake total", f"{total_in:.1f} mL")
    c2.metric("Recorded output total", f"{total_out:.1f} mL")
    c3.metric("Recorded net balance", f"{net_balance:+.1f} mL")
    st.write(f"**Total recorded urine:** {urine_total:.1f} mL")
    st.write(f"**Sum of entered intervals:** {total_hours:.2f} hours")
    st.write(f"**Recorded stool count:** {stool_total}")

    # Do not average rates from intervals with different weights.
    weights = fdf["Weight used (g)"].dropna().unique()
    if len(weights) == 1 and total_hours > 0:
        daily_rate = urine_total / (float(weights[0]) / 1000.0) / total_hours
        st.metric("Interval-weighted urine output estimate", f"{daily_rate:.2f} mL/kg/hr")
    else:
        st.info(
            "A combined urine-output rate is not shown because the saved records "
            "use different weights or have no valid summed interval."
        )
    st.caption(
        "This is an arithmetic summary of entered records only. The summed interval "
        "is not proof of continuous, non-overlapping monitoring. Verify completeness "
        "and interval timing before interpreting any result."
    )
else:
    st.info("No fluid records are available for this patient and date.")

st.divider()
st.subheader("6. Export fluid records")
if fluid_rows:
    export_df = pd.DataFrame(
        fluid_rows,
        columns=[
            "IV (mL)", "Feeds (mL)", "Medication fluids (mL)", "Other intake (mL)",
            "Urine (mL)", "Stool count", "Other output (mL)", "Interval (h)",
            "Weight used (g)", "Total intake (mL)", "Total output (mL)", "Net balance (mL)",
        ],
    )
    st.download_button(
        "Download fluid records (CSV)",
        data=export_df.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"{pid}_{day.isoformat()}_fluid_records.csv",
        mime="text/csv",
        key="fluid_records_csv",
    )


st.divider()
st.header("7. NICU Nursing Documentation")
st.caption("These forms are linked to the selected fictional demo patient. Save only fictional training data in this public demo.")

admission_tab, medication_tab, assessment_tab, patient_handover_tab, equipment_tab = st.tabs([
    "🍼 Initial Admission", "💊 Medication Record", "🩺 Head-to-Toe Assessment",
    "🤝 Patient Handover", "⚙️ Equipment Handover"
])

with admission_tab:
    st.markdown("#### Initial NICU admission record")
    with st.form("initial_admission_form"):
        c1, c2, c3 = st.columns(3)
        admission_date = c1.date_input("Admission date", value=day, key="adm_date")
        admission_time = c2.text_input("Admission time (HH:MM)", value="08:00", key="adm_time")
        sex = c3.selectbox("Sex", ["Not recorded", "Female", "Male", "Indeterminate / not documented"], key="adm_sex")
        c4, c5, c6 = st.columns(3)
        gestation = c4.text_input("Gestational age", value=patient["gestation"], help="Example: 32+4 weeks")
        birth_weight = c5.number_input("Birth weight (g)", min_value=0, max_value=10000, value=int(patient["weight_g"]), step=10)
        current_weight = c6.number_input("Current weight at admission (g)", min_value=0, max_value=10000, value=int(patient["weight_g"]), step=10)
        c7, c8 = st.columns(2)
        delivery_mode = c7.selectbox("Delivery mode", ["Not recorded", "Vaginal", "Caesarean", "Assisted vaginal", "Other / unknown"])
        apgar = c8.text_input("Apgar scores", placeholder="e.g., 1 min / 5 min / 10 min")
        reason = st.text_area("Reason for NICU admission *", placeholder="Document the stated clinical reason; do not enter real patient identifiers.")
        maternal_history = st.text_area("Maternal and perinatal history", placeholder="Relevant pregnancy, maternal, delivery and resuscitation history")
        initial_condition = st.text_area("Condition on arrival", placeholder="Appearance, activity, perfusion, temperature and other initial findings")
        respiratory_support = st.text_input("Respiratory support", placeholder="Room air / oxygen / CPAP / ventilation, as documented")
        lines_devices = st.text_area("Lines, tubes and devices", placeholder="Device type, site, status and checks")
        initial_assessment = st.text_area("Initial assessment / key findings")
        priorities = st.text_area("Initial nursing priorities and care plan")
        save_admission = st.form_submit_button("Save admission record")
    if save_admission:
        if not reason.strip() or not admission_time.strip():
            st.error("Admission reason and admission time are required.")
        elif birth_weight <= 0 or current_weight <= 0:
            st.error("Enter positive birth and current weights, or revise the form for a documented unknown value.")
        else:
            with connect() as conn:
                conn.execute("""INSERT INTO nicu_admissions
                    (patient_id, admission_date, admission_time, gestational_age, birth_weight_g, current_weight_g,
                     sex, delivery_mode, apgar, admission_reason, maternal_perinatal_history, initial_condition,
                     respiratory_support, lines_devices, initial_assessment, nursing_priorities, created_utc)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (pid, admission_date.isoformat(), admission_time.strip(), gestation.strip(), float(birth_weight),
                     float(current_weight), sex, delivery_mode, apgar.strip(), reason.strip(), maternal_history.strip(),
                     initial_condition.strip(), respiratory_support.strip(), lines_devices.strip(), initial_assessment.strip(),
                     priorities.strip(), timestamp_utc()))
            st.success("Admission record saved for the selected demo patient.")
    with connect() as conn:
        rows = conn.execute("SELECT id, admission_date, admission_time, gestational_age, admission_reason FROM nicu_admissions WHERE patient_id=? ORDER BY id DESC LIMIT 20", (pid,)).fetchall()
    st.markdown("**Recent admission records**")
    st.dataframe(pd.DataFrame(rows, columns=["ID", "Date", "Time", "Gestational age", "Admission reason"]), use_container_width=True, hide_index=True) if rows else st.info("No admission records saved yet.")

with medication_tab:
    st.markdown("#### Medication administration record (MAR)")
    st.warning("Record the verified prescription exactly as ordered. This tool does not calculate or recommend neonatal doses.")
    with st.form("medication_record_form"):
        c1, c2, c3 = st.columns(3)
        med_date = c1.date_input("Record date", value=day, key="med_date")
        medication = c2.text_input("Medication name *")
        prescribed_dose = c3.text_input("Prescribed dose as written *", placeholder="Include units and frequency from verified order")
        c4, c5, c6 = st.columns(3)
        route = c4.selectbox("Route *", ["Select route", "Oral / enteral", "IV", "IM", "SC", "Inhaled", "Topical", "Other"])
        scheduled_time = c5.text_input("Scheduled time", placeholder="HH:MM")
        status = c6.selectbox("Administration status", ["Administered", "Withheld", "Omitted", "Delayed", "Not given - other"])
        c7, c8, c9 = st.columns(3)
        administration_time = c7.text_input("Actual administration time", placeholder="HH:MM; leave blank if not given")
        weight_used = c8.number_input("Weight referenced by prescription (g)", min_value=0, max_value=10000, value=int(patient["weight_g"]), step=10)
        nurse_name = c9.text_input("Administering / documenting nurse")
        allergy_check = st.checkbox("Allergy status checked against available record")
        double_check = st.checkbox("Independent double-check documented where required by policy")
        indication = st.text_input("Indication / reason")
        omission_reason = st.text_input("Reason withheld, omitted or delayed (if applicable)")
        med_notes = st.text_area("Additional notes / response / follow-up")
        save_med = st.form_submit_button("Save medication record")
    if save_med:
        if not medication.strip() or not prescribed_dose.strip() or route == "Select route":
            st.error("Medication name, prescribed dose and route are required.")
        elif status == "Administered" and not administration_time.strip():
            st.error("Enter the actual administration time for a record marked administered.")
        elif status != "Administered" and not omission_reason.strip():
            st.error("Document the reason for a withheld, omitted, delayed or not-given dose.")
        else:
            with connect() as conn:
                conn.execute("""INSERT INTO medication_administration
                    (patient_id, record_date, medication, prescribed_dose, route, scheduled_time, status,
                     administration_time, weight_g, allergy_check, independent_double_check, nurse_name,
                     reason_or_indication, omission_reason, notes, created_utc)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (pid, med_date.isoformat(), medication.strip(), prescribed_dose.strip(), route, scheduled_time.strip(),
                     status, administration_time.strip(), float(weight_used) if weight_used > 0 else None,
                     int(allergy_check), int(double_check), nurse_name.strip(), indication.strip(), omission_reason.strip(),
                     med_notes.strip(), timestamp_utc()))
            st.success("Medication record saved. Verify it against the medication chart and local policy.")
    with connect() as conn:
        rows = conn.execute("SELECT id, record_date, medication, prescribed_dose, route, status, scheduled_time, administration_time, nurse_name FROM medication_administration WHERE patient_id=? ORDER BY id DESC LIMIT 50", (pid,)).fetchall()
    st.markdown("**Recent medication records**")
    st.dataframe(pd.DataFrame(rows, columns=["ID", "Date", "Medication", "Dose as prescribed", "Route", "Status", "Scheduled", "Actual time", "Nurse"]), use_container_width=True, hide_index=True) if rows else st.info("No medication records saved yet.")

with assessment_tab:
    st.markdown("#### Structured head-to-toe assessment")
    with st.form("head_to_toe_form"):
        c1, c2, c3 = st.columns(3)
        assess_date = c1.date_input("Assessment date", value=day, key="assess_date")
        assess_time = c2.text_input("Assessment time (HH:MM)", value="08:00", key="assess_time")
        assess_nurse = c3.text_input("Nurse completing assessment")
        neuro = st.text_area("Neurological", placeholder="State, activity, tone, responsiveness, fontanelle if assessed")
        respiratory = st.text_area("Respiratory", placeholder="Work of breathing, air entry, support and relevant observations")
        cardiovascular = st.text_area("Cardiovascular / perfusion", placeholder="Heart rate, pulses, colour, capillary refill, perfusion")
        temperature_skin = st.text_area("Temperature / skin", placeholder="Temperature, skin integrity, jaundice, pressure injury risk")
        gi_feeding = st.text_area("Gastrointestinal / feeding", placeholder="Abdomen, feeding plan/tolerance, emesis, stool")
        genitourinary = st.text_area("Genitourinary / elimination", placeholder="Urine output and relevant findings")
        musculoskeletal = st.text_area("Musculoskeletal / developmental care", placeholder="Movement, positioning, comfort and developmental support")
        lines_tubes = st.text_area("Lines, tubes and devices", placeholder="Site, patency, securement and device checks")
        c4, c5 = st.columns(2)
        pain_score = c4.text_input("Pain assessment tool and score", placeholder="Name the tool used and record score")
        infection_risk = c5.text_input("Infection risks / precautions")
        findings_interventions = st.text_area("Summary of findings and nursing interventions")
        escalation = st.text_area("Escalation, notification and follow-up required")
        save_assessment = st.form_submit_button("Save head-to-toe assessment")
    if save_assessment:
        if not assess_time.strip():
            st.error("Assessment time is required.")
        elif not any([neuro.strip(), respiratory.strip(), cardiovascular.strip(), temperature_skin.strip(), gi_feeding.strip(), genitourinary.strip(), musculoskeletal.strip(), lines_tubes.strip()]):
            st.error("Complete at least one assessment system before saving.")
        else:
            with connect() as conn:
                conn.execute("""INSERT INTO head_to_toe_assessments
                    (patient_id, assessment_date, assessment_time, neuro, respiratory, cardiovascular, temperature_skin,
                     gi_feeding, genitourinary, musculoskeletal, lines_tubes, pain_score, infection_risk,
                     findings_interventions, escalation, nurse_name, created_utc)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (pid, assess_date.isoformat(), assess_time.strip(), neuro.strip(), respiratory.strip(), cardiovascular.strip(),
                     temperature_skin.strip(), gi_feeding.strip(), genitourinary.strip(), musculoskeletal.strip(), lines_tubes.strip(),
                     pain_score.strip(), infection_risk.strip(), findings_interventions.strip(), escalation.strip(), assess_nurse.strip(), timestamp_utc()))
            st.success("Head-to-toe assessment saved.")
    with connect() as conn:
        rows = conn.execute("SELECT id, assessment_date, assessment_time, nurse_name, neuro, respiratory, cardiovascular, findings_interventions FROM head_to_toe_assessments WHERE patient_id=? ORDER BY id DESC LIMIT 20", (pid,)).fetchall()
    st.markdown("**Recent assessments**")
    st.dataframe(pd.DataFrame(rows, columns=["ID", "Date", "Time", "Nurse", "Neurological", "Respiratory", "Cardiovascular", "Summary / interventions"]), use_container_width=True, hide_index=True) if rows else st.info("No assessments saved yet.")

with patient_handover_tab:
    st.markdown("#### Structured patient shift handover (SBAR)")
    with st.form("patient_handover_form"):
        c1, c2, c3, c4 = st.columns(4)
        handover_date = c1.date_input("Handover date", value=day, key="patient_handover_date")
        handover_time = c2.text_input("Handover time (HH:MM)", value="07:00", key="patient_handover_time")
        outgoing = c3.text_input("Outgoing nurse")
        incoming = c4.text_input("Incoming nurse")
        situation = st.text_area("S · Situation *", placeholder="Current condition and immediate concerns")
        background = st.text_area("B · Background", placeholder="Relevant history, diagnosis and events during shift")
        assessment = st.text_area("A · Assessment", placeholder="Current observations, respiratory support, feeding, fluids, access/devices")
        recommendation = st.text_area("R · Recommendation / plan", placeholder="Priorities, monitoring, escalation thresholds from local protocol")
        pending_tasks = st.text_area("Pending tasks / investigations")
        escalation_plan = st.text_area("Escalation plan / clinician notified")
        acknowledgement = st.text_input("Read-back / acknowledgement notes")
        save_handover = st.form_submit_button("Save patient handover")
    if save_handover:
        if not situation.strip() or not handover_time.strip():
            st.error("Situation and handover time are required.")
        else:
            with connect() as conn:
                conn.execute("""INSERT INTO patient_handovers
                    (patient_id, handover_date, handover_time, outgoing_nurse, incoming_nurse, situation, background,
                     assessment, recommendation, pending_tasks, escalation_plan, acknowledgement, created_utc)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (pid, handover_date.isoformat(), handover_time.strip(), outgoing.strip(), incoming.strip(), situation.strip(),
                     background.strip(), assessment.strip(), recommendation.strip(), pending_tasks.strip(), escalation_plan.strip(),
                     acknowledgement.strip(), timestamp_utc()))
            st.success("Patient handover saved.")
    with connect() as conn:
        rows = conn.execute("SELECT id, handover_date, handover_time, outgoing_nurse, incoming_nurse, situation, recommendation, pending_tasks FROM patient_handovers WHERE patient_id=? ORDER BY id DESC LIMIT 20", (pid,)).fetchall()
    st.markdown("**Recent patient handovers**")
    st.dataframe(pd.DataFrame(rows, columns=["ID", "Date", "Time", "Outgoing nurse", "Incoming nurse", "Situation", "Recommendation", "Pending tasks"]), use_container_width=True, hide_index=True) if rows else st.info("No patient handovers saved yet.")

with equipment_tab:
    st.markdown("#### Equipment condition and handover checklist")
    with st.form("equipment_handover_form"):
        c1, c2, c3 = st.columns(3)
        equipment_date = c1.date_input("Handover date", value=day, key="equipment_date")
        equipment_time = c2.text_input("Handover time (HH:MM)", value="07:00", key="equipment_time")
        equipment_type = c3.selectbox("Equipment *", ["Incubator / radiant warmer", "Patient monitor", "CPAP system", "Ventilator", "Oxygen delivery", "Suction", "Infusion pump", "Syringe pump", "Phototherapy unit", "Other"])
        c4, c5, c6 = st.columns(3)
        equipment_id = c4.text_input("Asset / equipment ID")
        condition_status = c5.selectbox("Overall status", ["Checked - no issue noted", "Issue identified", "Out of service", "Not checked"])
        outgoing_staff = c6.text_input("Outgoing staff")
        incoming_staff = st.text_input("Incoming staff")
        function_check = st.selectbox("Function check", ["Not documented", "Passed per local checklist", "Failed / issue found", "Not applicable"])
        alarm_check = st.selectbox("Alarm check", ["Not documented", "Checked per local checklist", "Issue found", "Not applicable"])
        power_gas_check = st.selectbox("Power / gas / connections", ["Not documented", "Checked per local checklist", "Issue found", "Not applicable"])
        consumables_check = st.selectbox("Consumables / accessories", ["Not documented", "Available and checked", "Missing / needs replacement", "Not applicable"])
        fault_or_issue = st.text_area("Faults, damage or outstanding issues")
        action_taken = st.text_area("Action taken / person notified / equipment isolated if needed")
        equipment_notes = st.text_area("Additional handover notes")
        save_equipment = st.form_submit_button("Save equipment handover")
    if save_equipment:
        if not equipment_time.strip():
            st.error("Equipment handover time is required.")
        elif condition_status in ["Issue identified", "Out of service"] and not fault_or_issue.strip():
            st.error("Describe the issue or reason for taking the equipment out of service.")
        else:
            with connect() as conn:
                conn.execute("""INSERT INTO equipment_handovers
                    (patient_id, handover_date, handover_time, equipment_type, equipment_id, condition_status,
                     function_check, alarm_check, power_gas_check, consumables_check, fault_or_issue, action_taken,
                     outgoing_staff, incoming_staff, notes, created_utc)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (pid, equipment_date.isoformat(), equipment_time.strip(), equipment_type, equipment_id.strip(), condition_status,
                     function_check, alarm_check, power_gas_check, consumables_check, fault_or_issue.strip(), action_taken.strip(),
                     outgoing_staff.strip(), incoming_staff.strip(), equipment_notes.strip(), timestamp_utc()))
            st.success("Equipment handover saved. Follow local biomedical/equipment safety procedures for faults.")
    with connect() as conn:
        rows = conn.execute("SELECT id, handover_date, handover_time, equipment_type, equipment_id, condition_status, function_check, alarm_check, fault_or_issue FROM equipment_handovers WHERE patient_id=? ORDER BY id DESC LIMIT 30", (pid,)).fetchall()
    st.markdown("**Recent equipment handovers**")
    st.dataframe(pd.DataFrame(rows, columns=["ID", "Date", "Time", "Equipment", "Asset ID", "Status", "Function check", "Alarm check", "Fault / issue"]), use_container_width=True, hide_index=True) if rows else st.info("No equipment handovers saved yet.")


with st.expander("Dates with saved records"):
    with connect() as conn:
        saved_dates = conn.execute(
            """
            SELECT monitor_date FROM daily_observations WHERE patient_id = ?
            UNION SELECT monitor_date FROM daily_fluids WHERE patient_id = ?
            UNION SELECT admission_date FROM nicu_admissions WHERE patient_id = ?
            UNION SELECT record_date FROM medication_administration WHERE patient_id = ?
            UNION SELECT assessment_date FROM head_to_toe_assessments WHERE patient_id = ?
            UNION SELECT handover_date FROM patient_handovers WHERE patient_id = ?
            UNION SELECT handover_date FROM equipment_handovers WHERE patient_id = ?
            ORDER BY 1 DESC
            """,
            (pid, pid, pid, pid, pid, pid, pid),
        ).fetchall()
    st.write(", ".join(row[0] for row in saved_dates) if saved_dates else "No saved dates yet.")

with st.expander("About this educational prototype"):
    st.markdown(
        """
        - Select a fictional patient and monitoring date.
        - Vital-sign and fluid records are filtered by patient and date.
        - Additional modules record admission, medication administration, head-to-toe assessments,
          patient SBAR handovers, and equipment checks.
        - Medication doses are entered as prescribed; the app does not calculate or recommend doses.
        - Fluid calculations are arithmetic summaries, not treatment guidance.
        - The database is local SQLite storage and may be reset by the hosting platform.
        - This public demo has no login or access controls. Never enter real patient data.
        - This app is not validated for clinical use and does not replace bedside monitoring,
          clinical assessment, or approved neonatal protocols.
        """
    )

st.caption(f"Today Nurse · Educational prototype · Version {APP_VERSION} · Not for clinical use")
