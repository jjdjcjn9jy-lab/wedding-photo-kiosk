# Wedding Photo Kiosk

[![EUPL 1.2](https://img.shields.io/badge/License-EUPL_1.2-blue.svg)](LICENSE)

The printer-side companion to the [Wedding Photo Printer](../wedding-photo-printer)
web app. Runs on a device physically connected to the Canon SELPHY CP1500
(a Raspberry Pi, or any Linux box with CUPS), watches a private pCloud
folder for photos guests have sent from the web app, and prints each one
automatically.

This exists because mobile browsers — specifically Firefox for Android, and
every browser on iOS — do not reliably support custom paper sizes in their
print dialogs, which caused photos to print at the wrong scale or across
multiple pages. Routing the print job through this kiosk instead of the
guest's own browser sidesteps that entirely.

## Why this is a separate repo

This script holds a real, authenticated pCloud account credential
(`PCLOUD_AUTH_TOKEN`), not the write-only upload-link code the web app uses.
It must never live in, or be deployed alongside, the public-facing web app —
keeping it in its own repo means there's no shared history and no shared
deploy pipeline that could accidentally expose it.

## Requirements

- Python 3.9+
- A working CUPS installation with the SELPHY CP1500 already configured as
  a printer (`lpstat -p` should list it)
- The [Wedding Photo Printer](../wedding-photo-printer) web app deployed
  somewhere guests can reach, with its own pCloud upload-link code configured

Install the Python dependency:

```bash
pip install -r requirements.txt --break-system-packages
```

(`--break-system-packages` is needed on recent Debian/Raspberry Pi OS, which
otherwise blocks pip installs outside a virtual environment. Use a venv
instead if you prefer.)

## One-time setup

### 1. Get a pCloud auth token

Run this interactively on your own machine (not saved anywhere, not part of
this repo) to generate a long-lived auth token for your pCloud account:

```python
import requests, hashlib

email = "you@example.com"
password = "your-password"

digest = requests.get("https://eapi.pcloud.com/getdigest").json()["digest"]
passworddigest = hashlib.sha1(
    (password + hashlib.sha1(email.encode()).hexdigest() + digest).encode()
).hexdigest()

r = requests.get("https://eapi.pcloud.com/userinfo", params={
    "getauth": 1,
    "username": email,
    "digest": digest,
    "passworddigest": passworddigest,
}).json()

print(r["auth"])  # paste this into config.py as PCLOUD_AUTH_TOKEN
```

Use `api.pcloud.com` instead of `eapi.pcloud.com` if your account is on the
US region rather than EU.

This token doesn't expire until you log it out from pCloud's security
settings, so you only need to do this once, well before the event.

### 2. Find your folder ID

The folder ID must match the same folder your web app's upload-link code
points at (see the web app's `js/pcloudUploader.js` setup notes).

```python
import requests
print(requests.get("https://eapi.pcloud.com/listfolder", params={
    "auth": "YOUR_TOKEN_FROM_STEP_1", "folderid": 0
}).json())
```

Look for the folder's `"folderid"` field in the output.

### 3. Find your CUPS printer name

```bash
lpstat -p
```

### 4. Check supported paper sizes

```bash
lpoptions -p YOUR_PRINTER_NAME -l
```

The exact media-size string for the SELPHY CP1500 varies depending on which
CUPS driver got installed. Look for something matching 100x148mm (e.g.
`Custom.100x148mm`, `w288h432`, `4x6`, or `Postcard`) and set it in `config.py`.
If nothing matches cleanly, the script already passes `fit-to-page` as a
fallback, which scales the image to whatever media is loaded.

### 5. Configure

Copy the example config and fill in the four values from steps 1–4:

```bash
cp config.example.py config.py
```

`config.py` is gitignored — it holds your real credential and will never be
committed.

## Running

```bash
python3 print_watcher.py
```

Runs forever, polling the pCloud folder every 5 seconds, until stopped with
Ctrl+C.

## Running automatically at boot

A systemd unit is provided in `wedding-print-watcher.service`. Adjust the
`User` and paths inside it to match your setup, then:

```bash
sudo cp wedding-print-watcher.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now wedding-print-watcher
```

Check its status and logs with:

```bash
systemctl status wedding-print-watcher
journalctl -u wedding-print-watcher -f
```

## How it works

1. Polls the configured pCloud folder every `POLL_INTERVAL_SECONDS`.
2. Downloads any new files into `~/wedding-print-queue/pending/`.
3. Deletes the file from pCloud immediately after a successful download
   (so a slow poll cycle can't print the same photo twice).
4. Sends the file to CUPS via `lp`, then moves it into `printed/` or
   `failed/` depending on the outcome.
5. Anything in `failed/` needs manual review — check `journalctl` (if run
   via systemd) or the console output for the reason.

## Testing before the event

Please run this against the real printer, on the real device, well before
you need it — a polling loop, a cloud credential, and a physical print
driver are three separate things that can each go wrong in ways that are
hard to predict without a live test.

## License

Licensed under the [European Union Public Licence v1.2](LICENSE), matching
the companion web app.
