"""
Wedding Photo Kiosk - Configuration Template

Copy this file to config.py and fill in your real values. config.py is
gitignored and will never be committed — config.example.py (this file) is
the only config file that should ever go into version control.

See README.md for how to obtain each of these values.
"""

# EU endpoint; use "https://api.pcloud.com" instead if your account is on
# the US region.
PCLOUD_API_HOST = "https://eapi.pcloud.com"

# A long-lived pCloud auth token for YOUR account (see README.md step 1).
# This is a real account credential — never share it, never commit it.
PCLOUD_AUTH_TOKEN = "REPLACE_WITH_YOUR_PCLOUD_AUTH_TOKEN"

# The folder ID that guests' uploads land in — must match the folder your
# web app's upload-link code points at (see README.md step 2).
PCLOUD_FOLDER_ID = 0  # REPLACE with your actual folder id

# CUPS printer name as reported by `lpstat -p`, e.g. "Canon_SELPHY_CP1500"
CUPS_PRINTER_NAME = "REPLACE_WITH_YOUR_CUPS_PRINTER_NAME"

# The print-ready sheet is already composited at exactly 100x148mm by the
# web app, so this tells CUPS the matching media size rather than letting it
# auto-scale to a default like Letter or A4. The exact string varies by
# which SELPHY CUPS driver is installed — check with
# `lpoptions -p <printer> -l` and adjust to match (see README.md step 4).
CUPS_MEDIA_OPTION = "Custom.100x148mm"

# How often to check the pCloud folder for new photos, in seconds.
POLL_INTERVAL_SECONDS = 5
