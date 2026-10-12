"""Today Nurse NICU Documentation System.

Blank, linked documentation forms. This is a prototype, not a validated EHR.
Do not deploy for identifiable patient data without appropriate security controls.
"""

import math
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, time, timezone
from pathlib import Path

import pandas as pd
import streamlit as st

APP_VERSION = "1.1"
DB_PATH = Path(__file__).with_name("today_nurse_nicu.db")

st.set_page_config(
    page_title="Today Nurse | NICU Documentation",
    page_icon="🩺",
    layout="wide",
)


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def db():
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS patients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            hospital_patient_id TEXT NOT NULL UNIQUE,
            patient_label TEXT NOT NULL,
            date_of_birth TEXT,
            sex TEXT,
            created_utc TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS admissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER NOT NULL REFERENCES patients(id),
            admission_date TEXT NOT NULL,
            admission_time TEXT NOT NULL,
            gestational_age_weeks REAL,
            gestational_age_days INTEGER,
            birth_weight_g REAL,
            admission_weight_g REAL,
            delivery_mode TEXT,
            apgar_1 TEXT,
            apgar_5 TEXT,
            referring_facility TEXT,
            admission_reason TEXT NOT NULL,
            maternal_perinatal_history TEXT,
            resuscitation TEXT,
            initial_condition TEXT,
            respiratory_support TEXT,
            oxygen_or_support_settings TEXT,
            lines_devices TEXT,
            allergies TEXT,
            infection_risk TEXT,
            initial_nursing_assessment TEXT,
            nursing_priorities TEXT,
            admitting_clinician TEXT,
            admitting_nurse TEXT,
            status TEXT NOT NULL DEFAULT 'Active',
            created_utc TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS observations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admission_id INTEGER NOT NULL REFERENCES admissions(id),
            observation_date TEXT NOT NULL,
            observation_time TEXT NOT NULL,
            heart_rate REAL,
            respiratory_rate REAL,
            temperature_c REAL,
            spo2_percent REAL,
            fio2_percent REAL,
            blood_pressure TEXT,
            pain_score TEXT,
            respiratory_support TEXT,
            support_settings TEXT,
            capillary_refill TEXT,
            nurse_name TEXT NOT NULL,
            note TEXT,
            created_utc TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS fluid_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admission_id INTEGER NOT NULL REFERENCES admissions(id),
            record_date TEXT NOT NULL,
            interval_start TEXT NOT NULL,
            interval_end TEXT NOT NULL,
            weight_g REAL,
            iv_ml REAL DEFAULT 0,
            feeds_ml REAL DEFAULT 0,
            medication_ml REAL DEFAULT 0,
            blood_products_ml REAL DEFAULT 0,
            other_intake_ml REAL DEFAULT 0,
            urine_ml REAL DEFAULT 0,
            stool_count INTEGER DEFAULT 0,
            emesis_ml REAL DEFAULT 0,
            drains_ml REAL DEFAULT 0,
            other_output_ml REAL DEFAULT 0,
            total_intake_ml REAL NOT NULL,
            total_output_ml REAL NOT NULL,
            net_balance_ml REAL NOT NULL,
            urine_output_ml_kg_hr REAL,
            nurse_name TEXT NOT NULL,
            notes TEXT,
            created_utc TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS medication_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admission_id INTEGER NOT NULL REFERENCES admissions(id),
            record_date TEXT NOT NULL,
            medication_name TEXT NOT NULL,
            prescribed_dose TEXT NOT NULL,
            route TEXT NOT NULL,
            frequency TEXT,
            scheduled_time TEXT,
            status TEXT NOT NULL,
            actual_administration_time TEXT,
            weight_used_g REAL,
            allergy_check TEXT NOT NULL,
            double_check TEXT,
            nurse_name TEXT NOT NULL,
            indication TEXT,
            withheld_or_omitted_reason TEXT,
            response_or_notes TEXT,
            created_utc TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS assessments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admission_id INTEGER NOT NULL REFERENCES admissions(id),
            assessment_date TEXT NOT NULL,
            assessment_time TEXT NOT NULL,
            assessment_type TEXT NOT NULL,
            gestational_age_context TEXT,
            neurological TEXT,
            respiratory TEXT,
            cardiovascular TEXT,
            thermoregulation_skin TEXT,
            gastrointestinal_feeding TEXT,
            genitourinary TEXT,
            musculoskeletal TEXT,
            pain_comfort TEXT,
            lines_tubes_devices TEXT,
            infection_risk TEXT,
            developmental_family_care TEXT,
            findings_interventions TEXT,
            escalation_actions TEXT,
            nurse_name TEXT NOT NULL,
            created_utc TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS equipment_checks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admission_id INTEGER NOT NULL REFERENCES admissions(id),
            check_date TEXT NOT NULL,
            check_time TEXT NOT NULL,
            equipment_type TEXT NOT NULL,
            equipment_identifier TEXT,
            assigned_patient_confirmed TEXT NOT NULL,
            physical_condition TEXT NOT NULL,
            function_check TEXT NOT NULL,
            alarm_check TEXT,
            power_gas_check TEXT,
            consumables_check TEXT,
            cleaning_status TEXT,
            fault_or_issue TEXT,
            action_taken TEXT,
            escalation_or_ticket TEXT,
            outgoing_staff TEXT,
            incoming_staff TEXT,
            nurse_name TEXT NOT NULL,
            notes TEXT,
            created_utc TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS handovers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admission_id INTEGER NOT NULL REFERENCES admissions(id),
            handover_date TEXT NOT NULL,
            handover_time TEXT NOT NULL,
            shift TEXT NOT NULL,
            outgoing_nurse TEXT NOT NULL,
            incoming_nurse TEXT NOT NULL,
            situation TEXT NOT NULL,
            background TEXT,
            assessment_summary TEXT,
            recommendations TEXT,
            airway_respiratory TEXT,
            fluids_feeding_elimination TEXT,
            medication_due_or_pending TEXT,
            lines_devices_equipment TEXT,
            investigations_pending TEXT,
            safety_concerns TEXT,
            escalation_plan TEXT,
            acknowledgement TEXT,
            created_utc TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS progress_notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admission_id INTEGER NOT NULL REFERENCES admissions(id),
            note_date TEXT NOT NULL,
            note_time TEXT NOT NULL,
            note_type TEXT NOT NULL,
            assessment TEXT,
            nursing_intervention TEXT,
            response_evaluation TEXT,
            communication_escalation TEXT,
            nurse_name TEXT NOT NULL,
            created_utc TEXT NOT NULL
        );
        """)


init_db()

st.title("🩺 Today Nurse | NICU Nursing Documentation")
st.caption(f"Version {APP_VERSION} · Blank clinical forms linked to patient admissions")
st.warning(
    "SECURITY NOTICE: This prototype does not provide user authentication, role-based access, "
    "audit-grade record locking, or encrypted clinical storage. Do not enter identifiable patient "
    "information until it has been deployed in an approved, secured environment. Validate all forms "
    "and workflows against your hospital's policies before clinical use."
)


def fetchall(sql, params=()):
    with db() as conn:
        return conn.execute(sql, params).fetchall()


def save(sql, params):
    with db() as conn:
        cur = conn.execute(sql, params)
        return cur.lastrowid


def options_for_admissions():
    rows = fetchall("""SELECT a.id, p.hospital_patient_id, p.patient_label,
                     a.admission_date, a.admission_reason, a.status
                     FROM admissions a JOIN patients p ON p.id=a.patient_id
                     WHERE a.status='Active' ORDER BY a.admission_date DESC, a.id DESC""")
    labels = {
        f"{r['hospital_patient_id']} | {r['patient_label']} | admission #{r['id']} | {r['admission_date']}": r['id']
        for r in rows
    }
    return labels


def validate_optional_range(label, value, minimum, maximum):
    if value is not None and not minimum <= float(value) <= maximum:
        raise ValueError(f"{label} must be between {minimum} and {maximum}.")


with st.sidebar:
    st.header("Patient / admission")
    active_admissions = options_for_admissions()
    if active_admissions:
        selected_label = st.selectbox("Active admission", list(active_admissions))
        admission_id = active_admissions[selected_label]
        st.caption("All forms below are linked to this admission episode.")
    else:
        admission_id = None
        st.info("No active admission yet. Register a patient and create an admission first.")
    view_date = st.date_input("Record date", value=date.today(), key="global_record_date")

# Main workflow tabs
sections = st.tabs([
    "1 · Patient registry", "2 · Initial admission", "3 · Head-to-toe assessment",
    "4 · Vital signs", "5 · Fluid balance", "6 · Medication record",
    "7 · Equipment checks", "8 · Shift handover", "9 · Progress notes & history"
])

# 1. Patient registry
with sections[0]:
    st.subheader("Patient registry")
    st.caption("Enter the identifiers required by your organization's approved workflow. Do not use public or unsecured deployment for real identifiers.")
    with st.form("patient_registration", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            hospital_patient_id = st.text_input("Hospital patient / medical record number *")
            patient_label = st.text_input("Patient name or approved patient label *")
            dob = st.date_input("Date of birth", value=None, min_value=date(1990, 1, 1), max_value=date.today())
        with c2:
            sex = st.selectbox("Sex", ["Not recorded", "Female", "Male", "Indeterminate / not yet assigned", "Other / per local policy"])
        create_patient = st.form_submit_button("Register patient")
    if create_patient:
        if not hospital_patient_id.strip() or not patient_label.strip():
            st.error("Hospital patient ID and patient label are required.")
        else:
            try:
                new_id = save("INSERT INTO patients(hospital_patient_id, patient_label, date_of_birth, sex, created_utc) VALUES(?,?,?,?,?)",
                              (hospital_patient_id.strip(), patient_label.strip(), dob.isoformat() if dob else None,
                               None if sex == "Not recorded" else sex, utc_now()))
                st.success(f"Patient registered (internal record #{new_id}). Create an admission in the next tab.")
                st.rerun()
            except sqlite3.IntegrityError:
                st.error("That hospital patient ID already exists. Select the existing patient rather than registering a duplicate.")
    patients = fetchall("SELECT id, hospital_patient_id, patient_label, date_of_birth, sex FROM patients ORDER BY patient_label")
    if patients:
        st.markdown("#### Registered patients")
        st.dataframe(pd.DataFrame([dict(r) for r in patients]), use_container_width=True, hide_index=True)

# 2. Initial admission
with sections[1]:
    st.subheader("Initial NICU admission form")
    patients = fetchall("SELECT id, hospital_patient_id, patient_label FROM patients ORDER BY patient_label")
    if not patients:
        st.info("Register a patient in tab 1 before completing an admission.")
    else:
        patient_map = {f"{r['hospital_patient_id']} | {r['patient_label']}": r['id'] for r in patients}
        with st.form("admission_form", clear_on_submit=True):
            patient_key = st.selectbox("Patient *", list(patient_map))
            c1, c2, c3 = st.columns(3)
            with c1:
                adm_date = st.date_input("Admission date *", value=date.today(), key="adm_date")
                adm_time = st.time_input("Admission time *", value=datetime.now().time().replace(second=0, microsecond=0), key="adm_time")
                ga_weeks = st.number_input("Gestational age (completed weeks)", min_value=0, max_value=45, value=0, help="Use 0 if not documented; confirm the correct gestational age convention locally.")
                ga_days = st.number_input("Additional gestational days", min_value=0, max_value=6, value=0)
            with c2:
                birth_weight = st.number_input("Birth weight (g)", min_value=0.0, max_value=10000.0, value=0.0, step=10.0)
                admission_weight = st.number_input("Admission weight (g)", min_value=0.0, max_value=10000.0, value=0.0, step=10.0)
                delivery_mode = st.selectbox("Mode of delivery", ["Not documented", "Spontaneous vaginal", "Assisted vaginal", "Caesarean section", "Other / unknown"])
                apgar1 = st.text_input("Apgar at 1 minute", max_chars=20)
                apgar5 = st.text_input("Apgar at 5 minutes", max_chars=20)
            with c3:
                referring = st.text_input("Referring facility / location")
                admission_reason = st.text_area("Reason for NICU admission *", height=90)
                resuscitation = st.text_area("Delivery-room resuscitation / stabilization", height=70)
                initial_condition = st.text_area("Condition on arrival", height=90)
            maternal_history = st.text_area("Maternal and perinatal history", placeholder="Relevant antenatal history, maternal conditions, infection risk, membranes, medications, etc.")
            c4, c5 = st.columns(2)
            with c4:
                respiratory_support = st.selectbox("Respiratory support on admission", ["Not documented", "Room air", "Low-flow oxygen", "High-flow nasal cannula", "CPAP", "NIPPV", "Mechanical ventilation", "Other"])
                support_settings = st.text_area("Oxygen / respiratory support settings", height=70)
                lines_devices = st.text_area("Lines, tubes and devices on admission", height=70)
            with c5:
                allergies = st.text_area("Known allergies / status", height=70)
                infection_risk = st.text_area("Infection risk / precautions", height=70)
                initial_assessment = st.text_area("Initial nursing assessment", height=90)
            priorities = st.text_area("Initial nursing priorities / plan", height=90)
            c6, c7 = st.columns(2)
            with c6:
                admitting_clinician = st.text_input("Admitting clinician")
            with c7:
                admitting_nurse = st.text_input("Admitting nurse name / staff ID *")
            save_admission = st.form_submit_button("Save initial admission")
        if save_admission:
            if not admission_reason.strip() or not admitting_nurse.strip():
                st.error("Admission reason and admitting nurse are required.")
            else:
                try:
                    new_adm = save("""INSERT INTO admissions(patient_id, admission_date, admission_time, gestational_age_weeks, gestational_age_days,
                        birth_weight_g, admission_weight_g, delivery_mode, apgar_1, apgar_5, referring_facility, admission_reason,
                        maternal_perinatal_history, resuscitation, initial_condition, respiratory_support, oxygen_or_support_settings,
                        lines_devices, allergies, infection_risk, initial_nursing_assessment, nursing_priorities, admitting_clinician,
                        admitting_nurse, created_utc) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (patient_map[patient_key], adm_date.isoformat(), adm_time.strftime("%H:%M"), ga_weeks or None, ga_days,
                         birth_weight or None, admission_weight or None, delivery_mode, apgar1.strip() or None, apgar5.strip() or None,
                         referring.strip() or None, admission_reason.strip(), maternal_history.strip() or None, resuscitation.strip() or None,
                         initial_condition.strip() or None, respiratory_support, support_settings.strip() or None, lines_devices.strip() or None,
                         allergies.strip() or None, infection_risk.strip() or None, initial_assessment.strip() or None, priorities.strip() or None,
                         admitting_clinician.strip() or None, admitting_nurse.strip(), utc_now()))
                    st.success(f"Admission saved as episode #{new_adm}. It is now available in the sidebar selector.")
                    st.rerun()
                except sqlite3.Error as exc:
                    st.error(f"Could not save admission: {exc}")

# Shared guard for all linked clinical forms
if admission_id is None:
    for i in range(2, 9):
        with sections[i]:
            st.info("Register a patient and create an active admission before documenting care here.")
else:
    # Show context for selected admission
    context = fetchall("""SELECT a.*, p.hospital_patient_id, p.patient_label, p.date_of_birth, p.sex
                         FROM admissions a JOIN patients p ON p.id=a.patient_id WHERE a.id=?""", (admission_id,))
    selected_admission = context[0]
    st.sidebar.markdown("---")
    st.sidebar.markdown(f"**Selected patient:** {selected_admission['patient_label']}")
    st.sidebar.caption(f"MRN: {selected_admission['hospital_patient_id']} · Episode #{admission_id}")

    # 3. Head-to-toe assessment
    with sections[2]:
        st.subheader("Head-to-toe NICU nursing assessment")
        with st.form("assessment_form", clear_on_submit=True):
            c1, c2, c3 = st.columns(3)
            with c1:
                assess_date = st.date_input("Assessment date", value=view_date, key="assess_date")
                assess_time = st.time_input("Assessment time", value=datetime.now().time().replace(second=0, microsecond=0), key="assess_time")
                assess_type = st.selectbox("Assessment type", ["Initial baseline", "Routine shift assessment", "Focused reassessment", "Post-intervention", "Other"])
                neuro = st.text_area("Neurological: state, tone, activity, reflexes", height=100)
                respiratory = st.text_area("Respiratory: effort, air entry, support, secretions", height=100)
            with c2:
                cardiovascular = st.text_area("Cardiovascular: HR, perfusion, pulses, capillary refill", height=100)
                skin = st.text_area("Thermoregulation and skin: temperature, colour, integrity", height=100)
                gi = st.text_area("GI / feeding: abdomen, feeds, tolerance, emesis, stool", height=100)
                gu = st.text_area("Genitourinary: urine, output, genital assessment as indicated", height=100)
            with c3:
                musculoskeletal = st.text_area("Musculoskeletal: movement, posture, symmetry", height=100)
                pain = st.text_input("Pain / comfort tool and score")
                lines = st.text_area("Lines, tubes and devices: site, security, condition", height=100)
                infection = st.text_area("Infection risks, precautions and relevant findings", height=100)
                developmental = st.text_area("Developmental care and family involvement", height=100)
            findings = st.text_area("Findings, nursing interventions and evaluation", height=110)
            escalation = st.text_area("Escalation / clinician notified / time / response", height=80)
            nurse = st.text_input("Assessing nurse name / staff ID", key="assess_nurse")
            save_assess = st.form_submit_button("Save assessment")
        if save_assess:
            if not nurse.strip():
                st.error("Nurse name or staff ID is required.")
            else:
                save("""INSERT INTO assessments(admission_id, assessment_date, assessment_time, assessment_type, neurological, respiratory,
                    cardiovascular, thermoregulation_skin, gastrointestinal_feeding, genitourinary, musculoskeletal, pain_comfort,
                    lines_tubes_devices, infection_risk, developmental_family_care, findings_interventions, escalation_actions, nurse_name, created_utc)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (admission_id, assess_date.isoformat(), assess_time.strftime("%H:%M"), assess_type, neuro, respiratory, cardiovascular,
                     skin, gi, gu, musculoskeletal, pain, lines, infection, developmental, findings, escalation, nurse.strip(), utc_now()))
                st.success("Assessment saved.")

    # 4. Vital signs
    with sections[3]:
        st.subheader("Vital signs and monitoring chart")
        with st.form("observation_form", clear_on_submit=True):
            c1, c2, c3 = st.columns(3)
            with c1:
                obs_date = st.date_input("Observation date", value=view_date, key="obs_date")
                obs_time = st.time_input("Observation time", value=datetime.now().time().replace(second=0, microsecond=0), key="obs_time")
                hr = st.number_input("Heart rate (bpm)", min_value=0.0, max_value=350.0, value=None, step=1.0, placeholder="Enter measured value")
                rr = st.number_input("Respiratory rate (/min)", min_value=0.0, max_value=200.0, value=None, step=1.0, placeholder="Enter measured value")
            with c2:
                temp = st.number_input("Temperature (°C)", min_value=20.0, max_value=45.0, value=None, step=0.1, placeholder="Enter measured value")
                spo2 = st.number_input("SpO₂ (%)", min_value=0.0, max_value=100.0, value=None, step=1.0, placeholder="Enter measured value")
                fio2 = st.number_input("FiO₂ (%)", min_value=21.0, max_value=100.0, value=None, step=1.0, placeholder="If applicable")
                bp = st.text_input("Blood pressure (document units/site)")
            with c3:
                pain_score = st.text_input("Pain tool and score")
                support = st.selectbox("Respiratory support", ["Not documented", "Room air", "Oxygen", "HFNC", "CPAP", "NIPPV", "Mechanical ventilation", "Other"])
                support_settings = st.text_input("Support settings / interface")
                refill = st.selectbox("Capillary refill", ["Not assessed", "Document findings", "Documented as within local expected range", "Delayed / abnormal finding"])
            nurse = st.text_input("Recording nurse name / staff ID", key="obs_nurse")
            note = st.text_area("Clinical observation / action / escalation", max_chars=2000)
            save_obs = st.form_submit_button("Save observation")
        if save_obs:
            if not nurse.strip():
                st.error("Nurse name or staff ID is required.")
            elif all(v is None for v in [hr, rr, temp, spo2, fio2]) and not note.strip():
                st.error("Enter at least one measured observation or a clinical note.")
            else:
                try:
                    for label, value, lo, hi in [("Heart rate", hr, 0, 350), ("Respiratory rate", rr, 0, 200), ("Temperature", temp, 20, 45), ("SpO₂", spo2, 0, 100), ("FiO₂", fio2, 21, 100)]:
                        if value is not None and (not math.isfinite(float(value)) or not lo <= float(value) <= hi):
                            raise ValueError(f"{label} value is invalid.")
                    save("""INSERT INTO observations(admission_id, observation_date, observation_time, heart_rate, respiratory_rate, temperature_c,
                        spo2_percent, fio2_percent, blood_pressure, pain_score, respiratory_support, support_settings, capillary_refill,
                        nurse_name, note, created_utc) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (admission_id, obs_date.isoformat(), obs_time.strftime("%H:%M"), hr, rr, temp, spo2, fio2, bp.strip() or None,
                         pain_score.strip() or None, support, support_settings.strip() or None, refill, nurse.strip(), note.strip() or None, utc_now()))
                    st.success("Observation saved.")
                except (ValueError, sqlite3.Error) as exc:
                    st.error(f"Could not save observation: {exc}")

    # 5. Fluid balance
    with sections[4]:
        st.subheader("Fluid intake and output chart")
        st.caption("Enter actual measured volumes for a clearly defined, non-overlapping interval. The app does not infer missing values.")
        with st.form("fluid_form", clear_on_submit=True):
            c1, c2, c3 = st.columns(3)
            with c1:
                fluid_date = st.date_input("Record date", value=view_date, key="fluid_date")
                start_time = st.time_input("Interval start", value=time(0, 0), key="fluid_start")
                end_time = st.time_input("Interval end", value=time(1, 0), key="fluid_end")
                weight_g = st.number_input("Weight used for calculation (g)", min_value=0.0, max_value=10000.0, value=None, step=10.0, placeholder="Enter measured weight")
                iv = st.number_input("IV fluids (mL)", min_value=0.0, max_value=10000.0, value=None, step=0.5, placeholder="Measured volume")
                feeds = st.number_input("Enteral feeds (mL)", min_value=0.0, max_value=10000.0, value=None, step=0.5, placeholder="Measured volume")
            with c2:
                med_ml = st.number_input("Medication fluid volume (mL)", min_value=0.0, max_value=10000.0, value=None, step=0.5, placeholder="Measured volume")
                blood_ml = st.number_input("Blood products (mL)", min_value=0.0, max_value=10000.0, value=None, step=0.5, placeholder="Measured volume")
                other_in = st.number_input("Other intake (mL)", min_value=0.0, max_value=10000.0, value=None, step=0.5, placeholder="Measured volume")
            with c3:
                urine = st.number_input("Urine (mL)", min_value=0.0, max_value=10000.0, value=None, step=0.5, placeholder="Measured volume")
                stools = st.number_input("Stool count", min_value=0, max_value=100, value=None, step=1, placeholder="Count")
                emesis = st.number_input("Emesis (mL)", min_value=0.0, max_value=10000.0, value=None, step=0.5, placeholder="Measured volume")
                drains = st.number_input("Drain output (mL)", min_value=0.0, max_value=10000.0, value=None, step=0.5, placeholder="Measured volume")
                other_out = st.number_input("Other output (mL)", min_value=0.0, max_value=10000.0, value=None, step=0.5, placeholder="Measured volume")
            fluid_nurse = st.text_input("Recording nurse name / staff ID", key="fluid_nurse")
            fluid_notes = st.text_area("Notes / source of measurements")
            save_fluid = st.form_submit_button("Calculate and save interval")
        if save_fluid:
            try:
                if not fluid_nurse.strip():
                    raise ValueError("Nurse name or staff ID is required.")
                if weight_g is None or weight_g <= 0:
                    raise ValueError("Enter the measured weight used for the calculation.")
                volumes = [iv, feeds, med_ml, blood_ml, other_in, urine, emesis, drains, other_out]
                if any(v is None for v in volumes) or stools is None:
                    raise ValueError("Enter each intake/output field; use 0 only when confirmed to be zero.")
                start_dt = datetime.combine(fluid_date, start_time)
                end_dt = datetime.combine(fluid_date, end_time)
                if end_dt <= start_dt:
                    raise ValueError("Interval end must be later than interval start on the selected date. Split overnight intervals across dates.")
                duration_h = (end_dt - start_dt).total_seconds() / 3600
                intake = float(iv + feeds + med_ml + blood_ml + other_in)
                output = float(urine + emesis + drains + other_out)
                net = intake - output
                urine_rate = float(urine) / (float(weight_g) / 1000) / duration_h
                save("""INSERT INTO fluid_records(admission_id, record_date, interval_start, interval_end, weight_g, iv_ml, feeds_ml,
                    medication_ml, blood_products_ml, other_intake_ml, urine_ml, stool_count, emesis_ml, drains_ml, other_output_ml,
                    total_intake_ml, total_output_ml, net_balance_ml, urine_output_ml_kg_hr, nurse_name, notes, created_utc)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (admission_id, fluid_date.isoformat(), start_time.strftime("%H:%M"), end_time.strftime("%H:%M"), weight_g,
                     iv, feeds, med_ml, blood_ml, other_in, urine, stools, emesis, drains, other_out, intake, output, net,
                     urine_rate, fluid_nurse.strip(), fluid_notes.strip() or None, utc_now()))
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Total intake", f"{intake:.1f} mL")
                c2.metric("Total output", f"{output:.1f} mL")
                c3.metric("Net balance", f"{net:+.1f} mL")
                c4.metric("Urine output estimate", f"{urine_rate:.2f} mL/kg/hr")
                st.success("Fluid interval saved. Confirm calculation conventions with local policy.")
            except (ValueError, TypeError, sqlite3.Error) as exc:
                st.error(f"Could not save fluid record: {exc}")

    # 6. Medication administration record
    with sections[5]:
        st.subheader("Medication administration record (MAR)")
        st.warning("Document against a verified prescription and local neonatal medication policy. This form does not prescribe, calculate, or authorize doses.")
        with st.form("med_form", clear_on_submit=True):
            c1, c2 = st.columns(2)
            with c1:
                med_date = st.date_input("Record date", value=view_date, key="med_date")
                med_name = st.text_input("Medication name as prescribed *")
                prescribed_dose = st.text_input("Prescribed dose and units *")
                route = st.selectbox("Route *", ["Select route", "Oral / enteral", "IV", "IM", "SC", "Inhaled / nebulized", "Topical", "Other / per prescription"])
                frequency = st.text_input("Frequency / schedule")
                scheduled_time = st.text_input("Scheduled time (HH:MM or as prescribed)")
                med_status = st.selectbox("Administration status", ["Administered", "Withheld", "Omitted / not given", "Delayed", "Refused", "Not applicable / other"])
            with c2:
                actual_time = st.text_input("Actual administration time (HH:MM)")
                med_weight = st.number_input("Weight referenced by prescription (g, if applicable)", min_value=0.0, max_value=10000.0, value=None, step=10.0, placeholder="If applicable")
                allergy_check = st.selectbox("Allergy status checked", ["Select status", "Checked; none known documented", "Known allergy reviewed", "Unable to verify; escalated", "Not applicable per policy"])
                double_check = st.selectbox("Independent double-check", ["Not indicated by policy", "Completed and documented per policy", "Required but not completed; escalated", "Not applicable / local policy"])
                med_nurse = st.text_input("Administering nurse name / staff ID *")
                indication = st.text_input("Indication / relevant prescription reference")
            omit_reason = st.text_area("Reason if withheld, omitted, delayed or not given")
            response = st.text_area("Response, monitoring, adverse effects or other notes")
            save_med = st.form_submit_button("Save medication record")
        if save_med:
            if not med_name.strip() or not prescribed_dose.strip() or route == "Select route" or not med_nurse.strip():
                st.error("Medication, prescribed dose, route and nurse identification are required.")
            elif allergy_check == "Select status":
                st.error("Record the allergy-status check.")
            elif med_status != "Administered" and not omit_reason.strip():
                st.error("Document the reason when medication was not administered as scheduled.")
            else:
                save("""INSERT INTO medication_records(admission_id, record_date, medication_name, prescribed_dose, route, frequency,
                    scheduled_time, status, actual_administration_time, weight_used_g, allergy_check, double_check, nurse_name,
                    indication, withheld_or_omitted_reason, response_or_notes, created_utc) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (admission_id, med_date.isoformat(), med_name.strip(), prescribed_dose.strip(), route, frequency.strip() or None,
                     scheduled_time.strip() or None, med_status, actual_time.strip() or None, med_weight, allergy_check, double_check,
                     med_nurse.strip(), indication.strip() or None, omit_reason.strip() or None, response.strip() or None, utc_now()))
                st.success("Medication administration record saved.")

    # 7. Equipment safety check
    with sections[6]:
        st.subheader("Equipment check and handover")
        with st.form("equipment_form", clear_on_submit=True):
            c1, c2 = st.columns(2)
            with c1:
                eq_date = st.date_input("Check date", value=view_date, key="eq_date")
                eq_time = st.time_input("Check time", value=datetime.now().time().replace(second=0, microsecond=0), key="eq_time")
                eq_type = st.selectbox("Equipment type", ["Incubator", "Radiant warmer", "Patient monitor", "CPAP / NIPPV", "Ventilator", "Oxygen delivery", "Suction", "Infusion pump", "Syringe pump", "Phototherapy", "Other"])
                eq_id = st.text_input("Asset / equipment identifier")
                assigned = st.selectbox("Patient and equipment assignment verified", ["Select", "Yes", "No; escalated", "Not applicable"])
                condition = st.selectbox("Physical condition", ["Select", "No visible damage noted", "Damage / concern identified", "Not checked"])
                function_check = st.selectbox("Function check", ["Select", "Passed per local checklist", "Failed; removed from use / escalated", "Not completed"])
                alarm_check = st.selectbox("Alarm check", ["Not applicable", "Passed per local checklist", "Failed; escalated", "Not checked"])
            with c2:
                power_gas = st.selectbox("Power / gas / connection check", ["Not applicable", "Passed per local checklist", "Issue identified; escalated", "Not checked"])
                consumables = st.selectbox("Consumables / accessories", ["Not applicable", "Available and appropriate", "Restock needed", "Issue identified"])
                cleaning = st.selectbox("Cleaning / decontamination status", ["Not documented", "Completed per policy", "Required before use", "Concern / escalated"])
                fault = st.text_area("Fault or issue identified")
                action = st.text_area("Action taken")
                ticket = st.text_input("Maintenance ticket / escalation reference")
                outgoing = st.text_input("Outgoing staff")
                incoming = st.text_input("Incoming staff")
                eq_nurse = st.text_input("Person completing check name / staff ID *")
            eq_notes = st.text_area("Additional notes")
            save_eq = st.form_submit_button("Save equipment check")
        if save_eq:
            if assigned == "Select" or condition == "Select" or function_check == "Select" or not eq_nurse.strip():
                st.error("Complete patient assignment, physical condition, function check and staff identification.")
            elif (condition == "Damage / concern identified" or function_check.startswith("Failed") or alarm_check.startswith("Failed") or power_gas.startswith("Issue")) and not (fault.strip() or action.strip() or ticket.strip()):
                st.error("For an identified fault, document the issue and action or escalation reference.")
            else:
                save("""INSERT INTO equipment_checks(admission_id, check_date, check_time, equipment_type, equipment_identifier,
                    assigned_patient_confirmed, physical_condition, function_check, alarm_check, power_gas_check, consumables_check,
                    cleaning_status, fault_or_issue, action_taken, escalation_or_ticket, outgoing_staff, incoming_staff, nurse_name, notes, created_utc)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (admission_id, eq_date.isoformat(), eq_time.strftime("%H:%M"), eq_type, eq_id.strip() or None, assigned, condition,
                     function_check, alarm_check, power_gas, consumables, cleaning, fault.strip() or None, action.strip() or None,
                     ticket.strip() or None, outgoing.strip() or None, incoming.strip() or None, eq_nurse.strip(), eq_notes.strip() or None, utc_now()))
                st.success("Equipment check saved.")

    # 8. Shift handover
    with sections[7]:
        st.subheader("Nursing shift handover · SBAR")
        with st.form("handover_form", clear_on_submit=True):
            c1, c2, c3 = st.columns(3)
            with c1:
                hand_date = st.date_input("Handover date", value=view_date, key="hand_date")
                hand_time = st.time_input("Handover time", value=datetime.now().time().replace(second=0, microsecond=0), key="hand_time")
                shift = st.selectbox("Shift", ["Day", "Evening", "Night", "Other"])
                outgoing = st.text_input("Outgoing nurse *")
                incoming = st.text_input("Incoming nurse *")
            with c2:
                situation = st.text_area("S · Situation / current concern *", height=100)
                background = st.text_area("B · Background / diagnosis / relevant history", height=100)
                assessment_summary = st.text_area("A · Assessment / current status", height=100)
                recommendations = st.text_area("R · Recommendation / immediate priorities", height=100)
            with c3:
                airway = st.text_area("Airway / respiratory support", height=80)
                fluids_feeding = st.text_area("Fluids, feeding and elimination", height=80)
                meds_pending = st.text_area("Medication due / pending", height=80)
                lines_equipment = st.text_area("Lines, devices and equipment concerns", height=80)
            investigations = st.text_area("Pending tests / investigations / consultations")
            safety_concerns = st.text_area("Safety concerns / infection precautions")
            escalation_plan = st.text_area("Escalation plan and contact instructions")
            acknowledgement = st.text_area("Handover acknowledgement / questions clarified")
            save_hand = st.form_submit_button("Save shift handover")
        if save_hand:
            if not all(x.strip() for x in [outgoing, incoming, situation]):
                st.error("Outgoing nurse, incoming nurse and situation are required.")
            else:
                save("""INSERT INTO handovers(admission_id, handover_date, handover_time, shift, outgoing_nurse, incoming_nurse, situation,
                    background, assessment_summary, recommendations, airway_respiratory, fluids_feeding_elimination, medication_due_or_pending,
                    lines_devices_equipment, investigations_pending, safety_concerns, escalation_plan, acknowledgement, created_utc)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (admission_id, hand_date.isoformat(), hand_time.strftime("%H:%M"), shift, outgoing.strip(), incoming.strip(), situation.strip(),
                     background.strip() or None, assessment_summary.strip() or None, recommendations.strip() or None, airway.strip() or None,
                     fluids_feeding.strip() or None, meds_pending.strip() or None, lines_equipment.strip() or None, investigations.strip() or None,
                     safety_concerns.strip() or None, escalation_plan.strip() or None, acknowledgement.strip() or None, utc_now()))
                st.success("Shift handover saved.")

    # 9. Progress notes and history
    with sections[8]:
        st.subheader("Nursing progress notes")
        with st.form("progress_form", clear_on_submit=True):
            c1, c2 = st.columns(2)
            with c1:
                note_date = st.date_input("Note date", value=view_date, key="note_date")
                note_time = st.time_input("Note time", value=datetime.now().time().replace(second=0, microsecond=0), key="note_time")
                note_type = st.selectbox("Note type", ["Routine progress", "Focused reassessment", "Intervention", "Communication / escalation", "Incident follow-up", "Other"])
                note_nurse = st.text_input("Nurse name / staff ID *", key="progress_nurse")
            with c2:
                note_assessment = st.text_area("Assessment / observed facts")
                note_intervention = st.text_area("Nursing intervention / care provided")
                note_response = st.text_area("Response / evaluation")
                note_communication = st.text_area("Communication, clinician notified and response")
            save_note = st.form_submit_button("Save progress note")
        if save_note:
            if not note_nurse.strip() or not any(x.strip() for x in [note_assessment, note_intervention, note_response, note_communication]):
                st.error("Nurse identification and at least one note field are required.")
            else:
                save("""INSERT INTO progress_notes(admission_id, note_date, note_time, note_type, assessment, nursing_intervention,
                    response_evaluation, communication_escalation, nurse_name, created_utc) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                    (admission_id, note_date.isoformat(), note_time.strftime("%H:%M"), note_type, note_assessment.strip() or None,
                     note_intervention.strip() or None, note_response.strip() or None, note_communication.strip() or None, note_nurse.strip(), utc_now()))
                st.success("Progress note saved.")

        st.divider()
        st.subheader("Chronological record history")
        hist_tabs = st.tabs(["Admission", "Assessments", "Observations", "Fluid balance", "Medication", "Equipment", "Handovers", "Progress notes"])
        queries = [
            ("Admission", "SELECT admission_date AS Date, admission_time AS Time, admission_reason AS Summary, admitting_nurse AS Staff, created_utc AS 'Saved UTC' FROM admissions WHERE id=?", (admission_id,)),
            ("Assessments", "SELECT assessment_date AS Date, assessment_time AS Time, assessment_type AS Type, nurse_name AS Staff, findings_interventions AS Findings, created_utc AS 'Saved UTC' FROM assessments WHERE admission_id=? ORDER BY assessment_date DESC, assessment_time DESC, id DESC", (admission_id,)),
            ("Observations", "SELECT observation_date AS Date, observation_time AS Time, heart_rate AS HR, respiratory_rate AS RR, temperature_c AS 'Temp C', spo2_percent AS 'SpO2 %', fio2_percent AS 'FiO2 %', respiratory_support AS Support, nurse_name AS Staff, note AS Note, created_utc AS 'Saved UTC' FROM observations WHERE admission_id=? ORDER BY observation_date DESC, observation_time DESC, id DESC", (admission_id,)),
            ("Fluid balance", "SELECT record_date AS Date, interval_start AS Start, interval_end AS End, total_intake_ml AS 'Intake mL', total_output_ml AS 'Output mL', net_balance_ml AS 'Net mL', urine_output_ml_kg_hr AS 'Urine mL/kg/hr', nurse_name AS Staff, created_utc AS 'Saved UTC' FROM fluid_records WHERE admission_id=? ORDER BY record_date DESC, interval_start DESC, id DESC", (admission_id,)),
            ("Medication", "SELECT record_date AS Date, medication_name AS Medication, prescribed_dose AS 'Prescribed dose', route AS Route, status AS Status, scheduled_time AS 'Scheduled time', actual_administration_time AS 'Actual time', nurse_name AS Staff, created_utc AS 'Saved UTC' FROM medication_records WHERE admission_id=? ORDER BY record_date DESC, id DESC", (admission_id,)),
            ("Equipment", "SELECT check_date AS Date, check_time AS Time, equipment_type AS Equipment, equipment_identifier AS Identifier, physical_condition AS Condition, function_check AS 'Function check', fault_or_issue AS Fault, action_taken AS Action, nurse_name AS Staff, created_utc AS 'Saved UTC' FROM equipment_checks WHERE admission_id=? ORDER BY check_date DESC, check_time DESC, id DESC", (admission_id,)),
            ("Handovers", "SELECT handover_date AS Date, handover_time AS Time, shift AS Shift, outgoing_nurse AS Outgoing, incoming_nurse AS Incoming, situation AS Situation, recommendations AS Recommendations, created_utc AS 'Saved UTC' FROM handovers WHERE admission_id=? ORDER BY handover_date DESC, handover_time DESC, id DESC", (admission_id,)),
            ("Progress notes", "SELECT note_date AS Date, note_time AS Time, note_type AS Type, assessment AS Assessment, nursing_intervention AS Intervention, response_evaluation AS Response, nurse_name AS Staff, created_utc AS 'Saved UTC' FROM progress_notes WHERE admission_id=? ORDER BY note_date DESC, note_time DESC, id DESC", (admission_id,)),
        ]
        for tab, (name, sql, params) in zip(hist_tabs, queries):
            with tab:
                rows = fetchall(sql, params)
                if rows:
                    df = pd.DataFrame([dict(r) for r in rows])
                    st.dataframe(df, use_container_width=True, hide_index=True)
                    st.download_button(f"Export {name} as CSV", df.to_csv(index=False).encode("utf-8-sig"),
                                       file_name=f"admission_{admission_id}_{name.lower().replace(' ', '_')}.csv",
                                       mime="text/csv", key=f"export_{name}_{admission_id}")
                else:
                    st.info(f"No {name.lower()} records have been saved for this admission.")

st.divider()
st.caption("Every form starts blank. Enter only verified observations and information from the clinical record. This prototype is not a substitute for the hospital's approved charting system.")
