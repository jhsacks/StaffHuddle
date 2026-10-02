# Clinic staffing update

Drop these files into the existing Streamlit app or merge the modules. The logic provides:

- PTO/OFF/LEAVE exceptions with same-day reinstate
- automatic closure when all baseline MD coverage at a clinic is removed
- redeployment of staff from closed clinics
- role-qualified replacement coverage using ranked location preferences
- hard enforcement of inactive staff, leave, role qualification, and unavailable locations
- add/remove staff and add/remove unused roles
- visible change log and uncovered-role warnings

Run with `streamlit run app.py`. Recommendations require human approval.
