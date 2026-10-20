REYMINDER — multi-page personal reminder app
============================================

REQUIREMENTS
- Python 3.10 or newer
- Visual Studio Code
- Python extension for VS Code

RUN LOCALLY (Windows)
1. Extract the REYMINDER folder and open it in VS Code.
2. Open Terminal -> New Terminal.
3. Create a virtual environment:
       py -m venv .venv
4. Activate it in PowerShell:
       .\.venv\Scripts\Activate.ps1
   If PowerShell blocks activation, use Command Prompt and run:
       .venv\Scripts\activate.bat
5. Install dependencies:
       python -m pip install -r requirements.txt
6. Run the application:
       python app.py
7. Open http://127.0.0.1:5000

FEATURES
- Account registration and login with password hashing
- Separate Overview, Calendar, My Reminders, Add Reminder, Going-out Checklist,
  Notifications, and Profile Settings pages
- Light/dark theme toggle, remembered in the browser
- Password show/hide controls
- In-app notification list for overdue reminders and reminders due in 24 hours
- Checklist starter items for gas stove, outlets, doors/windows, keys, wallet, and ID
- Reminder filtering, completion, deletion, and calendar date selection
- Profile name/email editing
- Local demo password reset link printed in the terminal (not email delivery)

ACCOUNT AND DATABASE PERSISTENCE
- Local accounts are stored in REYMINDER/reyminder.db. Do not delete this file if
  you want to keep local accounts and reminders. It is intentionally not bundled.
- The app initializes its database at startup, including when launched by Gunicorn.
- On hosting platforms, SQLite files can be erased when the service is redeployed or
  restarted if the host filesystem is ephemeral. A persistent disk or managed database
  is required for accounts to survive deployments.
- For Render, attach a Persistent Disk to the web service and set its mount path to
  /var/data. Add this environment variable:
       REYMINDER_DATABASE_PATH=/var/data/reyminder.db
  Keep the disk attached after deploys. Without persistent storage, previously created
  accounts on an ephemeral deployment may not be recoverable.
- To keep existing local accounts, do not change the database path unless you also copy
  the existing reyminder.db file to the new path.

SECURITY / DEPLOYMENT NOTES
- Render build command: pip install -r requirements.txt
- Render start command: gunicorn app:app
- Set REYMINDER_SECRET_KEY to a long, random secret in your hosting environment.
- Use HTTPS. Set REYMINDER_HTTPS=1 when the app is served exclusively over HTTPS.
- Do not run Flask debug mode in production. The default is off.
- The password-reset flow is for local classroom demos only; it does not send email and
  should be replaced with a verified email delivery flow before public deployment.
- This is a school-project prototype. Before production use, add CSRF protection,
  login rate limiting, and a reviewed password-reset flow.
- Never commit .venv, reyminder.db, secrets, or real personal information to GitHub.

COMMON COMMANDS
- Start locally: python app.py
- Set a local secret in PowerShell for the current terminal session:
      $env:REYMINDER_SECRET_KEY = "put-a-long-random-secret-here"
- Optional local database override:
      $env:REYMINDER_DATABASE_PATH = "$PWD\reyminder.db"

PROJECT FILES
app.py                    Flask backend, database, routes
requirements.txt           Python dependencies
templates/                 Separate HTML pages and shared layouts
static/css/style.css       Responsive styling and light/dark themes
static/js/main.js          Theme, calendar, password, and list interactions
reyminder.db               Created automatically at first startup; keep private
