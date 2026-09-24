#!/usr/bin/env python3
"""
Wedding Photo Kiosk - Print Watcher
Copyright (C) 2026 sandifol
Licensed under the EUPL, Version 1.2

Runs on the device connected to the Canon SELPHY CP1500 via CUPS. Polls a
pCloud folder for new photos uploaded by guests' phones (via the companion
web app's pCloud upload path) and prints each one automatically, then
archives it so it isn't printed twice.

Setup instructions, including how to obtain a pCloud auth token and find
your folder ID and CUPS printer name, are in README.md.

Before running this, copy config.example.py to config.py and fill in your
own values — config.py is gitignored and never committed.

Usage:
    python3 print_watcher.py
    (runs forever, polling every POLL_INTERVAL_SECONDS; Ctrl+C to stop)

    To run unattended at boot, see wedding-print-watcher.service.
"""

import logging
import subprocess
import sys
import time
from pathlib import Path

import requests

try:
    import config
except ImportError:
    print(
        "config.py not found. Copy config.example.py to config.py and fill "
        "in your own values (see README.md) before running this script.",
        file=sys.stderr,
    )
    sys.exit(1)

# Where downloaded photos are kept before/after printing
WORK_DIR = Path.home() / "wedding-print-queue"
PENDING_DIR = WORK_DIR / "pending"
PRINTED_DIR = WORK_DIR / "printed"
FAILED_DIR = WORK_DIR / "failed"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("print_watcher")


def ensure_dirs():
    for d in (PENDING_DIR, PRINTED_DIR, FAILED_DIR):
        d.mkdir(parents=True, exist_ok=True)


def pcloud_call(method, params=None, stream=False):
    """Make an authenticated pCloud API call. Raises on transport or
    application-level errors."""
    params = dict(params or {})
    params["auth"] = config.PCLOUD_AUTH_TOKEN
    # POST with the token in the body rather than a GET query string: the
    # auth token must never end up in exception messages or logs. requests
    # connection errors include the full URL (query string and all) in
    # their message, but do not include POST body contents.
    resp = requests.post(
        f"{config.PCLOUD_API_HOST}/{method}",
        data=params,
        stream=stream,
        timeout=30,
    )
    resp.raise_for_status()
    if stream:
        return resp
    data = resp.json()
    if data.get("result") != 0:
        raise RuntimeError(f"pCloud API error on {method}: {data}")
    return data


def list_new_files():
    """Return metadata for files currently in the watched folder."""
    data = pcloud_call("listfolder", {"folderid": config.PCLOUD_FOLDER_ID})
    contents = data.get("metadata", {}).get("contents", [])
    return [f for f in contents if not f.get("isfolder")]


def download_file(fileid, name):
    """Download a file by id to PENDING_DIR, returning the local path."""
    link_data = pcloud_call("getfilelink", {"fileid": fileid})
    hosts = link_data.get("hosts", [])
    path = link_data.get("path", "")
    if not hosts or not path:
        raise RuntimeError(f"No download link returned for fileid {fileid}")

    download_url = f"https://{hosts[0]}{path}"
    # The remote name is attacker-controlled (the web app's upload code is
    # public and lets anyone drop files in the watched folder), and a name
    # like "../../evil" or an absolute path would escape PENDING_DIR when
    # joined onto it. Keep only the final path component, and prefix the
    # fileid so two uploads with the same name can't clobber each other.
    safe_name = f"{fileid}-{Path(name).name}"
    local_path = PENDING_DIR / safe_name

    resp = requests.get(download_url, stream=True, timeout=60)
    resp.raise_for_status()
    with open(local_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=65536):
            f.write(chunk)

    return local_path


def delete_remote_file(fileid):
    """Remove the file from pCloud once it's safely downloaded and queued,
    so the same photo is never picked up and printed twice."""
    pcloud_call("deletefile", {"fileid": fileid})


def print_file(local_path: Path) -> bool:
    """Send a file to CUPS. Returns True on apparent success."""
    cmd = [
        "lp",
        "-d", config.CUPS_PRINTER_NAME,
        "-o", f"media={config.CUPS_MEDIA_OPTION}",
        "-o", "fit-to-page",  # safety net if the media size isn't recognised
        str(local_path),
    ]
    log.info("Printing: %s", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        log.error("lp failed (%s): %s", result.returncode, result.stderr.strip())
        return False
    log.info("Print job submitted: %s", result.stdout.strip())
    return True


def process_once():
    try:
        files = list_new_files()
    except Exception as e:
        log.error("Failed to list pCloud folder: %s", e)
        return

    if not files:
        return

    log.info("Found %d file(s) to print", len(files))

    for f in files:
        fileid = f["fileid"]
        name = f["name"]
        try:
            local_path = download_file(fileid, name)
            log.info("Downloaded %s", local_path)
        except Exception as e:
            log.error("Failed to download %s (fileid %s): %s", name, fileid, e)
            continue

        # Delete from pCloud BEFORE printing: if printing fails we still
        # have the local copy in PENDING_DIR/FAILED_DIR to retry manually,
        # and we avoid a race where a slow poll cycle downloads + prints
        # the same file twice before it's removed remotely.
        try:
            delete_remote_file(fileid)
        except Exception as e:
            log.warning("Could not delete remote file %s (fileid %s): %s — "
                        "it may be re-downloaded next cycle", name, fileid, e)

        if print_file(local_path):
            local_path.rename(PRINTED_DIR / local_path.name)
        else:
            local_path.rename(FAILED_DIR / local_path.name)
            log.error("Moved %s to failed/ for manual review", local_path.name)


def check_config():
    problems = []
    if config.PCLOUD_AUTH_TOKEN == "REPLACE_WITH_YOUR_PCLOUD_AUTH_TOKEN":
        problems.append("PCLOUD_AUTH_TOKEN is not set in config.py")
    if config.PCLOUD_FOLDER_ID == "REPLACE_WITH_YOUR_PCLOUD_FOLDER_ID":
        problems.append("PCLOUD_FOLDER_ID is not set in config.py")
    if config.CUPS_PRINTER_NAME == "REPLACE_WITH_YOUR_CUPS_PRINTER_NAME":
        problems.append("CUPS_PRINTER_NAME is not set in config.py")
    if problems:
        for p in problems:
            log.error("Configuration problem: %s", p)
        log.error("Edit config.py before running (see README.md for setup steps).")
        sys.exit(1)


def main():
    check_config()
    ensure_dirs()
    log.info("Watching pCloud folder %s, printing to %s", config.PCLOUD_FOLDER_ID, config.CUPS_PRINTER_NAME)
    log.info("Polling every %ss. Ctrl+C to stop.", config.POLL_INTERVAL_SECONDS)

    while True:
        process_once()
        time.sleep(config.POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log.info("Stopped.")
