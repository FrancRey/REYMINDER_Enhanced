"""REYMINDER — personal reminders and everyday safety checklist."""
import os
import secrets
import sqlite3
from datetime import datetime, timedelta
from functools import wraps
from pathlib import Path
from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash

BASE_DIR = Path(__file__).resolve().parent
# Set REYMINDER_DATABASE_PATH to a persistent mounted disk on hosted deployments.
# Render example: /var/data/reyminder.db (requires a persistent disk mounted at /var/data).
DEFAULT_DATA_DIR = Path('/var/data') if Path('/var/data').is_dir() else BASE_DIR
DB_PATH = Path(os.environ.get('REYMINDER_DATABASE_PATH', str(DEFAULT_DATA_DIR / 'reyminder.db'))).expanduser().resolve()
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.environ.get('REYMINDER_SECRET_KEY') or 'local-development-key-change-before-deploying',
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_SECURE=os.environ.get('REYMINDER_HTTPS', '0') == '1',
    MAX_CONTENT_LENGTH=2 * 1024 * 1024,
)


def get_db():
    conn = sqlite3.connect(str(DB_PATH), timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    conn.execute('PRAGMA busy_timeout = 15000')
    return conn


def init_db():
    """Idempotent startup initialization; runs under Flask/Gunicorn too."""
    with get_db() as db:
        db.execute('PRAGMA journal_mode = WAL')
        db.execute('''CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            reset_token TEXT,
            reset_expires TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )''')
        db.execute('''CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            notes TEXT DEFAULT '',
            category TEXT NOT NULL DEFAULT 'Personal',
            due_at TEXT NOT NULL,
            completed INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        )''')
        db.execute('''CREATE TABLE IF NOT EXISTS checklist_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            category TEXT NOT NULL DEFAULT 'Before going out',
            checked INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        )''')
        db.execute('CREATE INDEX IF NOT EXISTS idx_reminders_user_due ON reminders(user_id, due_at)')
        db.execute('CREATE INDEX IF NOT EXISTS idx_checklist_user ON checklist_items(user_id)')
        # Give new accounts a useful starter checklist, but never duplicate existing entries.
        # Starter items are added on account creation, not on every application boot.


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to continue.', 'info')
            return redirect(url_for('login'))
        return view(*args, **kwargs)
    return wrapped


def get_user_reminders(user_id):
    with get_db() as db:
        rows = db.execute('SELECT * FROM reminders WHERE user_id = ? ORDER BY completed ASC, due_at ASC', (user_id,)).fetchall()
    return [dict(row) for row in rows]


def get_notifications(user_id):
    now = datetime.now()
    soon = now + timedelta(days=1)
    items = get_user_reminders(user_id)
    notifications = []
    for item in items:
        if item['completed']:
            continue
        try:
            due = datetime.fromisoformat(item['due_at'])
        except ValueError:
            continue
        if due < now:
            notifications.append({'title': item['title'], 'detail': 'Overdue reminder', 'kind': 'overdue', 'due_at': item['due_at']})
        elif due <= soon:
            notifications.append({'title': item['title'], 'detail': 'Due within 24 hours', 'kind': 'soon', 'due_at': item['due_at']})
    return sorted(notifications, key=lambda n: n['due_at'])


@app.context_processor
def inject_globals():
    notifications = get_notifications(session['user_id']) if session.get('user_id') else []
    return {'current_year': datetime.now().year, 'top_notifications': notifications,
            'notification_count': len(notifications), 'current_date': datetime.now().strftime('%A, %B %d')}


@app.route('/')
def index():
    return redirect(url_for('dashboard' if session.get('user_id') else 'login'))


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()[:80]
        email = request.form.get('email', '').strip().lower()[:254]
        password = request.form.get('password', '')
        confirm = request.form.get('confirm_password', '')
        if not name or not email or not password:
            flash('Please complete all required fields.', 'error')
        elif len(password) < 8:
            flash('Use a password with at least 8 characters.', 'error')
        elif password != confirm:
            flash('The passwords do not match.', 'error')
        else:
            try:
                with get_db() as db:
                    cursor = db.execute('INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)',
                                        (name, email, generate_password_hash(password)))
                    user_id = cursor.lastrowid
                    starter_items = [('Turn off the gas stove', 'Home & Safety'), ('Check electrical outlets', 'Home & Safety'),
                                     ('Lock doors and windows', 'Home & Safety'), ('Bring keys, wallet, and ID', 'Essentials')]
                    db.executemany('INSERT INTO checklist_items (user_id, title, category) VALUES (?, ?, ?)',
                                   [(user_id, title, category) for title, category in starter_items])
                flash('Your account is saved. Welcome to REYMINDER!', 'success')
                return redirect(url_for('login'))
            except sqlite3.IntegrityError:
                flash('An account with that email already exists. Try logging in instead.', 'error')
            except sqlite3.Error:
                app.logger.exception('Account creation failed')
                flash('We could not save your account right now. Please try again.', 'error')
    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        try:
            with get_db() as db:
                user = db.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
        except sqlite3.Error:
            app.logger.exception('Login database lookup failed')
            flash('The account database is temporarily unavailable. Please try again.', 'error')
            return render_template('login.html')
        if user and check_password_hash(user['password_hash'], password):
            session.clear()
            session['user_id'] = user['id']
            session['user_name'] = user['name']
            session['user_email'] = user['email']
            flash('Welcome back! Your space is ready.', 'success')
            return redirect(url_for('dashboard'))
        flash('Email or password is incorrect.', 'error')
    return render_template('login.html')


@app.route('/logout', methods=['POST'])
@login_required
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))


@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        with get_db() as db:
            user = db.execute('SELECT id FROM users WHERE email = ?', (email,)).fetchone()
            if user:
                token = secrets.token_urlsafe(32)
                expiry = (datetime.now() + timedelta(minutes=30)).isoformat(timespec='seconds')
                db.execute('UPDATE users SET reset_token = ?, reset_expires = ? WHERE id = ?', (token, expiry, user['id']))
                print(f"\n[REYMINDER LOCAL DEMO] Password reset link: http://127.0.0.1:5000/reset-password/{token}\n")
        flash('If the email is registered, a local demo reset link has been printed in the VS Code terminal.', 'info')
        return redirect(url_for('forgot_password'))
    return render_template('forgot_password.html')


@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    with get_db() as db:
        user = db.execute('SELECT * FROM users WHERE reset_token = ?', (token,)).fetchone()
    valid = False
    if user and user['reset_expires']:
        try:
            valid = datetime.fromisoformat(user['reset_expires']) > datetime.now()
        except ValueError:
            pass
    if not valid:
        flash('That reset link is invalid or expired. Request a new one.', 'error')
        return redirect(url_for('forgot_password'))
    if request.method == 'POST':
        password = request.form.get('password', '')
        confirm = request.form.get('confirm_password', '')
        if len(password) < 8:
            flash('Use a password with at least 8 characters.', 'error')
        elif password != confirm:
            flash('The passwords do not match.', 'error')
        else:
            with get_db() as db:
                db.execute('UPDATE users SET password_hash = ?, reset_token = NULL, reset_expires = NULL WHERE id = ?',
                           (generate_password_hash(password), user['id']))
            flash('Password updated. Please log in.', 'success')
            return redirect(url_for('login'))
    return render_template('reset_password.html')


@app.route('/dashboard')
@login_required
def dashboard():
    reminders = get_user_reminders(session['user_id'])
    total = len(reminders)
    completed = sum(bool(r['completed']) for r in reminders)
    upcoming = [r for r in reminders if not r['completed']][:5]
    return render_template('dashboard.html', reminders=reminders, total=total, completed=completed, upcoming=upcoming)


@app.route('/calendar')
@login_required
def calendar():
    return render_template('calendar.html', reminders=get_user_reminders(session['user_id']))


@app.route('/reminders')
@login_required
def reminders_page():
    reminders = get_user_reminders(session['user_id'])
    return render_template('reminders.html', reminders=reminders)


@app.route('/reminders/new', methods=['GET', 'POST'])
@login_required
def new_reminder():
    if request.method == 'POST':
        title = request.form.get('title', '').strip()[:120]
        notes = request.form.get('notes', '').strip()[:1000]
        category = request.form.get('category', 'Personal').strip()[:40]
        due_at = request.form.get('due_at', '').strip()
        if not title or not due_at:
            flash('Enter a reminder title and date/time.', 'error')
        else:
            try:
                datetime.fromisoformat(due_at)
                with get_db() as db:
                    db.execute('INSERT INTO reminders (user_id, title, notes, category, due_at) VALUES (?, ?, ?, ?, ?)',
                               (session['user_id'], title, notes, category, due_at))
                flash('Reminder saved successfully.', 'success')
                return redirect(url_for('reminders_page'))
            except ValueError:
                flash('Please choose a valid date and time.', 'error')
            except sqlite3.Error:
                app.logger.exception('Reminder save failed')
                flash('We could not save that reminder. Please try again.', 'error')
    return render_template('new_reminder.html')


@app.route('/reminders/<int:reminder_id>/toggle', methods=['POST'])
@login_required
def toggle_reminder(reminder_id):
    with get_db() as db:
        item = db.execute('SELECT completed FROM reminders WHERE id = ? AND user_id = ?', (reminder_id, session['user_id'])).fetchone()
        if item:
            db.execute('UPDATE reminders SET completed = ? WHERE id = ? AND user_id = ?',
                       (0 if item['completed'] else 1, reminder_id, session['user_id']))
    flash('Reminder status updated.', 'success')
    return redirect(request.referrer or url_for('reminders_page'))


@app.route('/reminders/<int:reminder_id>/delete', methods=['POST'])
@login_required
def delete_reminder(reminder_id):
    with get_db() as db:
        db.execute('DELETE FROM reminders WHERE id = ? AND user_id = ?', (reminder_id, session['user_id']))
    flash('Reminder deleted.', 'info')
    return redirect(request.referrer or url_for('reminders_page'))


@app.route('/checklist', methods=['GET', 'POST'])
@login_required
def checklist():
    if request.method == 'POST':
        title = request.form.get('title', '').strip()[:120]
        category = request.form.get('category', 'Before going out').strip()[:40]
        if title:
            with get_db() as db:
                db.execute('INSERT INTO checklist_items (user_id, title, category) VALUES (?, ?, ?)', (session['user_id'], title, category))
            flash('Checklist item added.', 'success')
        return redirect(url_for('checklist'))
    with get_db() as db:
        items = [dict(row) for row in db.execute('SELECT * FROM checklist_items WHERE user_id = ? ORDER BY category, id', (session['user_id'],)).fetchall()]
    return render_template('checklist.html', items=items)


@app.route('/checklist/<int:item_id>/toggle', methods=['POST'])
@login_required
def toggle_checklist(item_id):
    with get_db() as db:
        item = db.execute('SELECT checked FROM checklist_items WHERE id = ? AND user_id = ?', (item_id, session['user_id'])).fetchone()
        if item:
            db.execute('UPDATE checklist_items SET checked = ? WHERE id = ? AND user_id = ?', (0 if item['checked'] else 1, item_id, session['user_id']))
    return redirect(url_for('checklist'))


@app.route('/checklist/<int:item_id>/delete', methods=['POST'])
@login_required
def delete_checklist(item_id):
    with get_db() as db:
        db.execute('DELETE FROM checklist_items WHERE id = ? AND user_id = ?', (item_id, session['user_id']))
    flash('Checklist item removed.', 'info')
    return redirect(url_for('checklist'))


@app.route('/notifications')
@login_required
def notifications():
    return render_template('notifications.html', notifications=get_notifications(session['user_id']))


@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    with get_db() as db:
        user = db.execute('SELECT id, name, email, created_at FROM users WHERE id = ?', (session['user_id'],)).fetchone()
    if not user:
        session.clear()
        flash('Please log in again.', 'error')
        return redirect(url_for('login'))
    if request.method == 'POST':
        name = request.form.get('name', '').strip()[:80]
        email = request.form.get('email', '').strip().lower()[:254]
        if not name or not email:
            flash('Name and email are required.', 'error')
        else:
            try:
                with get_db() as db:
                    db.execute('UPDATE users SET name = ?, email = ? WHERE id = ?', (name, email, session['user_id']))
                session['user_name'] = name
                session['user_email'] = email
                flash('Profile updated.', 'success')
                return redirect(url_for('profile'))
            except sqlite3.IntegrityError:
                flash('That email is already used by another account.', 'error')
    return render_template('profile.html', user=dict(user))


@app.route('/privacy')
def privacy():
    return render_template('privacy.html')


# Initialize tables at import time so `gunicorn app:app` also has a ready database.
init_db()

if __name__ == '__main__':
    app.run(debug=os.environ.get('FLASK_DEBUG', '0') == '1')
