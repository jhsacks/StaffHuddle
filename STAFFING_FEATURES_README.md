# StaffHuddle automatic coverage add-on

This is an incremental add-on for the restored Streamlit app. It does not replace the existing huddle interface or Google Drive persistence.

## Install
1. Copy `staffing_features.py` and `patch_staffhuddle.py` into the repository root beside `app.py` and `storage.py`.
2. Run `python patch_staffhuddle.py` once.
3. Commit and push the three files. Streamlit redeploys automatically.

## What it adds
- Persistent roster with name, role, baseline clinic, travel-allowed clinics, and clinic preferences.
- Daily PTO, vacation, call-out, physician-off, clinic-closed, other exception controls.
- Reinstate/undo for any daily exception.
- Automatic release of staff from closed clinics and role-matched redeployment to the highest-need eligible open clinic.
- Google Drive persistence through the existing `load_root()` and `save_root()` functions.
- Audit log and explicit unassigned warnings when no compliant placement exists.

## Safety behavior
The generated plan is a recommendation and requires scheduler review. The engine never assigns a person marked off, never sends staff to a clinic outside `allowed_clinics`, never changes a staff member's role, and does not silently overwrite the baseline roster.
