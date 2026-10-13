# CHANIE v3.1 prototype

**Educational prototype, not a validated EHR.** Do not store identifiable patient data until institutional security, privacy, clinical governance, disaster recovery, and validation requirements are met.

## Included files
- `chanie_app.py`: Streamlit app.
- `setup_chanie_user.py`: local account creation and deactivation utility.
- `requirements.txt`: Python dependencies.

## Run locally
Use Python 3.10+.

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt
python setup_chanie_user.py --username admin --role admin
streamlit run chanie_app.py
```

The setup utility prompts for a password. Passwords must be at least 12 characters and are hashed using PBKDF2-HMAC-SHA256 with a unique random salt. No default/demo account is created. The app refuses access if there are no users.

## User roles
- `admin`: all prototype features and audit-log view.
- `clinician`: documentation and CSV export.
- `nurse`: documentation, no CSV export.
- `viewer`: read-only view, no clinical record creation or CSV export.

This is application-level prototype authorization, not a substitute for institutional SSO/MFA, network controls, database permissions, or a formal security review.

## Database location
Default: `today_nurse_nicu.db` next to the app, matching the database filename used by your supplied v3.0 code. Override with `CHANIE_DB_PATH` if your existing database is stored elsewhere.

Keep the database, its SQLite `-wal` and `-shm` companion files while the app is running, and backups in a protected location. Use SQLite's backup API or a quiesced/consistent backup procedure. Test restores regularly. Do not put this database in a public or ephemeral hosting directory.

## Important limitations
- The app does not provide clinical decision support, diagnosis, prescribing, or neonatal dose calculation.
- Vital-sign ranges are technical input constraints, not clinical reference ranges.
- Fluid-balance arithmetic is not clinical interpretation. Confirm measurements, interval, and the weight used.
- Time-of-day chart fields are local wall time without a configured IANA timezone. Production deployment needs a facility timezone and timezone-aware event timestamps.
- The audit hash chain is tamper-evident only in a limited sense and can be rewritten by someone with direct database access. Use externally protected logs/checkpoints for real systems.
- User administration is performed through the local setup utility. Deactivation does not immediately invalidate an already open browser session, so remove access through operational controls and restart sessions as required.
- Corrections/amendments are not yet a formal signed amendment workflow. Avoid silently editing database rows.
- The partial unique index prevents one patient from having multiple active admissions. If an older database already has duplicate active admissions, resolve those duplicates manually before creating the index; the app will skip index creation and the dashboard should be reviewed.
- The app may be suitable for prototyping and usability feedback only. It has not been penetration-tested, independently validated, or clinically approved.

## Before any clinical use
Require institutional security and privacy approval, formal clinical governance, usability testing, threat modeling, audit/recovery testing, role review, encryption/key management, monitored hosting, incident response, disaster recovery, and clinical validation by qualified neonatal clinicians.
