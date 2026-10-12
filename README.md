# Today Nurse: NICU Digital Monitoring System — Lesson 1

A beginner-friendly Streamlit prototype built for learning on an Android phone using a browser-based coding environment.

## What this first version demonstrates
- A fictional patient selector
- A simple vital-sign entry interface
- Intake/output fields
- Automatic total intake, total output, net balance, and urine-output calculation
- A clear educational-only warning

## Important limitations
- All patient records are fictional.
- Observation entries are not saved to a database.
- No authentication, audit log, clinical alerts, or clinical validation is implemented.
- Do not enter real patient data.
- This prototype is not approved for clinical care.

## Run locally in a Python environment
```bash
pip install -r requirements.txt
streamlit run app.py
```

## Suggested next lessons
1. Understand variables, inputs, calculations, and conditions.
2. Add data validation and unit tests.
3. Save demo observations to SQLite.
4. Add daily records and trend charts.
5. Add authentication, audit trails, backups, and security review before considering any real-world use.
