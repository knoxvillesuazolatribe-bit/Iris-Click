"""IrisClick online backup copy (Vercel).

The PC server (app/api/main.py) is unchanged. This package builds a second,
smaller server for the internet: account pages, Voice, SOS, Settings, Admin
and Reports, using the same Supabase database. Calibration, cameras and eye
tracking stay on the PC. Every request needs the site access code first
(see access.py).
"""
