import streamlit as st

st.set_page_config(
    page_title="Today Nurse | NICU Demo",
    page_icon="🩺",
    layout="wide",
)

# DEMO ONLY: all records below are fictional.
st.title("🩺 Today Nurse")
st.subheader("NICU Digital Monitoring System")
st.info(
    "Educational prototype only. Uses fictional newborn data. "
    "Not for clinical decision-making or real patient information."
)

with st.sidebar:
    st.header("Demo patient")
    patient_id = st.selectbox("Select fictional patient", ["DEMO-001", "DEMO-002"])
    if patient_id == "DEMO-001":
        patient_name = "Baby A (fictional)"
        gestation = "32 weeks"
        weight_g = 1650
        diagnosis = "Prematurity (example record)"
    else:
        patient_name = "Baby B (fictional)"
        gestation = "35 weeks"
        weight_g = 2200
        diagnosis = "Observation only (example record)"

    st.caption("No real patient identifiers are used.")

st.markdown("### Patient overview")
c1, c2, c3, c4 = st.columns(4)
c1.metric("Demo ID", patient_id)
c2.metric("Gestational age", gestation)
c3.metric("Weight", f"{weight_g:,} g")
c4.metric("Record type", "Fictional")

st.write("**Display name:**", patient_name)
st.write("**Example admission note:**", diagnosis)

st.divider()
st.markdown("### Practice: enter one observation")

left, right = st.columns(2)
with left:
    st.caption("These fields are for learning interface design only.")
    hr = st.number_input("Heart rate (bpm)", min_value=0, max_value=300, value=140, step=1)
    rr = st.number_input("Respiratory rate (/min)", min_value=0, max_value=150, value=45, step=1)
    temp = st.number_input("Temperature (°C)", min_value=25.0, max_value=45.0, value=36.7, step=0.1, format="%.1f")
with right:
    spo2 = st.number_input("SpO₂ (%)", min_value=0, max_value=100, value=96, step=1)
    fio2 = st.number_input("FiO₂ (%)", min_value=21, max_value=100, value=21, step=1)
    respiratory_support = st.selectbox(
        "Respiratory support",
        ["Room air", "Oxygen", "CPAP", "Other / not specified"],
    )

if st.button("Show entered observation", type="primary"):
    st.success("Observation displayed for practice. It has not been saved to a database.")
    st.write({
        "Demo patient": patient_id,
        "Heart rate (bpm)": hr,
        "Respiratory rate (/min)": rr,
        "Temperature (°C)": temp,
        "SpO₂ (%)": spo2,
        "FiO₂ (%)": fio2,
        "Respiratory support": respiratory_support,
    })

st.divider()
st.markdown("### Practice: daily intake and output")

a, b = st.columns(2)
with a:
    iv_ml = st.number_input("IV fluid volume (mL)", min_value=0.0, max_value=5000.0, value=120.0, step=1.0)
    feed_ml = st.number_input("Feed volume (mL)", min_value=0.0, max_value=2000.0, value=80.0, step=1.0)
    other_intake_ml = st.number_input("Other intake (mL)", min_value=0.0, max_value=2000.0, value=0.0, step=1.0)
with b:
    urine_ml = st.number_input("Urine volume (mL)", min_value=0.0, max_value=5000.0, value=90.0, step=1.0)
    other_output_ml = st.number_input("Other measured output (mL)", min_value=0.0, max_value=5000.0, value=5.0, step=1.0)
    hours = st.number_input("Monitoring interval (hours)", min_value=1.0, max_value=24.0, value=24.0, step=1.0)

total_intake = iv_ml + feed_ml + other_intake_ml
total_output = urine_ml + other_output_ml
net_balance = total_intake - total_output
weight_kg = weight_g / 1000
urine_rate = urine_ml / weight_kg / hours if weight_kg > 0 and hours > 0 else 0

m1, m2, m3, m4 = st.columns(4)
m1.metric("Total intake", f"{total_intake:.1f} mL")
m2.metric("Total output", f"{total_output:.1f} mL")
m3.metric("Net balance", f"{net_balance:+.1f} mL")
m4.metric("Urine output", f"{urine_rate:.2f} mL/kg/hr")

st.caption(
    "Calculation practice only. Verify definitions, included fluid sources, weight selection, "
    "and monitoring interval with your unit's approved protocol before any clinical use."
)

with st.expander("Lesson 1: what the Python code is doing"):
    st.markdown(
        """
        - `st.title()` displays a heading.
        - `st.number_input()` creates a numeric input field.
        - Variables such as `iv_ml` hold values entered by the user.
        - `total_intake = iv_ml + feed_ml + other_intake_ml` adds the intake values.
        - `st.metric()` displays a calculated result.
        - `if st.button(...)` runs a block only when the button is pressed.
        """
    )

st.caption("Today Nurse • Learning prototype • Version 0.1")
