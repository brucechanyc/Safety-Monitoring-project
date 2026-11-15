# Meraki Person-Detection Snapshot Capture

Grabs a snapshot from **three Meraki cameras** every ~5 seconds during working
hours (**07:00–18:00**), runs Ultralytics **YOLO26** person detection on each
image, and saves **only the photos that contain a person** — one folder per
camera. Built to run unattended for several days.

- **Active window:** 07:00–18:00 local time. Outside it, the program idles (no captures).
- **One folder per camera:** `photo saved/<SERIAL>/` with timestamped `.jpg` files.
- **Auto-stop:** when **any** camera folder reaches **1200** photos, the whole program ends.
- **Manual stop (no data loss):** press **Ctrl-C**, or create a file named **`STOP`** in this folder.

---

## 1. Setup

You need Python 3.9+ installed. The **first run downloads the YOLO weights**, so
that run needs an internet connection.

### Windows (the machine you'll actually run this on)

Open **Command Prompt** in this folder and run:

```bat
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

### macOS (for building/testing only)

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

---

## 2. Add your credentials

Copy `.env.example` to `.env` and fill in your real values:

```
MERAKI_API_KEY=...your key...
MERAKI_ORG_ID=...your org id...
MERAKI_SERIALS=SERIAL1,SERIAL2,SERIAL3
```

`.env` is git-ignored and never leaves this folder. **Don't paste your keys into chat.**

---

## 3. Test before the long run

This does exactly one snapshot per camera, tells you whether each one fetched and
whether a person was detected, then exits — no waiting for the schedule:

```bash
python main.py --test
```

If all three cameras report `snapshot OK`, your key/org/serials are correct.

---

## 4. Run it

### Windows

Double-click **`run.bat`**, or from Command Prompt:

```bat
python main.py
```

To keep it running for days:
- **Keep the PC awake:** Settings → **System → Power & sleep** → set **Sleep = Never**
  (and screen off is fine). Windows has no `caffeinate`.
- **Survive logoff (optional):** use **Task Scheduler** → create a task that runs
  `main.py` with *"Run whether user is logged on or not"* and the **Start in** field
  set to this folder.

### macOS (testing)

```bash
caffeinate -is python main.py
```

`caffeinate` stops the Mac sleeping and killing the process mid-run.

---

## 5. Stopping it

Any of these ends the program cleanly, finishing the current photo first so
**nothing already saved is lost**:

1. **It fills up** — any camera folder hits 1200 photos.
2. **Ctrl-C** in the window where it's running.
3. **Create a `STOP` file** in this folder (works even if the window isn't handy —
   e.g. `type nul > STOP` on Windows, or `touch STOP` on macOS). The file is
   deleted automatically on the next start.

---

## Where things go

```
photo saved/
├── SERIAL1/  2026-08-27_09-14-03_123456.jpg ...
├── SERIAL2/  ...
└── SERIAL3/  ...
capture.log   # rotating log of every save, error, and shutdown reason
```

## Tuning

Edit `config.py`:

| Setting | Meaning | Default |
|---|---|---|
| `CAPTURE_INTERVAL_SECONDS` | seconds between captures per camera | `5` |
| `ACTIVE_START_HOUR` / `ACTIVE_END_HOUR` | active window | `7` / `18` |
| `CONFIDENCE_THRESHOLD` | lower = catches more people, more false positives | `0.25` |
| `MAX_PHOTOS_PER_FOLDER` | photos per camera before the program stops | `1200` |
| `MODEL_NAME` | YOLO weight to use | `yolo26n.pt` |

> **Note on the 1200 cap:** it counts the files actually in each camera folder. If
> you restart while a folder is already full, the program stops immediately — clear
> or move that folder to resume.

> **Note on cadence:** a strict 5-second spacing is best-effort. Meraki's snapshot
> URL takes a few seconds to become available after it's requested, so a cycle can
> occasionally run a little longer than 5s.
