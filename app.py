"""
CHANIE v3.1
Comprehensive Healthcare Application for Neonatal Insights & Evaluation.

Educational prototype, not a validated EHR.
Do not store identifiable patient data until institutional security, privacy,
clinical governance, disaster recovery, and validation requirements are met.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import math
import os
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

APP_VERSION = "3.1.0"
APP_TITLE = "CHANIE | Neonatal Insights & Evaluation"
DB_PATH = Path(os.environ.get(
    "CHANIE_DB_PATH",
    str(Path(__file__).with_name("today_nurse_nicu.db"))
)).expanduser().resolve()
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

PBKDF2_ITERATIONS = 600_000
SESSION_IDLE_MINUTES = 20
MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_MINUTES = 15
ROLES = ("admin", "clinician", "nurse", "viewer")
EXPORT_ROLES = {"admin", "clinician"}
WRITE_ROLES = {"admin", "clinician", "nurse"}

st.set_page_config(page_title=APP_TITLE, page_icon="🩺", layout="wide")


# ----------------------------- Utilities ------------------------------------
def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def clean(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, str):
        return value.strip() or None
    return value


def valid_number(label: str, value: Any, low: float, high: float,
                 *, required: bool = False) -> float | None:
    if value is None:
        if required:
            raise ValueError(f"{label} is required.")
        return None
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be numeric.") from exc
    if not math.isfinite(number) or not low <= number <= high:
        raise ValueError(f"{label} must be between {low:g} and {high:g}.")
    return number


def staff_required(value: str) -> str:
    result = (value or "").strip()
    if not result:
        raise ValueError("Authenticated staff identity is required.")
    return result


def parse_local_interval(record_date: date, start: time, end: time):
    """Prototype assumes one configured facility timezone and stores ISO local wall time.
    Production deployments must configure a named timezone and migrate to aware timestamps.
    """
    start_dt = datetime.combine(record_date, start.replace(second=0, microsecond=0))
    end_dt = datetime.combine(record_date, end.replace(second=0, microsecond=0))
    if end_dt == start_dt:
        raise ValueError("Interval start and end cannot be identical.")
    if end_dt < start_dt:
        end_dt += timedelta(days=1)
    hours = (end_dt - start_dt).total_seconds() / 3600
    if not 0 < hours <= 48:
        raise ValueError("Interval duration must be greater than zero and no more than 48 hours.")
    return start_dt, end_dt, hours


def pbkdf2_hash(password: str, *, salt: bytes | None = None,
                iterations: int = PBKDF2_ITERATIONS) -> str:
    if len(password) < 12:
        raise ValueError("Password must contain at least 12 characters.")
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"pbkdf2_sha256${iterations}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, iter_s, salt_hex, digest_hex = stored.split("$", 3)
        if scheme != "pbkdf2_sha256":
            return False
        iterations = int(iter_s)
        if iterations < 100_000 or iterations > 2_000_000:
            return False
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
        supplied = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
        return hmac.compare_digest(supplied, expected)
    except (ValueError, TypeError):
        return False


@contextmanager
def db():
    conn = sqlite3.connect(DB_PATH, timeout=30, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=FULL")
    try:
        yield conn
    finally:
        conn.close()


def columns_for(conn: sqlite3.Connection, table: str) -> set[str]:
    return {r["name"] for r in conn.execute(f'PRAGMA table_info("{table}")').fetchall()}


def ensure_column(conn: sqlite3.Connection, table: str, name: str, typ: str) -> None:
    if name not in columns_for(conn, table):
        conn.execute(f'ALTER TABLE "{table}" ADD COLUMN "{name}" {typ}')


def audit_in_transaction(conn: sqlite3.Connection, actor: str, action: str,
                         entity_type: str, entity_id: int | None = None,
                         detail: str | None = None) -> None:
    """Append audit event inside the caller's transaction; failure rolls back record too."""
    previous = conn.execute(
        "SELECT event_hash FROM audit_events ORDER BY id DESC LIMIT 1"
    ).fetchone()
    previous_hash = previous["event_hash"] if previous else "GENESIS"
    event = {
        "event_utc": utc_now(), "actor": actor[:120], "action": action[:80],
        "entity_type": entity_type[:80], "entity_id": entity_id,
        "detail": (detail or "")[:1000], "previous_hash": previous_hash,
    }
    canonical = json.dumps(event, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    event_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    conn.execute(
        """INSERT INTO audit_events(event_utc,actor,action,entity_type,entity_id,
           detail,previous_hash,event_hash) VALUES(?,?,?,?,?,?,?,?)""",
        (event["event_utc"], event["actor"], event["action"], event["entity_type"],
         entity_id, event["detail"], previous_hash, event_hash),
    )


def insert_record(sql: str, params: tuple, actor: str, entity: str,
                  detail: str | None = None) -> int:
    with db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        cur = conn.execute(sql, params)
        record_id = int(cur.lastrowid)
        audit_in_transaction(conn, actor, "CREATE", entity, record_id, detail)
        conn.commit()
        return record_id


def update_record(sql: str, params: tuple, actor: str, entity: str,
                  entity_id: int, action: str, detail: str | None = None) -> int:
    with db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        cur = conn.execute(sql, params)
        if cur.rowcount != 1:
            conn.rollback()
            raise ValueError("Record was not changed. Refresh and verify its current status.")
        audit_in_transaction(conn, actor, action, entity, entity_id, detail)
        conn.commit()
        return int(cur.rowcount)


def rows(sql: str, params: tuple = ()) -> list[sqlite3.Row]:
    with db() as conn:
        return conn.execute(sql, params).fetchall()


def scalar(sql: str, params: tuple = ()) -> int:
    result = rows(sql, params)
    return int(result[0][0]) if result else 0


def csv_export(records: list[sqlite3.Row], filename: str, key: str,
               role: str, *, sensitive: bool = False) -> None:
    if not records:
        st.info("No records available.")
        return
    if role not in EXPORT_ROLES:
        st.info("CSV export is restricted to admin and clinician roles.")
        return
    frame = pd.DataFrame([dict(r) for r in records])
    st.dataframe(frame, use_container_width=True, hide_index=True)
    st.download_button(
        "Export CSV", frame.to_csv(index=False).encode("utf-8-sig"),
        filename, "text/csv", key=key,
    )


def notify_error(fn) -> None:
    try:
        fn()
    except (ValueError, sqlite3.IntegrityError) as exc:
        st.error(str(exc))
    except sqlite3.Error:
        st.error("The operation failed and was rolled back where transactional. Check server logs before retrying.")


# ----------------------------- Database -------------------------------------
def init_db() -> None:
    with db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
          username TEXT PRIMARY KEY, password_hash TEXT NOT NULL,
          role TEXT NOT NULL CHECK(role IN ('admin','clinician','nurse','viewer')),
          active INTEGER NOT NULL DEFAULT 1, created_utc TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS login_attempts (
          username TEXT PRIMARY KEY, failed_count INTEGER NOT NULL DEFAULT 0,
          locked_until_utc TEXT
        );
        CREATE TABLE IF NOT EXISTS patients (
          id INTEGER PRIMARY KEY, hospital_patient_id TEXT NOT NULL UNIQUE,
          patient_label TEXT NOT NULL, date_of_birth TEXT, sex TEXT,
          residential_address TEXT, guardian_name TEXT, guardian_relationship TEXT,
          primary_contact_phone TEXT, alternate_contact_phone TEXT, contact_email TEXT,
          created_utc TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS admissions (
          id INTEGER PRIMARY KEY, patient_id INTEGER NOT NULL REFERENCES patients(id),
          admission_date TEXT NOT NULL, admission_time TEXT NOT NULL,
          gestational_age_weeks INTEGER, gestational_age_days INTEGER,
          birth_weight_g REAL, admission_weight_g REAL, delivery_mode TEXT,
          apgar_1 TEXT, apgar_5 TEXT, referring_facility TEXT, admission_reason TEXT NOT NULL,
          maternal_perinatal_history TEXT, resuscitation TEXT, initial_condition TEXT,
          respiratory_support TEXT, oxygen_or_support_settings TEXT, lines_devices TEXT,
          allergies TEXT, infection_risk TEXT, initial_nursing_assessment TEXT,
          nursing_priorities TEXT, admitting_clinician TEXT, admitting_nurse TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'Active' CHECK(status IN ('Active','Closed')),
          discharge_date TEXT, discharge_time TEXT, discharge_summary TEXT,
          admission_record_json TEXT, created_utc TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS observations (
          id INTEGER PRIMARY KEY, admission_id INTEGER NOT NULL REFERENCES admissions(id),
          observation_date TEXT NOT NULL, observation_time TEXT NOT NULL,
          heart_rate REAL, respiratory_rate REAL, temperature_c REAL, spo2_percent REAL,
          fio2_percent REAL, blood_pressure TEXT, pain_score TEXT, respiratory_support TEXT,
          support_settings TEXT, capillary_refill TEXT, nurse_name TEXT NOT NULL, note TEXT,
          created_utc TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS assessments (
          id INTEGER PRIMARY KEY, admission_id INTEGER NOT NULL REFERENCES admissions(id),
          assessment_date TEXT NOT NULL, assessment_time TEXT NOT NULL, assessment_type TEXT NOT NULL,
          neurological TEXT, respiratory TEXT, cardiovascular TEXT, thermoregulation_skin TEXT,
          gastrointestinal_feeding TEXT, genitourinary TEXT, musculoskeletal TEXT, pain_comfort TEXT,
          lines_tubes_devices TEXT, infection_risk TEXT, developmental_family_care TEXT,
          findings_interventions TEXT, escalation_actions TEXT, nurse_name TEXT NOT NULL, created_utc TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS fluid_records (
          id INTEGER PRIMARY KEY, admission_id INTEGER NOT NULL REFERENCES admissions(id),
          record_date TEXT NOT NULL, interval_start TEXT NOT NULL, interval_end TEXT NOT NULL,
          interval_start_utc TEXT, interval_end_utc TEXT, duration_hours REAL,
          weight_g REAL NOT NULL, iv_ml REAL NOT NULL, feeds_ml REAL NOT NULL,
          medication_ml REAL NOT NULL, blood_products_ml REAL NOT NULL, other_intake_ml REAL NOT NULL,
          urine_ml REAL NOT NULL, stool_count INTEGER NOT NULL, emesis_ml REAL NOT NULL,
          drains_ml REAL NOT NULL, other_output_ml REAL NOT NULL, total_intake_ml REAL NOT NULL,
          total_output_ml REAL NOT NULL, net_balance_ml REAL NOT NULL, urine_output_ml_kg_hr REAL NOT NULL,
          nurse_name TEXT NOT NULL, notes TEXT, created_utc TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS medication_records (
          id INTEGER PRIMARY KEY, admission_id INTEGER NOT NULL REFERENCES admissions(id),
          record_date TEXT NOT NULL, medication_name TEXT NOT NULL, prescribed_dose TEXT NOT NULL,
          route TEXT NOT NULL, frequency TEXT, scheduled_time TEXT, status TEXT NOT NULL,
          actual_administration_time TEXT, weight_used_g REAL, allergy_check TEXT NOT NULL,
          double_check TEXT, nurse_name TEXT NOT NULL, indication TEXT,
          withheld_or_omitted_reason TEXT, response_or_notes TEXT, created_utc TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS equipment_checks (
          id INTEGER PRIMARY KEY, admission_id INTEGER NOT NULL REFERENCES admissions(id),
          check_date TEXT NOT NULL, check_time TEXT NOT NULL, equipment_type TEXT NOT NULL,
          equipment_identifier TEXT, assigned_patient_confirmed TEXT NOT NULL,
          physical_condition TEXT NOT NULL, function_check TEXT NOT NULL, alarm_check TEXT,
          power_gas_check TEXT, consumables_check TEXT, cleaning_status TEXT, fault_or_issue TEXT,
          action_taken TEXT, escalation_or_ticket TEXT, outgoing_staff TEXT, incoming_staff TEXT,
          nurse_name TEXT NOT NULL, notes TEXT, created_utc TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS handovers (
          id INTEGER PRIMARY KEY, admission_id INTEGER NOT NULL REFERENCES admissions(id),
          handover_date TEXT NOT NULL, handover_time TEXT NOT NULL, shift TEXT NOT NULL,
          outgoing_nurse TEXT NOT NULL, incoming_nurse TEXT NOT NULL, situation TEXT NOT NULL,
          background TEXT, assessment_summary TEXT, recommendations TEXT, airway_respiratory TEXT,
          fluids_feeding_elimination TEXT, medication_due_or_pending TEXT, lines_devices_equipment TEXT,
          investigations_pending TEXT, safety_concerns TEXT, escalation_plan TEXT, acknowledgement TEXT,
          created_utc TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS nursing_care_plans (
          id INTEGER PRIMARY KEY, admission_id INTEGER NOT NULL REFERENCES admissions(id),
          plan_date TEXT NOT NULL, review_date TEXT, priority TEXT NOT NULL, status TEXT NOT NULL,
          problem_or_diagnosis TEXT NOT NULL, assessment_cues TEXT, goals_outcomes TEXT NOT NULL,
          interventions TEXT NOT NULL, frequency_or_schedule TEXT, implementation_notes TEXT,
          evaluation TEXT, evaluation_status TEXT NOT NULL, escalation_or_communication TEXT,
          nurse_name TEXT NOT NULL, reviewer_name TEXT, created_utc TEXT NOT NULL, updated_utc TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS progress_notes (
          id INTEGER PRIMARY KEY, admission_id INTEGER NOT NULL REFERENCES admissions(id),
          note_date TEXT NOT NULL, note_time TEXT NOT NULL, note_type TEXT NOT NULL,
          assessment TEXT, nursing_intervention TEXT, response_evaluation TEXT,
          communication_escalation TEXT, nurse_name TEXT NOT NULL, created_utc TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS audit_events (
          id INTEGER PRIMARY KEY, event_utc TEXT NOT NULL, actor TEXT NOT NULL,
          action TEXT NOT NULL, entity_type TEXT NOT NULL, entity_id INTEGER,
          detail TEXT, previous_hash TEXT, event_hash TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_admissions_patient_status ON admissions(patient_id,status);
        CREATE INDEX IF NOT EXISTS idx_obs_admission_date ON observations(admission_id,observation_date,observation_time);
        CREATE INDEX IF NOT EXISTS idx_fluid_admission_date ON fluid_records(admission_id,record_date);
        CREATE INDEX IF NOT EXISTS idx_notes_admission_date ON progress_notes(admission_id,note_date,note_time);
        """)
        # Safe additive upgrades for existing prototype databases.
        upgrades = {
            "patients": {"residential_address":"TEXT", "guardian_name":"TEXT",
                "guardian_relationship":"TEXT", "primary_contact_phone":"TEXT",
                "alternate_contact_phone":"TEXT", "contact_email":"TEXT"},
            "admissions": {"status":"TEXT NOT NULL DEFAULT 'Active'", "discharge_date":"TEXT",
                "discharge_time":"TEXT", "discharge_summary":"TEXT", "admission_record_json":"TEXT"},
            "fluid_records": {"interval_start_utc":"TEXT", "interval_end_utc":"TEXT",
                "duration_hours":"REAL"},
        }
        for table, additions in upgrades.items():
            for name, typ in additions.items():
                ensure_column(conn, table, name, typ)

        # Prevent concurrent duplicate active admissions. Existing duplicates must be reconciled first.
        duplicates = conn.execute(
            "SELECT patient_id, COUNT(*) n FROM admissions WHERE status='Active' GROUP BY patient_id HAVING COUNT(*)>1"
        ).fetchall()
        if not duplicates:
            conn.execute("""
              CREATE UNIQUE INDEX IF NOT EXISTS uq_one_active_admission
              ON admissions(patient_id) WHERE status='Active'
            """)


def verify_audit_chain() -> tuple[bool, int, str | None]:
    events = rows("SELECT id,event_utc,actor,action,entity_type,entity_id,detail,previous_hash,event_hash FROM audit_events ORDER BY id")
    previous = "GENESIS"
    for event in events:
        canonical_event = {
            "event_utc": event["event_utc"], "actor": event["actor"],
            "action": event["action"], "entity_type": event["entity_type"],
            "entity_id": event["entity_id"], "detail": event["detail"],
            "previous_hash": event["previous_hash"],
        }
        canonical = json.dumps(canonical_event, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        expected = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        if event["previous_hash"] != previous or not hmac.compare_digest(expected, event["event_hash"]):
            return False, int(event["id"]), "Hash or previous-link mismatch"
        previous = event["event_hash"]
    return True, len(events), None


# ----------------------------- Authentication -------------------------------
def login() -> tuple[str, str] | None:
    st.title("🩺 CHANIE")
    st.subheader("Comprehensive Healthcare Application for Neonatal Insights & Evaluation")
    st.caption("Educational prototype. Authentication is fail-closed; no default/demo account exists.")
    if not scalar("SELECT COUNT(*) FROM users"):
        st.error("No user accounts exist. Create the first administrator using setup_chanie_user.py.")
        st.code("python setup_chanie_user.py", language="bash")
        st.stop()

    with st.form("login_form"):
        username = st.text_input("Username").strip()
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Sign in")
    if submitted:
        normalized = username[:120]
        attempt = rows("SELECT failed_count,locked_until_utc FROM login_attempts WHERE username=?", (normalized,))
        if attempt and attempt[0]["locked_until_utc"]:
            try:
                locked_until = datetime.fromisoformat(attempt[0]["locked_until_utc"])
            except ValueError:
                locked_until = datetime.now(timezone.utc) + timedelta(minutes=LOCKOUT_MINUTES)
            if locked_until > datetime.now(timezone.utc):
                st.error("Sign-in temporarily locked after repeated failures. Try again later.")
                return None
        account = rows("SELECT username,password_hash,role,active FROM users WHERE username=?", (normalized,))
        valid = bool(account and account[0]["active"] and verify_password(password, account[0]["password_hash"]))
        if valid:
            with db() as conn:
                conn.execute("BEGIN IMMEDIATE")
                conn.execute("DELETE FROM login_attempts WHERE username=?", (normalized,))
                audit_in_transaction(conn, normalized, "LOGIN", "session", None, "Successful login")
                conn.commit()
            st.session_state["actor"] = account[0]["username"]
            st.session_state["role"] = account[0]["role"]
            st.session_state["last_activity"] = utc_now()
            st.rerun()
        else:
            with db() as conn:
                conn.execute("BEGIN IMMEDIATE")
                old = conn.execute("SELECT failed_count FROM login_attempts WHERE username=?", (normalized,)).fetchone()
                count = (int(old["failed_count"]) if old else 0) + 1
                lock_until = (datetime.now(timezone.utc) + timedelta(minutes=LOCKOUT_MINUTES)).isoformat() if count >= MAX_LOGIN_ATTEMPTS else None
                conn.execute("""INSERT INTO login_attempts(username,failed_count,locked_until_utc) VALUES(?,?,?)
                    ON CONFLICT(username) DO UPDATE SET failed_count=excluded.failed_count,locked_until_utc=excluded.locked_until_utc""",
                    (normalized, count, lock_until))
                audit_in_transaction(conn, normalized or "unknown", "LOGIN_FAILED", "session", None, "Invalid credentials")
                conn.commit()
            st.error("Invalid credentials or inactive account.")
    st.info("Use individual accounts. For any real clinical deployment, prefer institutional SSO/MFA, centralized authorization, and protected audit logging.")
    return None


def current_identity() -> tuple[str, str]:
    actor = st.session_state.get("actor")
    role = st.session_state.get("role")
    last = st.session_state.get("last_activity")
    if not actor or role not in ROLES or not last:
        for key in ("actor", "role", "last_activity"):
            st.session_state.pop(key, None)
        return ("", "")
    try:
        last_dt = datetime.fromisoformat(last)
    except (ValueError, TypeError):
        last_dt = datetime.now(timezone.utc) - timedelta(days=1)
    if datetime.now(timezone.utc) - last_dt > timedelta(minutes=SESSION_IDLE_MINUTES):
        for key in ("actor", "role", "last_activity"):
            st.session_state.pop(key, None)
        st.warning("Your session expired due to inactivity. Sign in again.")
        return ("", "")
    st.session_state["last_activity"] = utc_now()
    return actor, role


def require_write(role: str) -> None:
    if role not in WRITE_ROLES:
        raise ValueError("Your account role does not permit clinical-record changes.")


# ----------------------------- App start ------------------------------------
init_db()
if not st.session_state.get("actor"):
    login()
    st.stop()

actor, role = current_identity()
if not actor:
    st.rerun()

st.title("🩺 CHANIE")
st.subheader("Comprehensive Healthcare Application for Neonatal Insights & Evaluation")
st.caption(f"Educational prototype · Version {APP_VERSION} · Role: {role}")
st.warning(
    "PROTOTYPE SAFETY NOTICE: not a validated EHR. Use fictional data only until institutional "
    "security, privacy, clinical governance, backup/restore, and clinical validation requirements are met. "
    "SQLite/WAL is not a complete production hosting or encryption solution."
)

with st.sidebar:
    st.header("Patient / admission")
    active = rows("""SELECT a.id,p.hospital_patient_id,p.patient_label,a.admission_date,a.admission_reason
        FROM admissions a JOIN patients p ON p.id=a.patient_id WHERE a.status='Active'
        ORDER BY a.admission_date DESC,a.id DESC""")
    label_map = {
        f"{r['hospital_patient_id']} · {r['patient_label']} · Episode #{r['id']} · {r['admission_date']}": r["id"]
        for r in active
    }
    selected_label = st.selectbox("Active admission", list(label_map)) if label_map else None
    admission_id = label_map.get(selected_label) if selected_label else None
    default_date = st.date_input("Default record date", value=date.today(), key="global_record_date")
    st.divider()
    st.caption(f"Signed in: {actor} · {role}")
    if st.button("Log out"):
        with db() as conn:
            conn.execute("BEGIN IMMEDIATE")
            audit_in_transaction(conn, actor, "LOGOUT", "session", None, "User logged out")
            conn.commit()
        for key in ("actor", "role", "last_activity"):
            st.session_state.pop(key, None)
        st.rerun()

if role == "admin":
    with st.sidebar.expander("User administration"):
        st.caption("Create/manage users through setup_chanie_user.py; this prototype does not expose password reset UI.")
        user_rows = rows("SELECT username,role,active,created_utc FROM users ORDER BY username")
        if user_rows:
            st.dataframe(pd.DataFrame([dict(r) for r in user_rows]), use_container_width=True, hide_index=True)

tabs = st.tabs([
    "Dashboard", "Patient registry", "Initial admission", "Assessment",
    "Vital signs", "Fluid balance", "Medication", "Equipment",
    "Shift handover", "Care plan", "Progress notes & history", "Audit integrity"
])

# Dashboard
with tabs[0]:
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Registered patients", scalar("SELECT COUNT(*) FROM patients"))
    c2.metric("Active admissions", scalar("SELECT COUNT(*) FROM admissions WHERE status='Active'"))
    c3.metric("Today's observations", scalar("SELECT COUNT(*) FROM observations WHERE observation_date=?", (date.today().isoformat(),)))
    c4.metric("Care plans due for review", scalar("SELECT COUNT(*) FROM nursing_care_plans WHERE status='Active' AND review_date IS NOT NULL AND review_date<=?", (date.today().isoformat(),)))
    st.subheader("Active admissions")
    dash = rows("""SELECT p.hospital_patient_id AS 'Patient ID',p.patient_label AS Patient,
        a.id AS Episode,a.admission_date AS 'Admission date',a.admission_reason AS 'Admission reason',
        a.gestational_age_weeks AS 'GA weeks',a.gestational_age_days AS 'GA days',a.status AS Status
        FROM admissions a JOIN patients p ON p.id=a.patient_id WHERE a.status='Active'
        ORDER BY a.admission_date DESC,a.id DESC""")
    if dash:
        st.dataframe(pd.DataFrame([dict(r) for r in dash]), use_container_width=True, hide_index=True)
    else:
        st.info("No active admissions. Register a patient, then create an admission.")
    st.subheader("Recent activity")
    activity = rows("SELECT event_utc AS UTC,actor AS Staff,action AS Action,entity_type AS Record,entity_id AS 'Record ID',detail AS Details FROM audit_events ORDER BY id DESC LIMIT 20")
    if activity:
        st.dataframe(pd.DataFrame([dict(r) for r in activity]), use_container_width=True, hide_index=True)
    st.caption("Counts are operational summaries, not clinical decision support.")

# Patient registry
with tabs[1]:
    st.subheader("Patient registry")
    if role in WRITE_ROLES:
        with st.form("patient_registration", clear_on_submit=True):
            c1, c2 = st.columns(2)
            with c1:
                mrn = st.text_input("Hospital record number *")
                patient_label = st.text_input("Approved patient label *")
                dob = st.date_input("Date of birth (optional)", value=None, min_value=date(1990, 1, 1), max_value=date.today())
                sex = st.selectbox("Sex", ["Not recorded", "Female", "Male", "Indeterminate / not yet assigned", "Other / per policy"])
                address = st.text_area("Residential address (optional)")
            with c2:
                guardian = st.text_input("Parent / guardian")
                relationship = st.selectbox("Relationship", ["Not recorded", "Mother", "Father", "Legal guardian", "Other"])
                phone = st.text_input("Primary contact")
                alt_phone = st.text_input("Alternate contact")
                email = st.text_input("Email (optional)")
            submit = st.form_submit_button("Register patient")
        if submit:
            def save_patient():
                require_write(role)
                if not mrn.strip() or not patient_label.strip():
                    raise ValueError("Hospital record number and patient label are required.")
                if dob and dob > date.today():
                    raise ValueError("Date of birth cannot be in the future.")
                if email.strip() and ("@" not in email or "." not in email.rsplit("@", 1)[-1]):
                    raise ValueError("Enter a valid email or leave it blank.")
                pid = insert_record(
                    """INSERT INTO patients(hospital_patient_id,patient_label,date_of_birth,sex,
                    residential_address,guardian_name,guardian_relationship,primary_contact_phone,
                    alternate_contact_phone,contact_email,created_utc) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                    (mrn.strip(), patient_label.strip(), dob.isoformat() if dob else None,
                     None if sex == "Not recorded" else sex, clean(address), clean(guardian),
                     None if relationship == "Not recorded" else relationship, clean(phone),
                     clean(alt_phone), clean(email), utc_now()),
                    actor, "patient", "Patient registration"
                )
                st.success(f"Patient registered (internal ID {pid}).")
                st.rerun()
            notify_error(save_patient)
    patient_rows = rows("""SELECT id,hospital_patient_id AS MRN,patient_label AS Patient,
        date_of_birth AS DOB,sex AS Sex,guardian_name AS Guardian,guardian_relationship AS Relationship,
        primary_contact_phone AS Phone,alternate_contact_phone AS 'Alternate phone',
        contact_email AS Email,residential_address AS Address,created_utc AS 'Created UTC'
        FROM patients ORDER BY patient_label""")
    csv_export(patient_rows, "chanie_patients.csv", "export_patients", role, sensitive=True)

# Admission
with tabs[2]:
    st.subheader("Initial NICU admission")
    patients = rows("SELECT id,hospital_patient_id,patient_label FROM patients ORDER BY patient_label")
    if not patients:
        st.info("Register a patient first.")
    elif role in WRITE_ROLES:
        pmap = {f"{r['hospital_patient_id']} · {r['patient_label']}": r["id"] for r in patients}
        with st.form("admission_form", clear_on_submit=True):
            pkey = st.selectbox("Patient *", list(pmap))
            c1, c2, c3 = st.columns(3)
            with c1:
                adm_date = st.date_input("Admission date", value=default_date, key="adm_date")
                adm_time = st.time_input("Admission time", value=datetime.now().time().replace(second=0, microsecond=0), key="adm_time")
                ga_w = st.number_input("Gestational age, completed weeks", min_value=0, max_value=45, value=0)
                ga_d = st.number_input("Additional days", min_value=0, max_value=6, value=0)
                birth_w = st.number_input("Birth weight (g, 0 = not recorded)", min_value=0.0, max_value=10000.0, value=0.0, step=10.0)
                adm_w = st.number_input("Admission weight (g, 0 = not recorded)", min_value=0.0, max_value=10000.0, value=0.0, step=10.0)
            with c2:
                delivery = st.selectbox("Delivery mode", ["Not documented", "Spontaneous vaginal", "Assisted vaginal", "Caesarean section", "Other / unknown"])
                apgar1 = st.text_input("Apgar at 1 minute")
                apgar5 = st.text_input("Apgar at 5 minutes")
                referring = st.text_input("Referring facility")
                reason = st.text_area("Reason for admission *")
                resuscitation = st.text_area("Resuscitation / stabilization")
            with c3:
                condition = st.text_area("Condition on arrival")
                maternal = st.text_area("Maternal / perinatal history")
                support = st.selectbox("Respiratory support", ["Not documented", "Room air", "Low-flow oxygen", "HFNC", "CPAP", "NIPPV", "Mechanical ventilation", "Other"])
                settings = st.text_area("Support settings")
            lines = st.text_area("Lines / tubes / devices")
            allergies = st.text_area("Allergies / verification status")
            infection = st.text_area("Infection risk / precautions")
            assessment = st.text_area("Initial nursing assessment")
            priorities = st.text_area("Initial nursing priorities")
            extra = st.text_area("Additional local admission details")
            clinician = st.text_input("Admitting clinician")
            adm_nurse = st.text_input("Admitting nurse / staff ID *")
            submit = st.form_submit_button("Save admission")
        if submit:
            def save_admission():
                require_write(role)
                staff = staff_required(adm_nurse)
                if not reason.strip():
                    raise ValueError("Admission reason is required.")
                if ga_w == 0 and ga_d != 0:
                    raise ValueError("Enter completed gestational weeks before additional days.")
                if adm_date > date.today():
                    raise ValueError("Admission date cannot be in the future.")
                bw = valid_number("Birth weight", birth_w, 0, 10000)
                aw = valid_number("Admission weight", adm_w, 0, 10000)
                aid = insert_record(
                    """INSERT INTO admissions(patient_id,admission_date,admission_time,
                    gestational_age_weeks,gestational_age_days,birth_weight_g,admission_weight_g,
                    delivery_mode,apgar_1,apgar_5,referring_facility,admission_reason,
                    maternal_perinatal_history,resuscitation,initial_condition,respiratory_support,
                    oxygen_or_support_settings,lines_devices,allergies,infection_risk,
                    initial_nursing_assessment,nursing_priorities,admitting_clinician,admitting_nurse,
                    status,admission_record_json,created_utc)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (pmap[pkey], adm_date.isoformat(), adm_time.strftime("%H:%M"),
                     int(ga_w) if ga_w else None, int(ga_d), bw or None, aw or None, delivery,
                     clean(apgar1), clean(apgar5), clean(referring), reason.strip(), clean(maternal),
                     clean(resuscitation), clean(condition), support, clean(settings), clean(lines),
                     clean(allergies), clean(infection), clean(assessment), clean(priorities),
                     clean(clinician), staff, "Active",
                     json.dumps({"additional_details": clean(extra)}, ensure_ascii=False), utc_now()),
                    actor, "admission", f"Patient internal ID {pmap[pkey]}"
                )
                st.success(f"Admission episode #{aid} saved.")
                st.rerun()
            notify_error(save_admission)
    st.divider()
    st.subheader("Close an admission")
    open_adms = rows("""SELECT a.id,p.hospital_patient_id,p.patient_label,a.admission_date
        FROM admissions a JOIN patients p ON p.id=a.patient_id
        WHERE a.status='Active' ORDER BY a.id DESC""")
    if open_adms and role in WRITE_ROLES:
        amap = {f"Episode #{r['id']} · {r['hospital_patient_id']} · {r['patient_label']} · {r['admission_date']}": r["id"] for r in open_adms}
        with st.form("discharge_form"):
            discharge_key = st.selectbox("Active episode", list(amap))
            dc_date = st.date_input("Discharge / transfer date", value=date.today(), key="dc_date")
            dc_time = st.time_input("Discharge / transfer time", value=datetime.now().time().replace(second=0, microsecond=0), key="dc_time")
            dc_summary = st.text_area("Discharge / transfer summary *")
            confirm_dc = st.checkbox("I verified the episode and approved disposition.")
            submit_dc = st.form_submit_button("Close admission")
        if submit_dc:
            def close_admission():
                require_write(role)
                if not confirm_dc or not dc_summary.strip():
                    raise ValueError("Confirmation and a discharge/transfer summary are required.")
                if dc_date > date.today():
                    raise ValueError("Discharge date cannot be in the future.")
                aid = amap[discharge_key]
                update_record(
                    "UPDATE admissions SET status='Closed',discharge_date=?,discharge_time=?,discharge_summary=? WHERE id=? AND status='Active'",
                    (dc_date.isoformat(), dc_time.strftime("%H:%M"), dc_summary.strip(), aid),
                    actor, "admission", aid, "CLOSE_ADMISSION", "Admission closed"
                )
                st.success("Admission closed.")
                st.rerun()
            notify_error(close_admission)
    elif not open_adms:
        st.caption("No active episodes to close.")

context = rows("""SELECT a.*,p.hospital_patient_id,p.patient_label FROM admissions a
    JOIN patients p ON p.id=a.patient_id WHERE a.id=? AND a.status='Active'""", (admission_id,)) if admission_id else []
if not context:
    for idx in range(3, 11):
        with tabs[idx]:
            st.info("Select an active admission in the sidebar. If none exists, register a patient and create an admission.")
else:
    current = context[0]
    with st.sidebar:
        st.markdown(f"**Selected:** {current['patient_label']}")
        st.caption(f"Record number: {current['hospital_patient_id']} · Episode #{admission_id}")

    # Assessment
    with tabs[3]:
        st.subheader("Head-to-toe assessment")
        if role in WRITE_ROLES:
            with st.form("assessment_form", clear_on_submit=True):
                d = st.date_input("Assessment date", value=default_date, key="assess_date")
                t = st.time_input("Assessment time", value=datetime.now().time().replace(second=0, microsecond=0), key="assess_time")
                atype = st.selectbox("Assessment type", ["Initial baseline", "Routine shift assessment", "Focused reassessment", "Post-intervention", "Other"])
                c1, c2, c3 = st.columns(3)
                with c1:
                    neuro = st.text_area("Neurological")
                    resp = st.text_area("Respiratory")
                with c2:
                    cardio = st.text_area("Cardiovascular")
                    skin = st.text_area("Thermoregulation / skin")
                    gi = st.text_area("GI / feeding / abdomen / stool")
                with c3:
                    gu = st.text_area("Genitourinary / output")
                    ms = st.text_area("Musculoskeletal")
                    pain = st.text_input("Pain tool and score")
                    devices = st.text_area("Lines / tubes / devices")
                    inf = st.text_area("Infection risks / precautions")
                    dev = st.text_area("Developmental care / family involvement")
                findings = st.text_area("Findings, interventions and evaluation")
                escalation = st.text_area("Escalation, person notified, time and response")
                submit = st.form_submit_button("Save assessment")
            if submit:
                def save_assessment():
                    require_write(role)
                    staff = staff_required(actor)
                    rid = insert_record(
                        """INSERT INTO assessments(admission_id,assessment_date,assessment_time,assessment_type,
                        neurological,respiratory,cardiovascular,thermoregulation_skin,gastrointestinal_feeding,
                        genitourinary,musculoskeletal,pain_comfort,lines_tubes_devices,infection_risk,
                        developmental_family_care,findings_interventions,escalation_actions,nurse_name,created_utc)
                        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (admission_id, d.isoformat(), t.strftime("%H:%M"), atype, clean(neuro),
                         clean(resp), clean(cardio), clean(skin), clean(gi), clean(gu), clean(ms),
                         clean(pain), clean(devices), clean(inf), clean(dev), clean(findings),
                         clean(escalation), staff, utc_now()), actor, "assessment"
                    )
                    st.success(f"Assessment #{rid} saved.")
                notify_error(save_assessment)
        result = rows("SELECT assessment_date AS Date,assessment_time AS Time,assessment_type AS Type,neurological AS Neurological,respiratory AS Respiratory,cardiovascular AS Cardiovascular,findings_interventions AS Findings,escalation_actions AS Escalation,nurse_name AS Staff FROM assessments WHERE admission_id=? ORDER BY assessment_date DESC,assessment_time DESC,id DESC LIMIT 50", (admission_id,))
        if result:
            st.dataframe(pd.DataFrame([dict(r) for r in result]), use_container_width=True, hide_index=True)

    # Vital signs
    with tabs[4]:
        st.subheader("Vital signs and monitoring")
        st.caption("Technical input limits are not clinical reference ranges. Use locally approved neonatal guidance.")
        if role in WRITE_ROLES:
            with st.form("observation_form", clear_on_submit=True):
                d = st.date_input("Observation date", value=default_date, key="obs_date")
                t = st.time_input("Observation time", value=datetime.now().time().replace(second=0, microsecond=0), key="obs_time")
                c1, c2, c3 = st.columns(3)
                with c1:
                    hr = st.number_input("Heart rate (bpm)", min_value=0.0, max_value=350.0, value=None, step=1.0)
                    rr = st.number_input("Respiratory rate (/min)", min_value=0.0, max_value=200.0, value=None, step=1.0)
                with c2:
                    temp = st.number_input("Temperature (°C)", min_value=20.0, max_value=45.0, value=None, step=0.1)
                    spo2 = st.number_input("SpO₂ (%)", min_value=0.0, max_value=100.0, value=None, step=1.0)
                    fio2 = st.number_input("FiO₂ (%)", min_value=21.0, max_value=100.0, value=None, step=1.0)
                with c3:
                    bp = st.text_input("Blood pressure with units/site")
                    pain = st.text_input("Pain tool / score")
                    support = st.selectbox("Respiratory support", ["Not documented", "Room air", "Oxygen", "HFNC", "CPAP", "NIPPV", "Mechanical ventilation", "Other"])
                    settings = st.text_input("Support settings / interface")
                crt = st.selectbox("Capillary refill", ["Not assessed", "Within locally expected range", "Delayed / abnormal", "Other / details in note"])
                note = st.text_area("Clinical note, action and escalation")
                submit = st.form_submit_button("Save observation")
            if submit:
                def save_observation():
                    require_write(role)
                    vals = [("Heart rate", hr, 0, 350), ("Respiratory rate", rr, 0, 200),
                            ("Temperature", temp, 20, 45), ("SpO₂", spo2, 0, 100), ("FiO₂", fio2, 21, 100)]
                    for label, val, low, high in vals:
                        valid_number(label, val, low, high)
                    if all(v is None for _, v, _, _ in vals) and not note.strip():
                        raise ValueError("Enter at least one measurement or a clinical note.")
                    rid = insert_record(
                        """INSERT INTO observations(admission_id,observation_date,observation_time,heart_rate,
                        respiratory_rate,temperature_c,spo2_percent,fio2_percent,blood_pressure,pain_score,
                        respiratory_support,support_settings,capillary_refill,nurse_name,note,created_utc)
                        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (admission_id, d.isoformat(), t.strftime("%H:%M"), hr, rr, temp, spo2, fio2,
                         clean(bp), clean(pain), support, clean(settings), crt, actor, clean(note), utc_now()),
                        actor, "observation"
                    )
                    st.success(f"Observation #{rid} saved.")
                notify_error(save_observation)
        recent = rows("SELECT observation_date AS Date,observation_time AS Time,heart_rate AS HR,respiratory_rate AS RR,temperature_c AS 'Temp °C',spo2_percent AS 'SpO₂ %',fio2_percent AS 'FiO₂ %',blood_pressure AS BP,respiratory_support AS Support,nurse_name AS Staff,note AS Note FROM observations WHERE admission_id=? ORDER BY observation_date DESC,observation_time DESC,id DESC LIMIT 50", (admission_id,))
        if recent:
            st.dataframe(pd.DataFrame([dict(r) for r in recent]), use_container_width=True, hide_index=True)

    # Fluid balance
    with tabs[5]:
        st.subheader("Fluid intake and output")
        st.caption("Measured values only. Stool count is not a volume and is excluded from total output. Urine rate is arithmetic only.")
        if role in WRITE_ROLES:
            with st.form("fluid_form", clear_on_submit=True):
                d = st.date_input("Interval start date", value=default_date, key="fluid_date")
                c1, c2, c3 = st.columns(3)
                with c1:
                    start = st.time_input("Interval start time", value=time(0, 0), key="fluid_start")
                    end = st.time_input("Interval end time", value=time(1, 0), key="fluid_end")
                    weight = st.number_input("Measured weight used (g) *", min_value=0.0, max_value=10000.0, value=None, step=10.0)
                    weight_time = st.date_input("Weight measurement date", value=default_date, key="fluid_weight_date")
                with c2:
                    iv = st.number_input("IV fluids (mL)", min_value=0.0, max_value=10000.0, value=None, step=0.5)
                    feeds = st.number_input("Enteral feeds (mL)", min_value=0.0, max_value=10000.0, value=None, step=0.5)
                    med = st.number_input("Medication fluid (mL)", min_value=0.0, max_value=10000.0, value=None, step=0.5)
                    blood = st.number_input("Blood products (mL)", min_value=0.0, max_value=10000.0, value=None, step=0.5)
                    other_in = st.number_input("Other intake (mL)", min_value=0.0, max_value=10000.0, value=None, step=0.5)
                with c3:
                    urine = st.number_input("Urine (mL)", min_value=0.0, max_value=10000.0, value=None, step=0.5)
                    stools = st.number_input("Stool count", min_value=0, max_value=100, value=None, step=1)
                    emesis = st.number_input("Emesis (mL)", min_value=0.0, max_value=10000.0, value=None, step=0.5)
                    drains = st.number_input("Drain output (mL)", min_value=0.0, max_value=10000.0, value=None, step=0.5)
                    other_out = st.number_input("Other output (mL)", min_value=0.0, max_value=10000.0, value=None, step=0.5)
                notes = st.text_area("Measurement notes / source")
                submit = st.form_submit_button("Calculate and save interval")
            if submit:
                def save_fluid():
                    require_write(role)
                    w = valid_number("Weight", weight, 1, 10000, required=True)
                    if weight_time > d:
                        raise ValueError("Weight measurement date cannot be after the interval start date.")
                    names = ["IV intake", "Feeds", "Medication fluid", "Blood products", "Other intake", "Urine", "Emesis", "Drain output", "Other output"]
                    raw = [iv, feeds, med, blood, other_in, urine, emesis, drains, other_out]
                    if any(v is None for v in raw) or stools is None:
                        raise ValueError("Complete all intake/output fields. Use 0 only when confirmed.")
                    vals = [valid_number(n, v, 0, 10000, required=True) for n, v in zip(names, raw)]
                    if not isinstance(stools, int) or stools < 0:
                        raise ValueError("Stool count must be a whole number of zero or more.")
                    start_dt, end_dt, hours = parse_local_interval(d, start, end)
                    # ISO local datetimes are intentionally not mislabeled as UTC. Legacy columns retain names.
                    start_iso, end_iso = start_dt.isoformat(), end_dt.isoformat()
                    total_in = sum(vals[:5])
                    total_out = vals[5] + vals[6] + vals[7] + vals[8]
                    net = total_in - total_out
                    urine_rate = vals[5] / (w / 1000.0) / hours
                    if not math.isfinite(urine_rate):
                        raise ValueError("Urine output calculation is invalid; verify weight and interval.")
                    existing = rows("SELECT id,interval_start,interval_end,interval_start_utc,interval_end_utc FROM fluid_records WHERE admission_id=?", (admission_id,))
                    for item in existing:
                        # Prefer old stored ISO values; fall back to legacy local date/time fields.
                        try:
                            old_start = datetime.fromisoformat(item["interval_start_utc"]) if item["interval_start_utc"] else None
                            old_end = datetime.fromisoformat(item["interval_end_utc"]) if item["interval_end_utc"] else None
                        except ValueError:
                            old_start = old_end = None
                        if old_start is None or old_end is None:
                            try:
                                old_start = datetime.fromisoformat(f"{item['record_date']}T{item['interval_start']}")
                                old_end = datetime.fromisoformat(f"{item['record_date']}T{item['interval_end']}")
                                if old_end <= old_start:
                                    old_end += timedelta(days=1)
                            except (ValueError, TypeError, KeyError):
                                continue
                        if old_start < end_dt and old_end > start_dt:
                            raise ValueError(f"Interval overlaps existing fluid record #{item['id']}. Review the chart before saving.")
                    with db() as conn:
                        conn.execute("BEGIN IMMEDIATE")
                        # Re-check overlap while holding the write lock to avoid concurrent double insertion.
                        items = conn.execute("SELECT id,record_date,interval_start,interval_end,interval_start_utc,interval_end_utc FROM fluid_records WHERE admission_id=?", (admission_id,)).fetchall()
                        for item in items:
                            try:
                                old_start = datetime.fromisoformat(item["interval_start_utc"]) if item["interval_start_utc"] else datetime.fromisoformat(f"{item['record_date']}T{item['interval_start']}")
                                old_end = datetime.fromisoformat(item["interval_end_utc"]) if item["interval_end_utc"] else datetime.fromisoformat(f"{item['record_date']}T{item['interval_end']}")
                                if old_end <= old_start:
                                    old_end += timedelta(days=1)
                            except (ValueError, TypeError):
                                continue
                            if old_start < end_dt and old_end > start_dt:
                                raise ValueError(f"Interval overlaps existing fluid record #{item['id']}.")
                        cur = conn.execute(
                            """INSERT INTO fluid_records(admission_id,record_date,interval_start,interval_end,
                            interval_start_utc,interval_end_utc,duration_hours,weight_g,iv_ml,feeds_ml,
                            medication_ml,blood_products_ml,other_intake_ml,urine_ml,stool_count,emesis_ml,
                            drains_ml,other_output_ml,total_intake_ml,total_output_ml,net_balance_ml,
                            urine_output_ml_kg_hr,nurse_name,notes,created_utc)
                            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                            (admission_id, d.isoformat(), start_dt.strftime("%H:%M"), end_dt.strftime("%H:%M"),
                             start_iso, end_iso, hours, w, *vals[:5], vals[5], stools, vals[6], vals[7],
                             vals[8], total_in, total_out, net, urine_rate, actor, clean(notes), utc_now())
                        )
                        rid = int(cur.lastrowid)
                        audit_in_transaction(conn, actor, "CREATE", "fluid_record", rid, f"Duration {hours:.2f} h")
                        conn.commit()
                    st.success(f"Fluid record #{rid} saved.")
                    a, b, c, e = st.columns(4)
                    a.metric("Duration", f"{hours:.2f} h")
                    b.metric("Total intake", f"{total_in:.2f} mL")
                    c.metric("Total output", f"{total_out:.2f} mL")
                    e.metric("Net balance", f"{net:.2f} mL")
                    st.metric("Calculated urine output", f"{urine_rate:.3f} mL/kg/hour",
                              help="Arithmetic result only. Clinical interpretation requires verified measurements and local guidance.")
                notify_error(save_fluid)
        fluids = rows("SELECT record_date AS 'Start date',interval_start AS Start,interval_end AS End,duration_hours AS 'Duration h',weight_g AS 'Weight g',total_intake_ml AS 'Intake mL',total_output_ml AS 'Output mL',net_balance_ml AS 'Net mL',urine_output_ml_kg_hr AS 'Urine mL/kg/h',nurse_name AS Staff,notes AS Notes FROM fluid_records WHERE admission_id=? ORDER BY record_date DESC,id DESC LIMIT 50", (admission_id,))
        if fluids:
            st.dataframe(pd.DataFrame([dict(r) for r in fluids]), use_container_width=True, hide_index=True)

    # Medication
    with tabs[6]:
        st.subheader("Medication administration record")
        st.warning("Document against a verified prescription and local neonatal medication policy. This app does not calculate or authorize doses.")
        if role in WRITE_ROLES:
            with st.form("med_form", clear_on_submit=True):
                c1, c2 = st.columns(2)
                with c1:
                    d = st.date_input("Record date", value=default_date, key="med_date")
                    name = st.text_input("Medication name as prescribed *")
                    dose = st.text_input("Prescribed dose and units *")
                    route = st.selectbox("Route", ["Select route", "Oral / enteral", "IV", "IM", "SC", "Inhaled / nebulized", "Topical", "Other / per prescription"])
                    freq = st.text_input("Frequency / schedule")
                    sched = st.text_input("Scheduled time (HH:MM or as prescribed)")
                    status = st.selectbox("Status", ["Administered", "Withheld", "Omitted / not given", "Delayed", "Refused", "Other"])
                with c2:
                    actual = st.text_input("Actual administration time (HH:MM)")
                    weight = st.number_input("Prescription reference weight (g, 0 = not recorded)", min_value=0.0, max_value=10000.0, value=0.0, step=10.0)
                    allergy = st.selectbox("Allergy status", ["Select status", "Checked; none known documented", "Known allergy reviewed", "Unable to verify; escalated", "Not applicable per policy"])
                    double = st.selectbox("Independent double-check", ["Not indicated by policy", "Completed per policy", "Required but not completed; escalated", "Not applicable / local policy"])
                    indication = st.text_input("Indication / prescription reference")
                reason = st.text_area("Reason if withheld / omitted / delayed")
                response = st.text_area("Response / adverse effects / monitoring")
                submit = st.form_submit_button("Save medication record")
            if submit:
                def save_med():
                    require_write(role)
                    if not name.strip() or not dose.strip() or route == "Select route":
                        raise ValueError("Medication, prescribed dose and route are required.")
                    if allergy == "Select status":
                        raise ValueError("Record allergy status.")
                    if status != "Administered" and not reason.strip():
                        raise ValueError("Document why the medication was not administered as scheduled.")
                    if status == "Administered" and not actual.strip():
                        raise ValueError("Enter actual administration time or choose the status that reflects what occurred.")
                    for value, label in ((actual, "Actual time"), (sched, "Scheduled time")):
                        if value.strip():
                            try:
                                datetime.strptime(value.strip(), "%H:%M")
                            except ValueError as exc:
                                raise ValueError(f"{label} must use HH:MM format or be blank.") from exc
                    w = valid_number("Prescription reference weight", weight, 0, 10000)
                    rid = insert_record(
                        """INSERT INTO medication_records(admission_id,record_date,medication_name,prescribed_dose,
                        route,frequency,scheduled_time,status,actual_administration_time,weight_used_g,
                        allergy_check,double_check,nurse_name,indication,withheld_or_omitted_reason,
                        response_or_notes,created_utc) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (admission_id, d.isoformat(), name.strip(), dose.strip(), route, clean(freq),
                         clean(sched), status, clean(actual), w or None, allergy, double, actor,
                         clean(indication), clean(reason), clean(response), utc_now()),
                        actor, "medication_record"
                    )
                    st.success(f"Medication record #{rid} saved.")
                notify_error(save_med)
        meds = rows("SELECT record_date AS Date,medication_name AS Medication,prescribed_dose AS Dose,route AS Route,status AS Status,scheduled_time AS Scheduled,actual_administration_time AS Actual,withheld_or_omitted_reason AS Reason,nurse_name AS Staff FROM medication_records WHERE admission_id=? ORDER BY record_date DESC,id DESC LIMIT 50", (admission_id,))
        if meds:
            st.dataframe(pd.DataFrame([dict(r) for r in meds]), use_container_width=True, hide_index=True)

    # Equipment
    with tabs[7]:
        st.subheader("Equipment safety check")
        if role in WRITE_ROLES:
            with st.form("equipment_form", clear_on_submit=True):
                d = st.date_input("Check date", value=default_date, key="eq_date")
                t = st.time_input("Check time", value=datetime.now().time().replace(second=0, microsecond=0), key="eq_time")
                c1, c2 = st.columns(2)
                with c1:
                    typ = st.selectbox("Equipment type", ["Incubator", "Radiant warmer", "Patient monitor", "CPAP / NIPPV", "Ventilator", "Oxygen delivery", "Suction", "Infusion pump", "Syringe pump", "Phototherapy", "Other"])
                    identifier = st.text_input("Asset identifier")
                    assigned = st.selectbox("Patient / equipment assignment", ["Select", "Verified", "Mismatch; escalated", "Not applicable"])
                    condition = st.selectbox("Physical condition", ["Select", "No visible damage noted", "Damage / concern identified", "Not checked"])
                    function = st.selectbox("Function check", ["Select", "Passed per local checklist", "Failed; removed from use / escalated", "Not completed"])
                with c2:
                    alarm = st.selectbox("Alarm check", ["Not applicable", "Passed per local checklist", "Failed; escalated", "Not checked"])
                    power = st.selectbox("Power / gas / connection", ["Not applicable", "Passed per local checklist", "Issue identified; escalated", "Not checked"])
                    consumables = st.selectbox("Consumables / accessories", ["Not applicable", "Available and appropriate", "Restock needed", "Issue identified"])
                    cleaning = st.selectbox("Cleaning status", ["Not documented", "Completed per policy", "Required before use", "Concern / escalated"])
                    fault = st.text_area("Fault / issue")
                    action = st.text_area("Action taken")
                    ticket = st.text_input("Maintenance ticket / escalation reference")
                outgoing = st.text_input("Outgoing staff")
                incoming = st.text_input("Incoming staff")
                notes = st.text_area("Additional notes")
                submit = st.form_submit_button("Save equipment check")
            if submit:
                def save_equipment():
                    require_write(role)
                    if assigned == "Select" or condition == "Select" or function == "Select":
                        raise ValueError("Complete assignment, physical condition and function check.")
                    issue = condition == "Damage / concern identified" or function.startswith("Failed") or alarm.startswith("Failed") or power.startswith("Issue") or consumables == "Issue identified"
                    if issue and not any(x.strip() for x in [fault, action, ticket]):
                        raise ValueError("Document the issue and action or escalation reference.")
                    rid = insert_record(
                        """INSERT INTO equipment_checks(admission_id,check_date,check_time,equipment_type,
                        equipment_identifier,assigned_patient_confirmed,physical_condition,function_check,
                        alarm_check,power_gas_check,consumables_check,cleaning_status,fault_or_issue,
                        action_taken,escalation_or_ticket,outgoing_staff,incoming_staff,nurse_name,notes,created_utc)
                        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (admission_id, d.isoformat(), t.strftime("%H:%M"), typ, clean(identifier), assigned,
                         condition, function, alarm, power, consumables, cleaning, clean(fault), clean(action),
                         clean(ticket), clean(outgoing), clean(incoming), actor, clean(notes), utc_now()),
                        actor, "equipment_check"
                    )
                    st.success(f"Equipment check #{rid} saved.")
                notify_error(save_equipment)
        eqs = rows("SELECT check_date AS Date,check_time AS Time,equipment_type AS Equipment,equipment_identifier AS Identifier,physical_condition AS Condition,function_check AS Function,alarm_check AS Alarm,fault_or_issue AS Fault,action_taken AS Action,nurse_name AS Staff FROM equipment_checks WHERE admission_id=? ORDER BY check_date DESC,check_time DESC,id DESC LIMIT 50", (admission_id,))
        if eqs:
            st.dataframe(pd.DataFrame([dict(r) for r in eqs]), use_container_width=True, hide_index=True)

    # Handover
    with tabs[8]:
        st.subheader("Shift handover · SBAR")
        if role in WRITE_ROLES:
            with st.form("handover_form", clear_on_submit=True):
                d = st.date_input("Handover date", value=default_date, key="hand_date")
                t = st.time_input("Handover time", value=datetime.now().time().replace(second=0, microsecond=0), key="hand_time")
                shift = st.selectbox("Shift", ["Day", "Evening", "Night", "Other"])
                c1, c2, c3 = st.columns(3)
                with c1:
                    outgoing = st.text_input("Outgoing nurse *")
                    incoming = st.text_input("Incoming nurse *")
                    situation = st.text_area("S · Situation / current concern *")
                with c2:
                    background = st.text_area("B · Background / history")
                    assess = st.text_area("A · Assessment / status")
                    recs = st.text_area("R · Recommendations / priorities")
                with c3:
                    airway = st.text_area("Airway / respiratory support")
                    fluids = st.text_area("Fluids / feeds / elimination")
                    meds = st.text_area("Medication due / pending")
                    lines = st.text_area("Lines / devices / equipment")
                investigations = st.text_area("Pending investigations / consultations")
                safety = st.text_area("Safety concerns / infection precautions")
                escalation = st.text_area("Escalation plan")
                ack = st.text_area("Acknowledgement / clarifications")
                submit = st.form_submit_button("Save handover")
            if submit:
                def save_handover():
                    require_write(role)
                    if not outgoing.strip() or not incoming.strip() or not situation.strip():
                        raise ValueError("Outgoing nurse, incoming nurse and situation are required.")
                    rid = insert_record(
                        """INSERT INTO handovers(admission_id,handover_date,handover_time,shift,
                        outgoing_nurse,incoming_nurse,situation,background,assessment_summary,recommendations,
                        airway_respiratory,fluids_feeding_elimination,medication_due_or_pending,
                        lines_devices_equipment,investigations_pending,safety_concerns,escalation_plan,
                        acknowledgement,created_utc) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (admission_id, d.isoformat(), t.strftime("%H:%M"), shift, outgoing.strip(),
                         incoming.strip(), situation.strip(), clean(background), clean(assess), clean(recs),
                         clean(airway), clean(fluids), clean(meds), clean(lines), clean(investigations),
                         clean(safety), clean(escalation), clean(ack), utc_now()), actor, "handover"
                    )
                    st.success(f"Handover #{rid} saved.")
                notify_error(save_handover)
        hand = rows("SELECT handover_date AS Date,handover_time AS Time,shift AS Shift,outgoing_nurse AS Outgoing,incoming_nurse AS Incoming,situation AS Situation,recommendations AS Recommendations FROM handovers WHERE admission_id=? ORDER BY handover_date DESC,handover_time DESC,id DESC LIMIT 30", (admission_id,))
        if hand:
            st.dataframe(pd.DataFrame([dict(r) for r in hand]), use_container_width=True, hide_index=True)

    # Care plan
    with tabs[9]:
        st.subheader("Individualized nursing care plan")
        st.caption("Record patient-specific findings and clinician-approved interventions. This app does not generate a diagnosis or care recommendation.")
        if role in WRITE_ROLES:
            with st.form("care_plan_form", clear_on_submit=True):
                c1, c2, c3 = st.columns(3)
                with c1:
                    pdte = st.date_input("Plan date", value=default_date, key="plan_date")
                    review = st.date_input("Review date", value=default_date, key="plan_review")
                    priority = st.selectbox("Priority", ["Immediate / high", "High", "Moderate", "Low"])
                    status = st.selectbox("Status", ["Active", "On hold", "Discontinued", "Completed"])
                with c2:
                    problem = st.text_area("Nursing problem / diagnosis *")
                    cues = st.text_area("Assessment cues / evidence")
                with c3:
                    goals = st.text_area("Measurable expected outcomes *")
                    interventions = st.text_area("Planned nursing interventions *")
                frequency = st.text_area("Frequency / schedule")
                implementation = st.text_area("Implementation notes: care actually provided")
                evaluation = st.text_area("Evaluation / response")
                eval_status = st.selectbox("Outcome evaluation", ["Ongoing", "Achieved", "Partially achieved", "Not achieved", "Unable to evaluate"])
                reviewer = st.text_input("Reviewer / next-shift nurse")
                escalation = st.text_area("Communication / escalation")
                submit = st.form_submit_button("Save care plan")
            if submit:
                def save_plan():
                    require_write(role)
                    if not problem.strip() or not goals.strip() or not interventions.strip():
                        raise ValueError("Problem, measurable outcomes and interventions are required.")
                    if review < pdte:
                        raise ValueError("Review date cannot precede plan date.")
                    rid = insert_record(
                        """INSERT INTO nursing_care_plans(admission_id,plan_date,review_date,priority,status,
                        problem_or_diagnosis,assessment_cues,goals_outcomes,interventions,frequency_or_schedule,
                        implementation_notes,evaluation,evaluation_status,escalation_or_communication,nurse_name,
                        reviewer_name,created_utc,updated_utc) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (admission_id, pdte.isoformat(), review.isoformat(), priority, status, problem.strip(),
                         clean(cues), goals.strip(), interventions.strip(), clean(frequency), clean(implementation),
                         clean(evaluation), eval_status, clean(escalation), actor, clean(reviewer), utc_now(), utc_now()),
                        actor, "nursing_care_plan"
                    )
                    st.success(f"Care plan #{rid} saved.")
                notify_error(save_plan)
        plans = rows("SELECT id,plan_date AS 'Plan date',review_date AS 'Review date',priority AS Priority,status AS Status,problem_or_diagnosis AS Problem,goals_outcomes AS Outcomes,evaluation_status AS Evaluation,nurse_name AS Staff,reviewer_name AS Reviewer FROM nursing_care_plans WHERE admission_id=? ORDER BY plan_date DESC,id DESC", (admission_id,))
        csv_export(plans, f"admission_{admission_id}_care_plans.csv", f"care_plans_{admission_id}", role)
        full = rows("SELECT * FROM nursing_care_plans WHERE admission_id=? ORDER BY plan_date DESC,id DESC", (admission_id,))
        for plan in full:
            with st.expander(f"Plan #{plan['id']} · {plan['plan_date']} · {plan['status']}"):
                for label, key in [("Problem", "problem_or_diagnosis"), ("Assessment cues", "assessment_cues"),
                                   ("Expected outcomes", "goals_outcomes"), ("Interventions", "interventions"),
                                   ("Frequency", "frequency_or_schedule"), ("Implementation", "implementation_notes"),
                                   ("Evaluation", "evaluation"), ("Communication / escalation", "escalation_or_communication")]:
                    st.markdown(f"**{label}:** {plan[key] or 'Not recorded'}")
                st.caption(f"Evaluation: {plan['evaluation_status']} · Responsible: {plan['nurse_name']} · Reviewer: {plan['reviewer_name'] or 'Not recorded'}")

    # Progress notes and history
    with tabs[10]:
        st.subheader("Nursing progress notes")
        if role in WRITE_ROLES:
            with st.form("progress_form", clear_on_submit=True):
                d = st.date_input("Note date", value=default_date, key="progress_date")
                t = st.time_input("Note time", value=datetime.now().time().replace(second=0, microsecond=0), key="progress_time")
                kind = st.selectbox("Note type", ["Routine progress", "Focused reassessment", "Intervention", "Communication / escalation", "Incident follow-up", "Other"])
                c1, c2 = st.columns(2)
                with c1:
                    assessment = st.text_area("Assessment / observed facts")
                    intervention = st.text_area("Intervention / care provided")
                with c2:
                    response = st.text_area("Response / evaluation")
                    communication = st.text_area("Communication, clinician notified and response")
                submit = st.form_submit_button("Save progress note")
            if submit:
                def save_note():
                    require_write(role)
                    if not any(x.strip() for x in [assessment, intervention, response, communication]):
                        raise ValueError("Enter at least one progress-note field.")
                    rid = insert_record(
                        """INSERT INTO progress_notes(admission_id,note_date,note_time,note_type,assessment,
                        nursing_intervention,response_evaluation,communication_escalation,nurse_name,created_utc)
                        VALUES(?,?,?,?,?,?,?,?,?,?)""",
                        (admission_id, d.isoformat(), t.strftime("%H:%M"), kind, clean(assessment),
                         clean(intervention), clean(response), clean(communication), actor, utc_now()),
                        actor, "progress_note"
                    )
                    st.success(f"Progress note #{rid} saved.")
                notify_error(save_note)
        st.subheader("Chronological record history")
        hist_tabs = st.tabs(["Admission", "Assessments", "Observations", "Fluid balance", "Medication", "Equipment", "Handovers", "Care plans", "Progress notes"])
        hist_queries = [
            ("Admission", "SELECT admission_date AS Date,admission_time AS Time,admission_reason AS Summary,admitting_nurse AS Staff,status AS Status,discharge_date AS 'Discharge date',discharge_summary AS 'Discharge summary',created_utc AS 'Saved UTC' FROM admissions WHERE id=?", (admission_id,)),
            ("Assessments", "SELECT assessment_date AS Date,assessment_time AS Time,assessment_type AS Type,neurological AS Neurological,respiratory AS Respiratory,cardiovascular AS Cardiovascular,findings_interventions AS Findings,escalation_actions AS Escalation,nurse_name AS Staff,created_utc AS 'Saved UTC' FROM assessments WHERE admission_id=? ORDER BY assessment_date DESC,assessment_time DESC,id DESC", (admission_id,)),
            ("Observations", "SELECT observation_date AS Date,observation_time AS Time,heart_rate AS HR,respiratory_rate AS RR,temperature_c AS 'Temp °C',spo2_percent AS 'SpO₂ %',fio2_percent AS 'FiO₂ %',blood_pressure AS BP,respiratory_support AS Support,nurse_name AS Staff,note AS Note,created_utc AS 'Saved UTC' FROM observations WHERE admission_id=? ORDER BY observation_date DESC,observation_time DESC,id DESC", (admission_id,)),
            ("Fluid balance", "SELECT record_date AS 'Start date',interval_start AS Start,interval_end AS End,duration_hours AS 'Duration h',weight_g AS 'Weight g',total_intake_ml AS 'Intake mL',total_output_ml AS 'Output mL',net_balance_ml AS 'Net mL',urine_output_ml_kg_hr AS 'Urine mL/kg/h',nurse_name AS Staff,notes AS Notes FROM fluid_records WHERE admission_id=? ORDER BY record_date DESC,id DESC", (admission_id,)),
            ("Medication", "SELECT record_date AS Date,medication_name AS Medication,prescribed_dose AS Dose,route AS Route,status AS Status,scheduled_time AS Scheduled,actual_administration_time AS Actual,withheld_or_omitted_reason AS Reason,nurse_name AS Staff,created_utc AS 'Saved UTC' FROM medication_records WHERE admission_id=? ORDER BY record_date DESC,id DESC", (admission_id,)),
            ("Equipment", "SELECT check_date AS Date,check_time AS Time,equipment_type AS Equipment,equipment_identifier AS Identifier,physical_condition AS Condition,function_check AS Function,alarm_check AS Alarm,fault_or_issue AS Fault,action_taken AS Action,nurse_name AS Staff,created_utc AS 'Saved UTC' FROM equipment_checks WHERE admission_id=? ORDER BY check_date DESC,check_time DESC,id DESC", (admission_id,)),
            ("Handovers", "SELECT handover_date AS Date,handover_time AS Time,shift AS Shift,outgoing_nurse AS Outgoing,incoming_nurse AS Incoming,situation AS Situation,recommendations AS Recommendations,created_utc AS 'Saved UTC' FROM handovers WHERE admission_id=? ORDER BY handover_date DESC,handover_time DESC,id DESC", (admission_id,)),
            ("Care plans", "SELECT plan_date AS 'Plan date',review_date AS 'Review date',priority AS Priority,status AS Status,problem_or_diagnosis AS Problem,goals_outcomes AS Outcomes,evaluation_status AS Evaluation,nurse_name AS Staff,reviewer_name AS Reviewer,updated_utc AS 'Updated UTC' FROM nursing_care_plans WHERE admission_id=? ORDER BY plan_date DESC,id DESC", (admission_id,)),
            ("Progress notes", "SELECT note_date AS Date,note_time AS Time,note_type AS Type,assessment AS Assessment,nursing_intervention AS Intervention,response_evaluation AS Response,communication_escalation AS Communication,nurse_name AS Staff,created_utc AS 'Saved UTC' FROM progress_notes WHERE admission_id=? ORDER BY note_date DESC,note_time DESC,id DESC", (admission_id,)),
        ]
        for tab, (name, sql, params) in zip(hist_tabs, hist_queries):
            with tab:
                result = rows(sql, params)
                if result:
                    csv_export(result, f"admission_{admission_id}_{name.lower().replace(' ', '_')}.csv", f"hist_{name}_{admission_id}", role)
                else:
                    st.info(f"No {name.lower()} records for this admission.")

# Audit integrity
with tabs[11]:
    st.subheader("Audit-chain integrity check")
    st.warning("This hash chain detects some changes; it is not tamper-proof against an administrator who can rewrite the database. Use protected external logs and signed checkpoints in any real deployment.")
    if st.button("Verify audit chain"):
        ok, count, bad_id = verify_audit_chain()
        if ok:
            st.success(f"Audit chain verified for {count} events.")
        else:
            st.error(f"Audit-chain verification failed at event #{count}: {bad_id}")
    if role == "admin":
        audit_rows = rows("SELECT id,event_utc AS UTC,actor AS Actor,action AS Action,entity_type AS Entity,entity_id AS 'Entity ID',detail AS Detail,previous_hash AS 'Previous hash',event_hash AS 'Event hash' FROM audit_events ORDER BY id DESC LIMIT 500")
        if audit_rows:
            st.dataframe(pd.DataFrame([dict(r) for r in audit_rows]), use_container_width=True, hide_index=True)

st.divider()
st.caption(
    "CHANIE · Educational prototype. Use verified information only. Use the institution's approved charting system for care. "
    "No clinical decision support, diagnosis, prescribing, or dosing authorization is provided."
)
