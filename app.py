"""
Today Nurse NICU Documentation System
Blank, linked documentation forms for a neonatal unit.

Prototype only; not a validated EHR. Do not use identifiable patient data
until authentication, authorization, encryption, audit logging, backups,
retention controls, and clinical governance have been implemented and approved.
"""

import json
import math
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, time, timezone
from pathlib import Path

import pandas as pd
import streamlit as st

APP_VERSION = "2.0"
DB_PATH = Path(__file__).with_name("today_nurse_nicu.db")

st.set_page_config(
    page_title="Today Nurse | NICU Documentation",
    page_icon="🩺",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Utilities and persistence
# ---------------------------------------------------------------------------

def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def validate_measurement(
    label: str,
    value: float | int | None,
    minimum: float,
    maximum: float,
    *,
    allow_zero: bool = True,
) -> float | None:
    """Validate a measured numeric value. Never infer missing data."""
    if value is None:
        return None

    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label}: enter a valid numeric value.") from exc

    if not math.isfinite(number):
        raise ValueError(f"{label}: value must be finite.")

    if number < minimum or number > maximum:
        raise ValueError(
            f"{label}: value must be between {minimum} and {maximum}."
        )

    if not allow_zero and number == 0:
        raise ValueError(f"{label}: value must be greater than zero.")

    return number


def validate_staff_name(name: str) -> str:
    """Require a non-empty staff identifier."""
    cleaned = name.strip()
    if not cleaned:
        raise ValueError("Staff name or staff ID is required.")
    return cleaned


def validate_time_order(start, end) -> float:
    """Validate same-day intervals; overnight intervals need explicit dates."""
    start_minutes = start.hour * 60 + start.minute
    end_minutes = end.hour * 60 + end.minute

    if end_minutes <= start_minutes:
        raise ValueError(
            "The end time must be later than the start time. "
            "Overnight intervals need an explicit end date."
        )

    return (end_minutes - start_minutes) / 60.0

@contextmanager
def db():
    conn = sqlite3.connect(DB_PATH, timeout=20)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def columns_for(conn, table):
    return {r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def ensure_column(conn, table, name, sql_type):
    if name not in columns_for(conn, table):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {sql_type}")


def init_db():
    with db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS patients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            hospital_patient_id TEXT NOT NULL UNIQUE,
            patient_label TEXT NOT NULL,
            date_of_birth TEXT,
            sex TEXT,
            residential_address TEXT,
            guardian_name TEXT,
            guardian_relationship TEXT,
            primary_contact_phone TEXT,
            alternate_contact_phone TEXT,
            contact_email TEXT,
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
            admitting_nurse TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Active',
            admission_record_json TEXT,
            created_utc TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS observations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admission_id INTEGER NOT NULL REFERENCES admissions(id),
            observation_date TEXT NOT NULL,
            observation_time TEXT NOT NULL,
            heart_rate REAL, respiratory_rate REAL, temperature_c REAL,
            spo2_percent REAL, fio2_percent REAL, blood_pressure TEXT,
            pain_score TEXT, respiratory_support TEXT, support_settings TEXT,
            capillary_refill TEXT, nurse_name TEXT NOT NULL, note TEXT,
            created_utc TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS fluid_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admission_id INTEGER NOT NULL REFERENCES admissions(id),
            record_date TEXT NOT NULL,
            interval_start TEXT NOT NULL, interval_end TEXT NOT NULL,
            weight_g REAL NOT NULL,
            iv_ml REAL NOT NULL DEFAULT 0, feeds_ml REAL NOT NULL DEFAULT 0,
            medication_ml REAL NOT NULL DEFAULT 0, blood_products_ml REAL NOT NULL DEFAULT 0,
            other_intake_ml REAL NOT NULL DEFAULT 0, urine_ml REAL NOT NULL DEFAULT 0,
            stool_count INTEGER NOT NULL DEFAULT 0, emesis_ml REAL NOT NULL DEFAULT 0,
            drains_ml REAL NOT NULL DEFAULT 0, other_output_ml REAL NOT NULL DEFAULT 0,
            total_intake_ml REAL NOT NULL, total_output_ml REAL NOT NULL,
            net_balance_ml REAL NOT NULL, urine_output_ml_kg_hr REAL,
            nurse_name TEXT NOT NULL, notes TEXT, created_utc TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS medication_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admission_id INTEGER NOT NULL REFERENCES admissions(id),
            record_date TEXT NOT NULL, medication_name TEXT NOT NULL,
            prescribed_dose TEXT NOT NULL, route TEXT NOT NULL, frequency TEXT,
            scheduled_time TEXT, status TEXT NOT NULL, actual_administration_time TEXT,
            weight_used_g REAL, allergy_check TEXT NOT NULL, double_check TEXT,
            nurse_name TEXT NOT NULL, indication TEXT,
            withheld_or_omitted_reason TEXT, response_or_notes TEXT, created_utc TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS assessments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admission_id INTEGER NOT NULL REFERENCES admissions(id),
            assessment_date TEXT NOT NULL, assessment_time TEXT NOT NULL,
            assessment_type TEXT NOT NULL, gestational_age_context TEXT,
            neurological TEXT, respiratory TEXT, cardiovascular TEXT,
            thermoregulation_skin TEXT, gastrointestinal_feeding TEXT,
            genitourinary TEXT, musculoskeletal TEXT, pain_comfort TEXT,
            lines_tubes_devices TEXT, infection_risk TEXT,
            developmental_family_care TEXT, findings_interventions TEXT,
            escalation_actions TEXT, nurse_name TEXT NOT NULL, created_utc TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS equipment_checks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admission_id INTEGER NOT NULL REFERENCES admissions(id),
            check_date TEXT NOT NULL, check_time TEXT NOT NULL,
            equipment_type TEXT NOT NULL, equipment_identifier TEXT,
            assigned_patient_confirmed TEXT NOT NULL, physical_condition TEXT NOT NULL,
            function_check TEXT NOT NULL, alarm_check TEXT, power_gas_check TEXT,
            consumables_check TEXT, cleaning_status TEXT, fault_or_issue TEXT,
            action_taken TEXT, escalation_or_ticket TEXT, outgoing_staff TEXT,
            incoming_staff TEXT, nurse_name TEXT NOT NULL, notes TEXT, created_utc TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS handovers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admission_id INTEGER NOT NULL REFERENCES admissions(id),
            handover_date TEXT NOT NULL, handover_time TEXT NOT NULL,
            shift TEXT NOT NULL, outgoing_nurse TEXT NOT NULL, incoming_nurse TEXT NOT NULL,
            situation TEXT NOT NULL, background TEXT, assessment_summary TEXT,
            recommendations TEXT, airway_respiratory TEXT, fluids_feeding_elimination TEXT,
            medication_due_or_pending TEXT, lines_devices_equipment TEXT,
            investigations_pending TEXT, safety_concerns TEXT, escalation_plan TEXT,
            acknowledgement TEXT, created_utc TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS progress_notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admission_id INTEGER NOT NULL REFERENCES admissions(id),
            note_date TEXT NOT NULL, note_time TEXT NOT NULL, note_type TEXT NOT NULL,
            assessment TEXT, nursing_intervention TEXT, response_evaluation TEXT,
            communication_escalation TEXT, nurse_name TEXT NOT NULL, created_utc TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS nursing_care_plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admission_id INTEGER NOT NULL REFERENCES admissions(id),
            plan_date TEXT NOT NULL, review_date TEXT,
            priority TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'Active',
            problem_or_diagnosis TEXT NOT NULL, assessment_cues TEXT,
            goals_outcomes TEXT NOT NULL, interventions TEXT NOT NULL,
            frequency_or_schedule TEXT, implementation_notes TEXT,
            evaluation TEXT, evaluation_status TEXT NOT NULL DEFAULT 'Ongoing',
            escalation_or_communication TEXT, nurse_name TEXT NOT NULL,
            reviewer_name TEXT, created_utc TEXT NOT NULL, updated_utc TEXT NOT NULL
        );
        """)

        # Migrations for databases made by earlier app versions.
        patient_additions = {
            "residential_address": "TEXT", "guardian_name": "TEXT",
            "guardian_relationship": "TEXT", "primary_contact_phone": "TEXT",
            "alternate_contact_phone": "TEXT", "contact_email": "TEXT",
        }
        for name, typ in patient_additions.items():
            ensure_column(conn, "patients", name, typ)
        ensure_column(conn, "admissions", "admission_record_json", "TEXT")
        ensure_column(conn, "admissions", "status", "TEXT NOT NULL DEFAULT 'Active'")


init_db()


def fetchall(sql, params=()):
    with db() as conn:
        return conn.execute(sql, params).fetchall()


def save(sql, params):
    with db() as conn:
        cur = conn.execute(sql, params)
        return cur.lastrowid


def as_optional(value):
    if value is None:
        return None
    if isinstance(value, str):
        return value.strip() or None
    return value


def export_table(rows, filename, key):
    if rows:
        df = pd.DataFrame([dict(r) for r in rows])
        st.dataframe(df, use_container_width=True, hide_index=True)
        st.download_button(
            "Export CSV",
            df.to_csv(index=False).encode("utf-8-sig"),
            file_name=filename,
            mime="text/csv",
            key=key,
        )
    else:
        st.info("No records have been saved for this admission.")


def show_datetime_inputs(prefix, selected_date):
    a, b = st.columns(2)
    with a:
        d = st.date_input("Date", value=selected_date, key=f"{prefix}_date")
    with b:
        t = st.time_input(
            "Time",
            value=datetime.now().time().replace(second=0, microsecond=0),
            key=f"{prefix}_time",
        )
    return d, t


# ---------------------------------------------------------------------------
# App header and safety notice
# ---------------------------------------------------------------------------

st.title("🩺 Today Nurse | NICU Nursing Documentation")
st.caption(f"Version {APP_VERSION} · Linked documentation forms · SQLite storage")
st.warning(
    "SECURITY NOTICE: This prototype does not provide user authentication, role-based "
    "access, audit-grade record locking, or encrypted clinical storage. Do not enter "
    "identifiable patient information until deployed in an approved, secured environment. "
    "Validate workflows against hospital policies before clinical use."
)

# ---------------------------------------------------------------------------
# Sidebar: admission selection
# ---------------------------------------------------------------------------

with st.sidebar:
    st.header("Patient / admission")
    active_rows = fetchall("""
        SELECT a.id, p.hospital_patient_id, p.patient_label, a.admission_date,
               a.admission_reason, a.status
        FROM admissions a JOIN patients p ON p.id=a.patient_id
        WHERE a.status='Active'
        ORDER BY a.admission_date DESC, a.id DESC
    """)
    admission_labels = {
        f"{r['hospital_patient_id']} | {r['patient_label']} | episode #{r['id']} | {r['admission_date']}": r["id"]
        for r in active_rows
    }
    if admission_labels:
        selected_label = st.selectbox("Active admission", list(admission_labels))
        admission_id = admission_labels[selected_label]
        st.caption("Clinical forms are linked to this admission episode.")
    else:
        admission_id = None
        st.info("No active admission. Register a patient and create an admission first.")
    view_date = st.date_input("Default record date", value=date.today(), key="global_record_date")
    st.divider()
    st.caption("Today Nurse · NICU Documentation")

# ---------------------------------------------------------------------------
# Workflow tabs
# ---------------------------------------------------------------------------

sections = st.tabs([
    "1 · Patient registry",
    "2 · Initial admission",
    "3 · Head-to-toe assessment",
    "4 · Vital signs",
    "5 · Fluid balance",
    "6 · Medication record",
    "7 · Equipment checks",
    "8 · Shift handover",
    "9 · Nursing care plan",
    "10 · Progress notes & history",
])

# 1. Patient registry
with sections[0]:
    st.subheader("Patient registry")
    st.caption("Use the hospital-assigned MRN and follow local privacy and identification policies.")
    with st.form("patient_registration", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            mrn = st.text_input("Medical Record Number (MRN) *")
            patient_label = st.text_input("Newborn name / approved patient label *")
            dob = st.date_input("Date of birth (optional)", value=None, min_value=date(1990, 1, 1), max_value=date.today())
            sex = st.selectbox("Sex", ["Not recorded", "Female", "Male", "Indeterminate / not yet assigned", "Other / per policy"])
            address = st.text_area("Parent/guardian residential address")
        with c2:
            guardian = st.text_input("Parent/guardian full name")
            relationship = st.selectbox("Relationship", ["Not recorded", "Mother", "Father", "Legal guardian", "Other"])
            phone = st.text_input("Primary contact phone")
            alternate_phone = st.text_input("Alternate contact phone")
            email = st.text_input("Contact email (optional)")
        register = st.form_submit_button("Register patient")
    if register:
        if not mrn.strip() or not patient_label.strip():
            st.error("MRN and patient label are required.")
        elif email.strip() and ("@" not in email or "." not in email.split("@")[-1]):
            st.error("Enter a valid email address or leave email blank.")
        else:
            try:
                new_patient = save(
                    """INSERT INTO patients(
                        hospital_patient_id, patient_label, date_of_birth, sex,
                        residential_address, guardian_name, guardian_relationship,
                        primary_contact_phone, alternate_contact_phone, contact_email, created_utc
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        mrn.strip(), patient_label.strip(), dob.isoformat() if dob else None,
                        None if sex == "Not recorded" else sex, as_optional(address),
                        as_optional(guardian), None if relationship == "Not recorded" else relationship,
                        as_optional(phone), as_optional(alternate_phone), as_optional(email), utc_now(),
                    ),
                )
                st.success(f"Patient registered (internal record #{new_patient}). Create an admission in tab 2.")
                st.rerun()
            except sqlite3.IntegrityError:
                st.error("That MRN already exists. Select the existing patient rather than creating a duplicate.")

    patient_rows = fetchall("""
        SELECT id, hospital_patient_id AS MRN, patient_label AS Patient,
               date_of_birth AS DOB, sex AS Sex, guardian_name AS Guardian,
               guardian_relationship AS Relationship, primary_contact_phone AS Phone,
               alternate_contact_phone AS 'Alternate phone', contact_email AS Email,
               residential_address AS Address
        FROM patients ORDER BY patient_label
    """)
    if patient_rows:
        st.markdown("#### Registered patients")
        export_table(patient_rows, "today_nurse_patients.csv", "export_patients")


# 2. Initial admission
with sections[1]:
    st.subheader("Initial NICU admission")
    patients = fetchall("""
        SELECT id, hospital_patient_id, patient_label, date_of_birth, sex,
               residential_address, guardian_name, guardian_relationship,
               primary_contact_phone, alternate_contact_phone, contact_email
        FROM patients ORDER BY patient_label
    """)
    if not patients:
        st.info("Register a patient in tab 1 before creating an admission.")
    else:
        patient_map = {
            f"{r['hospital_patient_id']} | {r['patient_label']}": r["id"] for r in patients
        }
        with st.form("admission_form", clear_on_submit=True):
            patient_key = st.selectbox("Patient *", list(patient_map))
            c1, c2, c3 = st.columns(3)
            with c1:
                adm_date = st.date_input("Admission date", value=view_date, key="adm_date")
                adm_time = st.time_input("Admission time", value=datetime.now().time().replace(second=0, microsecond=0), key="adm_time")
                ga_weeks = st.number_input("Gestational age (completed weeks)", min_value=0, max_value=45, value=0)
                ga_days = st.number_input("Additional gestational days", min_value=0, max_value=6, value=0)
                birth_weight = st.number_input("Birth weight (g)", min_value=0.0, max_value=10000.0, value=0.0, step=10.0)
                admission_weight = st.number_input("Admission weight (g)", min_value=0.0, max_value=10000.0, value=0.0, step=10.0)
            with c2:
                delivery = st.selectbox("Mode of delivery", ["Not documented", "Spontaneous vaginal", "Assisted vaginal", "Caesarean section", "Other / unknown"])
                apgar1 = st.text_input("Apgar at 1 minute")
                apgar5 = st.text_input("Apgar at 5 minutes")
                referring = st.text_input("Referring facility / location")
                reason = st.text_area("Reason for NICU admission *", height=100)
                resuscitation = st.text_area("Delivery-room resuscitation / stabilization", height=90)
            with c3:
                initial_condition = st.text_area("Condition on arrival", height=90)
                maternal_history = st.text_area("Maternal / perinatal history", height=90)
                support = st.selectbox("Respiratory support", ["Not documented", "Room air", "Low-flow oxygen", "HFNC", "CPAP", "NIPPV", "Mechanical ventilation", "Other"])
                settings = st.text_area("Oxygen / respiratory support settings", height=70)
            lines = st.text_area("Lines, tubes and devices")
            allergies = st.text_area("Known allergies / status")
            infection = st.text_area("Infection risk / precautions")
            initial_assessment = st.text_area("Initial nursing assessment")
            priorities = st.text_area("Initial nursing priorities / plan")
            extra_record = st.text_area(
                "Additional neonatal admission record details (optional)",
                help="You can record other locally required admission fields here. Do not enter unverified information.",
            )
            c4, c5 = st.columns(2)
            with c4:
                clinician = st.text_input("Admitting clinician")
            with c5:
                admitting_nurse = st.text_input("Admitting nurse name / staff ID *")
            create_admission = st.form_submit_button("Save initial admission")
        if create_admission:
            if not reason.strip() or not admitting_nurse.strip():
                st.error("Admission reason and admitting nurse are required.")
            else:
                try:
                    new_adm = save(
                        """INSERT INTO admissions(
                            patient_id, admission_date, admission_time, gestational_age_weeks,
                            gestational_age_days, birth_weight_g, admission_weight_g, delivery_mode,
                            apgar_1, apgar_5, referring_facility, admission_reason,
                            maternal_perinatal_history, resuscitation, initial_condition,
                            respiratory_support, oxygen_or_support_settings, lines_devices,
                            allergies, infection_risk, initial_nursing_assessment, nursing_priorities,
                            admitting_clinician, admitting_nurse, admission_record_json, created_utc
                        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (
                            patient_map[patient_key], adm_date.isoformat(), adm_time.strftime("%H:%M"),
                            ga_weeks or None, int(ga_days), birth_weight or None, admission_weight or None,
                            delivery, as_optional(apgar1), as_optional(apgar5), as_optional(referring),
                            reason.strip(), as_optional(maternal_history), as_optional(resuscitation),
                            as_optional(initial_condition), support, as_optional(settings), as_optional(lines),
                            as_optional(allergies), as_optional(infection), as_optional(initial_assessment),
                            as_optional(priorities), as_optional(clinician), admitting_nurse.strip(),
                            json.dumps({"additional_admission_details": extra_record.strip() or None}, ensure_ascii=False),
                            utc_now(),
                        ),
                    )
                    st.success(f"Admission saved as episode #{new_adm}. It is now available in the sidebar.")
                    st.rerun()
                except sqlite3.Error as exc:
                    st.error(f"Could not save admission: {exc}")


# Linked clinical forms require an active admission.
if admission_id is None:
    for idx in range(2, 10):
        with sections[idx]:
            st.info("Register a patient and create an active admission before documenting care.")
else:
    context_rows = fetchall("""
        SELECT a.*, p.hospital_patient_id, p.patient_label, p.date_of_birth, p.sex
        FROM admissions a JOIN patients p ON p.id=a.patient_id WHERE a.id=?
    """, (admission_id,))
    selected_admission = context_rows[0]
    with st.sidebar:
        st.divider()
        st.markdown(f"**Selected patient:** {selected_admission['patient_label']}")
        st.caption(f"MRN: {selected_admission['hospital_patient_id']} · Episode #{admission_id}")
        st.caption(f"Admission: {selected_admission['admission_date']}")

    # 3. Head-to-toe assessment
    with sections[2]:
        st.subheader("Head-to-toe NICU nursing assessment")
        with st.form("assessment_form", clear_on_submit=True):
            c1, c2, c3 = st.columns(3)
            with c1:
                assess_date, assess_time = show_datetime_inputs("assess", view_date)
                assess_type = st.selectbox("Assessment type", ["Initial baseline", "Routine shift assessment", "Focused reassessment", "Post-intervention", "Other"])
                neuro = st.text_area("Neurological: state, tone, activity, reflexes", height=100)
                respiratory = st.text_area("Respiratory: effort, air entry, support, secretions", height=100)
            with c2:
                cardiovascular = st.text_area("Cardiovascular: HR, perfusion, pulses, capillary refill", height=100)
                skin = st.text_area("Thermoregulation / skin: temperature, colour, integrity", height=100)
                gi = st.text_area("GI / feeding: abdomen, feeds, tolerance, emesis, stool", height=100)
                gu = st.text_area("Genitourinary: urine / output", height=80)
            with c3:
                musculoskeletal = st.text_area("Musculoskeletal: movement, posture, symmetry", height=90)
                pain = st.text_input("Pain / comfort tool and score")
                device_assess = st.text_area("Lines, tubes and devices: site, security, condition", height=90)
                infection_assess = st.text_area("Infection risks, precautions, relevant findings", height=90)
                developmental = st.text_area("Developmental care and family involvement", height=90)
            findings = st.text_area("Findings, nursing interventions and evaluation", height=100)
            escalation = st.text_area("Escalation / clinician notified / time / response", height=80)
            nurse = st.text_input("Assessing nurse name / staff ID", key="assess_nurse")
            save_assess = st.form_submit_button("Save assessment")
        if save_assess:
            if not nurse.strip():
                st.error("Nurse name or staff ID is required.")
            else:
                save(
                    """INSERT INTO assessments(
                        admission_id, assessment_date, assessment_time, assessment_type,
                        neurological, respiratory, cardiovascular, thermoregulation_skin,
                        gastrointestinal_feeding, genitourinary, musculoskeletal, pain_comfort,
                        lines_tubes_devices, infection_risk, developmental_family_care,
                        findings_interventions, escalation_actions, nurse_name, created_utc
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        admission_id, assess_date.isoformat(), assess_time.strftime("%H:%M"),
                        assess_type, as_optional(neuro), as_optional(respiratory),
                        as_optional(cardiovascular), as_optional(skin), as_optional(gi),
                        as_optional(gu), as_optional(musculoskeletal), as_optional(pain),
                        as_optional(device_assess), as_optional(infection_assess),
                        as_optional(developmental), as_optional(findings), as_optional(escalation),
                        nurse.strip(), utc_now(),
                    ),
                )
                st.success("Assessment saved.")

    # 4. Vital signs
    with sections[3]:
        st.subheader("Vital signs and monitoring chart")
        with st.form("observation_form", clear_on_submit=True):
            c1, c2, c3 = st.columns(3)
            with c1:
                obs_date, obs_time = show_datetime_inputs("obs", view_date)
                hr = st.number_input("Heart rate (bpm)", min_value=0.0, max_value=350.0, value=None, step=1.0, placeholder="Measured value")
                rr = st.number_input("Respiratory rate (/min)", min_value=0.0, max_value=200.0, value=None, step=1.0, placeholder="Measured value")
            with c2:
                temp = st.number_input("Temperature (°C)", min_value=20.0, max_value=45.0, value=None, step=0.1, placeholder="Measured value")
                spo2 = st.number_input("SpO₂ (%)", min_value=0.0, max_value=100.0, value=None, step=1.0, placeholder="Measured value")
                fio2 = st.number_input("FiO₂ (%)", min_value=21.0, max_value=100.0, value=None, step=1.0, placeholder="If applicable")
                bp = st.text_input("Blood pressure (include units / site)")
            with c3:
                pain_score = st.text_input("Pain tool and score")
                respiratory_support = st.selectbox("Respiratory support", ["Not documented", "Room air", "Oxygen", "HFNC", "CPAP", "NIPPV", "Mechanical ventilation", "Other"])
                support_settings = st.text_input("Support settings / interface")
                refill = st.selectbox("Capillary refill", ["Not assessed", "Within locally expected range", "Delayed / abnormal", "Other / details in note"])
            obs_nurse = st.text_input("Recording nurse name / staff ID", key="obs_nurse")
            obs_note = st.text_area("Clinical observation / action / escalation", max_chars=3000)
            save_obs = st.form_submit_button("Save observation")
        if save_obs:
            if not obs_nurse.strip():
                st.error("Nurse name or staff ID is required.")
            elif all(v is None for v in [hr, rr, temp, spo2, fio2]) and not obs_note.strip():
                st.error("Enter at least one measured observation or a clinical note.")
            else:
                try:
                    for label, value, lo, hi in [
                        ("Heart rate", hr, 0, 350), ("Respiratory rate", rr, 0, 200),
                        ("Temperature", temp, 20, 45), ("SpO₂", spo2, 0, 100), ("FiO₂", fio2, 21, 100),
                    ]:
                        if value is not None and (not math.isfinite(float(value)) or not lo <= float(value) <= hi):
                            raise ValueError(f"{label} value is invalid.")
                    save(
                        """INSERT INTO observations(
                            admission_id, observation_date, observation_time, heart_rate, respiratory_rate,
                            temperature_c, spo2_percent, fio2_percent, blood_pressure, pain_score,
                            respiratory_support, support_settings, capillary_refill, nurse_name, note, created_utc
                        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (
                            admission_id, obs_date.isoformat(), obs_time.strftime("%H:%M"), hr, rr, temp,
                            spo2, fio2, as_optional(bp), as_optional(pain_score), respiratory_support,
                            as_optional(support_settings), refill, obs_nurse.strip(), as_optional(obs_note), utc_now(),
                        ),
                    )
                    st.success("Observation saved.")
                except (ValueError, sqlite3.Error) as exc:
                    st.error(f"Could not save observation: {exc}")

    # 5. Fluid balance
    with sections[4]:
        st.subheader("Fluid intake and output chart")
        st.caption("Use actual measured values for a defined, non-overlapping interval. Use 0 only when confirmed zero.")
        with st.form("fluid_form", clear_on_submit=True):
            c1, c2, c3 = st.columns(3)
            with c1:
                fluid_date = st.date_input("Record date", value=view_date, key="fluid_date")
                start_time = st.time_input("Interval start", value=time(0, 0), key="fluid_start")
                end_time = st.time_input("Interval end", value=time(1, 0), key="fluid_end")
                weight_g = st.number_input("Measured weight used (g)", min_value=0.0, max_value=10000.0, value=None, step=10.0, placeholder="Measured weight")
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
                    raise ValueError("Enter the measured weight used for calculation.")
                volumes = [iv, feeds, med_ml, blood_ml, other_in, urine, emesis, drains, other_out]
                if any(v is None for v in volumes) or stools is None:
                    raise ValueError("Complete each intake/output field; enter 0 only when confirmed zero.")
                start_dt = datetime.combine(fluid_date, start_time)
                end_dt = datetime.combine(fluid_date, end_time)
                if end_dt <= start_dt:
                    raise ValueError("End must be later than start on the selected date. Split overnight intervals across dates.")
                duration_h = (end_dt - start_dt).total_seconds() / 3600
                intake = float(iv + feeds + med_ml + blood_ml + other_in)
                output = float(urine + emesis + drains + other_out)
                net = intake - output
                urine_rate = float(urine) / (float(weight_g) / 1000) / duration_h
                save(
                    """INSERT INTO fluid_records(
                        admission_id, record_date, interval_start, interval_end, weight_g,
                        iv_ml, feeds_ml, medication_ml, blood_products_ml, other_intake_ml,
                        urine_ml, stool_count, emesis_ml, drains_ml, other_output_ml,
                        total_intake_ml, total_output_ml, net_balance_ml, urine_output_ml_kg_hr,
                        nurse_name, notes, created_utc
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        admission_id, fluid_date.isoformat(), start_time.strftime("%H:%M"),
                        end_time.strftime("%H:%M"), weight_g, iv, feeds, med_ml, blood_ml,
                        other_in, urine, stools, emesis, drains, other_out, intake, output, net,
                        urine_rate, fluid_nurse.strip(), as_optional(fluid_notes), utc_now(),
                    ),
                )
                a, b, c, d = st.columns(4)
                a.metric("Total intake", f"{intake:.1f} mL")
                b.metric("Total output", f"{output:.1f} mL")
                c.metric("Net balance", f"{net:+.1f} mL")
                d.metric("Urine output estimate", f"{urine_rate:.2f} mL/kg/hr")
                st.success("Fluid interval saved. Confirm calculation conventions with local policy.")
            except (ValueError, TypeError, sqlite3.Error) as exc:
                st.error(f"Could not save fluid record: {exc}")

    # 6. Medication administration record
    with sections[5]:
        st.subheader("Medication administration record (MAR)")
        st.warning("Document against a verified prescription and local neonatal medication policy. This form does not prescribe or authorize doses.")
        with st.form("med_form", clear_on_submit=True):
            c1, c2 = st.columns(2)
            with c1:
                med_date = st.date_input("Record date", value=view_date, key="med_date")
                med_name = st.text_input("Medication name as prescribed *")
                prescribed_dose = st.text_input("Prescribed dose and units *")
                route = st.selectbox("Route *", ["Select route", "Oral / enteral", "IV", "IM", "SC", "Inhaled / nebulized", "Topical", "Other / per prescription"])
                frequency = st.text_input("Frequency / schedule")
                scheduled_time = st.text_input("Scheduled time (HH:MM or as prescribed)")
                med_status = st.selectbox("Administration status", ["Administered", "Withheld", "Omitted / not given", "Delayed", "Refused", "Other"])
            with c2:
                actual_time = st.text_input("Actual administration time (HH:MM)")
                med_weight = st.number_input("Weight referenced by prescription (g, if applicable)", min_value=0.0, max_value=10000.0, value=None, step=10.0, placeholder="If applicable")
                allergy_check = st.selectbox("Allergy status checked", ["Select status", "Checked; none known documented", "Known allergy reviewed", "Unable to verify; escalated", "Not applicable per policy"])
                double_check = st.selectbox("Independent double-check", ["Not indicated by policy", "Completed per policy", "Required but not completed; escalated", "Not applicable / local policy"])
                med_nurse = st.text_input("Administering nurse name / staff ID *")
                indication = st.text_input("Indication / prescription reference")
            omit_reason = st.text_area("Reason if withheld, omitted, delayed or not given")
            response = st.text_area("Response, monitoring, adverse effects or notes")
            save_med = st.form_submit_button("Save medication record")
        if save_med:
            if not med_name.strip() or not prescribed_dose.strip() or route == "Select route" or not med_nurse.strip():
                st.error("Medication, prescribed dose, route and nurse identification are required.")
            elif allergy_check == "Select status":
                st.error("Record the allergy-status check.")
            elif med_status != "Administered" and not omit_reason.strip():
                st.error("Document the reason when medication was not administered as scheduled.")
            else:
                save(
                    """INSERT INTO medication_records(
                        admission_id, record_date, medication_name, prescribed_dose, route, frequency,
                        scheduled_time, status, actual_administration_time, weight_used_g, allergy_check,
                        double_check, nurse_name, indication, withheld_or_omitted_reason, response_or_notes, created_utc
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        admission_id, med_date.isoformat(), med_name.strip(), prescribed_dose.strip(),
                        route, as_optional(frequency), as_optional(scheduled_time), med_status,
                        as_optional(actual_time), med_weight, allergy_check, double_check, med_nurse.strip(),
                        as_optional(indication), as_optional(omit_reason), as_optional(response), utc_now(),
                    ),
                )
                st.success("Medication administration record saved.")

    # 7. Equipment safety check
    with sections[6]:
        st.subheader("Equipment safety check and handover")
        with st.form("equipment_form", clear_on_submit=True):
            c1, c2 = st.columns(2)
            with c1:
                eq_date, eq_time = show_datetime_inputs("eq", view_date)
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
                save(
                    """INSERT INTO equipment_checks(
                        admission_id, check_date, check_time, equipment_type, equipment_identifier,
                        assigned_patient_confirmed, physical_condition, function_check, alarm_check,
                        power_gas_check, consumables_check, cleaning_status, fault_or_issue, action_taken,
                        escalation_or_ticket, outgoing_staff, incoming_staff, nurse_name, notes, created_utc
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        admission_id, eq_date.isoformat(), eq_time.strftime("%H:%M"), eq_type,
                        as_optional(eq_id), assigned, condition, function_check, alarm_check, power_gas,
                        consumables, cleaning, as_optional(fault), as_optional(action), as_optional(ticket),
                        as_optional(outgoing), as_optional(incoming), eq_nurse.strip(), as_optional(eq_notes), utc_now(),
                    ),
                )
                st.success("Equipment check saved.")

    # 8. Shift handover
    with sections[7]:
        st.subheader("Nursing shift handover · SBAR")
        with st.form("handover_form", clear_on_submit=True):
            c1, c2, c3 = st.columns(3)
            with c1:
                hand_date, hand_time = show_datetime_inputs("hand", view_date)
                shift = st.selectbox("Shift", ["Day", "Evening", "Night", "Other"])
                outgoing_nurse = st.text_input("Outgoing nurse *")
                incoming_nurse = st.text_input("Incoming nurse *")
            with c2:
                situation = st.text_area("S · Situation / current concern *", height=100)
                background = st.text_area("B · Background / diagnosis / history", height=100)
                assessment_summary = st.text_area("A · Assessment / current status", height=100)
                recommendations = st.text_area("R · Recommendations / priorities", height=100)
            with c3:
                airway = st.text_area("Airway / respiratory support", height=80)
                fluids_feeding = st.text_area("Fluids, feeding and elimination", height=80)
                meds_pending = st.text_area("Medication due / pending", height=80)
                lines_equipment = st.text_area("Lines, devices and equipment concerns", height=80)
            investigations = st.text_area("Pending tests / investigations / consultations")
            safety_concerns = st.text_area("Safety concerns / infection precautions")
            escalation_plan = st.text_area("Escalation plan / contact instructions")
            acknowledgement = st.text_area("Handover acknowledgement / questions clarified")
            save_hand = st.form_submit_button("Save shift handover")
        if save_hand:
            if not all(x.strip() for x in [outgoing_nurse, incoming_nurse, situation]):
                st.error("Outgoing nurse, incoming nurse and situation are required.")
            else:
                save(
                    """INSERT INTO handovers(
                        admission_id, handover_date, handover_time, shift, outgoing_nurse, incoming_nurse,
                        situation, background, assessment_summary, recommendations, airway_respiratory,
                        fluids_feeding_elimination, medication_due_or_pending, lines_devices_equipment,
                        investigations_pending, safety_concerns, escalation_plan, acknowledgement, created_utc
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        admission_id, hand_date.isoformat(), hand_time.strftime("%H:%M"), shift,
                        outgoing_nurse.strip(), incoming_nurse.strip(), situation.strip(), as_optional(background),
                        as_optional(assessment_summary), as_optional(recommendations), as_optional(airway),
                        as_optional(fluids_feeding), as_optional(meds_pending), as_optional(lines_equipment),
                        as_optional(investigations), as_optional(safety_concerns), as_optional(escalation_plan),
                        as_optional(acknowledgement), utc_now(),
                    ),
                )
                st.success("Shift handover saved.")

    # 9. Nursing care plan
    with sections[8]:
        st.subheader("Individualized NICU nursing care plan")
        st.caption(
            "Link assessment findings to a nursing problem, measurable goals, planned care, "
            "implementation, and evaluation. Use clinical judgment and local neonatal protocols."
        )
        with st.expander("Care plan workflow", expanded=True):
            st.markdown(
                "1. **Assess:** document relevant cues and verified findings.\n"
                "2. **Identify:** record the nursing diagnosis or problem supported by those findings.\n"
                "3. **Plan:** set measurable outcomes and timeframes.\n"
                "4. **Implement:** record planned interventions and what was actually performed.\n"
                "5. **Evaluate:** compare the patient's response with the expected outcomes and revise the plan as appropriate."
            )
        with st.form("nursing_care_plan_form", clear_on_submit=True):
            c1, c2, c3 = st.columns(3)
            with c1:
                plan_date = st.date_input("Plan initiated", value=view_date, key="ncp_date")
                review_date = st.date_input("Next review date", value=view_date, key="ncp_review_date")
                priority = st.selectbox("Priority", ["Immediate / high", "High", "Moderate", "Low"])
                plan_status = st.selectbox("Care-plan status", ["Active", "On hold", "Discontinued", "Completed"])
            with c2:
                problem = st.text_area(
                    "Nursing diagnosis / identified problem *",
                    placeholder="State the patient-specific problem supported by assessment findings.",
                    height=145,
                )
                cues = st.text_area(
                    "Assessment cues / supporting evidence",
                    placeholder="Observed signs, symptoms, measurements, risks, relevant history.",
                    height=145,
                )
            with c3:
                goals = st.text_area(
                    "Expected outcomes / measurable goals *",
                    placeholder="Write observable outcomes and a target timeframe.",
                    height=145,
                )
                interventions = st.text_area(
                    "Planned nursing interventions *",
                    placeholder="Individualized nursing actions, monitoring, safety measures, and escalation criteria.",
                    height=145,
                )
            frequency = st.text_area(
                "Frequency / schedule",
                placeholder="Record prescribed or locally approved frequency; do not infer it.",
            )
            implementation = st.text_area(
                "Implementation notes",
                placeholder="Record care actually provided, including relevant dates/times.",
            )
            evaluation = st.text_area(
                "Evaluation / response to care",
                placeholder="Compare observed findings with the expected outcomes.",
            )
            c1, c2 = st.columns(2)
            with c1:
                evaluation_status = st.selectbox(
                    "Outcome evaluation",
                    ["Ongoing", "Achieved", "Partially achieved", "Not achieved", "Unable to evaluate"],
                )
                nurse_name = st.text_input("Responsible nurse name / staff ID *", key="ncp_nurse")
            with c2:
                reviewer_name = st.text_input("Reviewer / next-shift nurse (optional)")
                escalation = st.text_area("Communication / escalation", placeholder="Person/team notified, time, response, follow-up.")
            save_plan = st.form_submit_button("Save nursing care plan")
        if save_plan:
            if not problem.strip() or not goals.strip() or not interventions.strip():
                st.error("Problem/diagnosis, expected outcomes, and planned interventions are required.")
            elif not nurse_name.strip():
                st.error("Responsible nurse name or staff ID is required.")
            elif review_date < plan_date:
                st.error("Next review date cannot be earlier than the plan initiation date.")
            else:
                try:
                    save(
                        """INSERT INTO nursing_care_plans(
                            admission_id, plan_date, review_date, priority, status,
                            problem_or_diagnosis, assessment_cues, goals_outcomes, interventions,
                            frequency_or_schedule, implementation_notes, evaluation, evaluation_status,
                            escalation_or_communication, nurse_name, reviewer_name, created_utc, updated_utc
                        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (
                            admission_id, plan_date.isoformat(), review_date.isoformat(), priority,
                            plan_status, problem.strip(), as_optional(cues), goals.strip(), interventions.strip(),
                            as_optional(frequency), as_optional(implementation), as_optional(evaluation),
                            evaluation_status, as_optional(escalation), nurse_name.strip(),
                            as_optional(reviewer_name), utc_now(), utc_now(),
                        ),
                    )
                    st.success("Nursing care plan saved and linked to the selected admission.")
                except sqlite3.Error as exc:
                    st.error(f"Could not save nursing care plan: {exc}")

        st.divider()
        st.subheader("Care plans for this admission")
        plan_rows = fetchall(
            """SELECT id, plan_date AS 'Plan date', review_date AS 'Review date',
                      priority AS Priority, status AS Status,
                      problem_or_diagnosis AS 'Nursing problem',
                      goals_outcomes AS 'Expected outcomes',
                      evaluation_status AS 'Evaluation status',
                      nurse_name AS 'Responsible nurse',
                      reviewer_name AS Reviewer, updated_utc AS 'Updated UTC'
               FROM nursing_care_plans
               WHERE admission_id=? ORDER BY plan_date DESC, id DESC""",
            (admission_id,),
        )
        if plan_rows:
            plan_df = pd.DataFrame([dict(r) for r in plan_rows])
            st.dataframe(plan_df, use_container_width=True, hide_index=True)
            st.download_button(
                "Export care plans as CSV",
                plan_df.to_csv(index=False).encode("utf-8-sig"),
                file_name=f"admission_{admission_id}_nursing_care_plans.csv",
                mime="text/csv",
                key=f"export_care_plans_{admission_id}",
            )
            with st.expander("View full care-plan details"):
                full_plans = fetchall(
                    "SELECT * FROM nursing_care_plans WHERE admission_id=? ORDER BY plan_date DESC, id DESC",
                    (admission_id,),
                )
                for p in full_plans:
                    with st.container(border=True):
                        st.markdown(f"**Plan #{p['id']} · {p['plan_date']} · {p['priority']} · {p['status']}**")
                        st.markdown(f"**Problem / diagnosis:** {p['problem_or_diagnosis']}")
                        st.markdown(f"**Assessment cues:** {p['assessment_cues'] or 'Not recorded'}")
                        st.markdown(f"**Expected outcomes:** {p['goals_outcomes']}")
                        st.markdown(f"**Planned interventions:** {p['interventions']}")
                        st.markdown(f"**Frequency / schedule:** {p['frequency_or_schedule'] or 'Not recorded'}")
                        st.markdown(f"**Implementation:** {p['implementation_notes'] or 'Not recorded'}")
                        st.markdown(f"**Evaluation:** {p['evaluation'] or 'Not recorded'}")
                        st.markdown(f"**Outcome status:** {p['evaluation_status']}")
                        st.markdown(f"**Communication / escalation:** {p['escalation_or_communication'] or 'Not recorded'}")
                        st.caption(
                            f"Responsible nurse: {p['nurse_name']} · Reviewer: {p['reviewer_name'] or 'Not recorded'} · "
                            f"Created UTC: {p['created_utc']} · Updated UTC: {p['updated_utc']}"
                        )
        else:
            st.info("No nursing care plans have been saved for this admission yet.")

    # 10. Progress notes and history
    with sections[9]:
        st.subheader("Nursing progress notes")
        with st.form("progress_form", clear_on_submit=True):
            c1, c2 = st.columns(2)
            with c1:
                note_date, note_time = show_datetime_inputs("progress", view_date)
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
                save(
                    """INSERT INTO progress_notes(
                        admission_id, note_date, note_time, note_type, assessment,
                        nursing_intervention, response_evaluation, communication_escalation,
                        nurse_name, created_utc
                    ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                    (
                        admission_id, note_date.isoformat(), note_time.strftime("%H:%M"), note_type,
                        as_optional(note_assessment), as_optional(note_intervention), as_optional(note_response),
                        as_optional(note_communication), note_nurse.strip(), utc_now(),
                    ),
                )
                st.success("Progress note saved.")

        st.divider()
        st.subheader("Chronological record history")
        history_tabs = st.tabs([
            "Admission", "Assessments", "Observations", "Fluid balance", "Medication",
            "Equipment", "Handovers", "Care plans", "Progress notes",
        ])
        history_queries = [
            ("Admission", """SELECT admission_date AS Date, admission_time AS Time,
                admission_reason AS Summary, admitting_nurse AS Staff, status AS Status,
                admission_record_json AS 'Additional details', created_utc AS 'Saved UTC'
                FROM admissions WHERE id=?""", (admission_id,)),
            ("Assessments", """SELECT assessment_date AS Date, assessment_time AS Time,
                assessment_type AS Type, neurological AS Neurological, respiratory AS Respiratory,
                cardiovascular AS Cardiovascular, findings_interventions AS Findings,
                escalation_actions AS Escalation, nurse_name AS Staff, created_utc AS 'Saved UTC'
                FROM assessments WHERE admission_id=? ORDER BY assessment_date DESC, assessment_time DESC, id DESC""", (admission_id,)),
            ("Observations", """SELECT observation_date AS Date, observation_time AS Time,
                heart_rate AS HR, respiratory_rate AS RR, temperature_c AS 'Temp C',
                spo2_percent AS 'SpO2 %', fio2_percent AS 'FiO2 %', blood_pressure AS BP,
                respiratory_support AS Support, support_settings AS 'Support settings',
                nurse_name AS Staff, note AS Note, created_utc AS 'Saved UTC'
                FROM observations WHERE admission_id=? ORDER BY observation_date DESC, observation_time DESC, id DESC""", (admission_id,)),
            ("Fluid balance", """SELECT record_date AS Date, interval_start AS Start, interval_end AS End,
                total_intake_ml AS 'Intake mL', total_output_ml AS 'Output mL',
                net_balance_ml AS 'Net mL', urine_output_ml_kg_hr AS 'Urine mL/kg/hr',
                nurse_name AS Staff, notes AS Notes, created_utc AS 'Saved UTC'
                FROM fluid_records WHERE admission_id=? ORDER BY record_date DESC, interval_start DESC, id DESC""", (admission_id,)),
            ("Medication", """SELECT record_date AS Date, medication_name AS Medication,
                prescribed_dose AS 'Prescribed dose', route AS Route, status AS Status,
                scheduled_time AS 'Scheduled time', actual_administration_time AS 'Actual time',
                withheld_or_omitted_reason AS 'Reason if not given', nurse_name AS Staff,
                created_utc AS 'Saved UTC'
                FROM medication_records WHERE admission_id=? ORDER BY record_date DESC, id DESC""", (admission_id,)),
            ("Equipment", """SELECT check_date AS Date, check_time AS Time, equipment_type AS Equipment,
                equipment_identifier AS Identifier, physical_condition AS Condition,
                function_check AS 'Function check', fault_or_issue AS Fault, action_taken AS Action,
                nurse_name AS Staff, created_utc AS 'Saved UTC'
                FROM equipment_checks WHERE admission_id=? ORDER BY check_date DESC, check_time DESC, id DESC""", (admission_id,)),
            ("Handovers", """SELECT handover_date AS Date, handover_time AS Time, shift AS Shift,
                outgoing_nurse AS Outgoing, incoming_nurse AS Incoming, situation AS Situation,
                recommendations AS Recommendations, created_utc AS 'Saved UTC'
                FROM handovers WHERE admission_id=? ORDER BY handover_date DESC, handover_time DESC, id DESC""", (admission_id,)),
            ("Care plans", """SELECT plan_date AS 'Plan date', review_date AS 'Review date',
                priority AS Priority, status AS Status, problem_or_diagnosis AS 'Nursing problem',
                goals_outcomes AS 'Expected outcomes', evaluation_status AS 'Evaluation status',
                nurse_name AS Staff, reviewer_name AS Reviewer, updated_utc AS 'Updated UTC'
                FROM nursing_care_plans WHERE admission_id=? ORDER BY plan_date DESC, id DESC""", (admission_id,)),
            ("Progress notes", """SELECT note_date AS Date, note_time AS Time, note_type AS Type,
                assessment AS Assessment, nursing_intervention AS Intervention,
                response_evaluation AS Response, communication_escalation AS Communication,
                nurse_name AS Staff, created_utc AS 'Saved UTC'
                FROM progress_notes WHERE admission_id=? ORDER BY note_date DESC, note_time DESC, id DESC""", (admission_id,)),
        ]
        for tab, (name, sql, params) in zip(history_tabs, history_queries):
            with tab:
                rows = fetchall(sql, params)
                if rows:
                    # Render additional admission JSON as a readable object in its own expander.
                    row_dicts = [dict(r) for r in rows]
                    if name == "Admission":
                        for item in row_dicts:
                            raw = item.get("Additional details")
                            if raw:
                                try:
                                    item["Additional details"] = json.dumps(json.loads(raw), ensure_ascii=False, indent=2)
                                except (TypeError, json.JSONDecodeError):
                                    pass
                    df = pd.DataFrame(row_dicts)
                    st.dataframe(df, use_container_width=True, hide_index=True)
                    st.download_button(
                        f"Export {name} as CSV",
                        df.to_csv(index=False).encode("utf-8-sig"),
                        file_name=f"admission_{admission_id}_{name.lower().replace(' ', '_')}.csv",
                        mime="text/csv",
                        key=f"export_{name}_{admission_id}",
                    )
                else:
                    st.info(f"No {name.lower()} records have been saved for this admission.")

st.divider()
st.caption(
    "Every form starts blank. Enter only verified observations and information from the clinical record. "
    "This prototype is not a substitute for the hospital's approved charting system."
)
