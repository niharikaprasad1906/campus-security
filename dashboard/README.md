# Campus Security Operations Dashboard

The Streamlit application does not require the separate YOLO window to be
running. It uses local SQLite by default. When `SUPABASE_DB_URL` is configured,
it reads and writes incident records in Supabase PostgreSQL instead.

## Run

From the repository root:

```powershell
.\venv\Scripts\python.exe -m pip install -r dashboard/requirements.txt
.\venv\Scripts\python.exe -m streamlit run dashboard/app.py
```

## Pages

- **Overview** — incident totals, incident trend and distribution, recent
  alerts, and configured-camera status.
- **Camera Monitoring** — camera selection and playback of configured local
  recordings when present. **Run fresh tracking and playback** starts the
  selected recording from frame zero with a new YOLO tracker, records the
  tracker and stable person IDs seen, and displays annotated frames as the
  recording is analyzed. When processing finishes, the annotated video is
  available for replay alongside the IDs and newly saved incident records.
  Processing analyzes every source frame without waiting for real-time pacing;
  the live preview is throttled for responsiveness. Choose 1x, 1.5x, 2x, or 3x
  for the finished video's replay speed. The annotated browser-compatible
  H.264 video is temporary; the source recording is unchanged. A recorded
  sample is not a live feed.
- **Incident Management** — searchable incident table, date/type/camera/
  derived-severity/review-status filters, record details, persisted "mark
  reviewed" action, and filtered CSV export.
- **Analytics & Reports** — filtered incident trends, type/camera/hour/
  weekday charts, derived-severity distribution, and CSV export.
- **Camera & Zone Management** — read-only view of the backend's camera and
  zone configuration unless admin access is enabled. To enable editing, set
  `CAMPUS_SECURITY_ADMIN_PASSWORD` in the environment before launching
  Streamlit. Zone edits are validated against the configured recording frame,
  atomically saved to `dashboard/zone_config.json`, and loaded by the detector
  at startup. Restart a separately running detector after saving.
- **System Logs & Settings** — available incident text log and information
  about dashboard/backend capabilities.

## Supabase deployment

The dashboard creates the empty `incidents` table on startup when Supabase is
configured. It does not import the local `incidents.db`; existing local history
stays on the local machine.

1. Create a Supabase project and copy its PostgreSQL connection URI. Use the
   Supabase connection pooler URI for hosted deployments and ensure it includes
   SSL mode.
2. In Streamlit Community Cloud, open the app's **Settings → Secrets** and add:

   ```toml
   SUPABASE_DB_URL = "postgresql://..."
   ```

3. Reboot the app. Keep the connection URI private; never commit it or
   `.streamlit/secrets.toml` to Git.

Without this secret, the app continues to use the local `incidents.db` file.

## Data and limitations

Viewing pages does not modify incident history. Running fresh tracking
intentionally saves newly detected incidents through the backend logger and
also appends its existing text log; the backend's normal duplicate-event
protection still applies. Marking an incident reviewed adds `review_status` and
`reviewed_at` columns when needed; this is an additive schema migration and
preserves existing records. Review information is shared with every dashboard
session. Severity is derived from incident type; it is not stored in the
database. The application does not provide investigation notes or persistent
camera connectivity state. The dashboard does not claim a camera is live or
fabricate camera/service logs.

The application resolves `incidents.db`, `incident_log.txt`, backend camera
configuration, model weights, and sample video paths relative to the
repository, not the current working directory. Admin-password access is a
single shared environment-secret gate, not a campus identity-management
system. `imageio-ffmpeg` encodes annotated, browser-compatible sample playback.
