# Karna OS v0.3.0 — Targeting Engine

Released: 2026-08-15

## Added

- Professional Karna-inspired light dashboard with navy/gold visual system
- Evidence edit, verify, reject, restore, and resume deletion controls
- Automatic reviewed/partially-reviewed resume state
- ATS careers-URL detection for Ashby, Greenhouse, and Lever
- Matching v2 hard eligibility checks and transparent explanations
- Country/remote-country, seniority, experience, and score-threshold preferences
- Application pipeline statuses, notes, event history, and removal
- Resume-tailoring and interview-preparation interfaces
- Timestamped SQLite backup control and v0.2 migration support
- IEEE experimental roadmap and future Supabase lifecycle fields

## Safety decisions

- No automatic application submission
- No silent local inactivity deletion
- No secrets in frontend code
- No AI-generated resume claims without supplied evidence
