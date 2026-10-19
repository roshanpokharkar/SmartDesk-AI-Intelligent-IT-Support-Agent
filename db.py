"""Database helpers: connection, schema and starter data (SQLite)."""
import os
import sqlite3
from flask import g

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "smartdesk.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'user' CHECK (role IN ('user','admin')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('user','assistant')),
    content TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS tickets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    conversation_id INTEGER REFERENCES conversations(id) ON DELETE SET NULL,
    subject TEXT NOT NULL,
    description TEXT NOT NULL,
    category TEXT NOT NULL CHECK (category IN ('Network','Hardware','Software','Account','Other')),
    priority TEXT NOT NULL DEFAULT 'Medium' CHECK (priority IN ('Low','Medium','High')),
    status TEXT NOT NULL DEFAULT 'Open' CHECK (status IN ('Open','In Progress','Resolved')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS kb_articles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    category TEXT NOT NULL,
    keywords TEXT NOT NULL DEFAULT '',
    content TEXT NOT NULL
);
"""

KB_SEED = [
    ("Wi-Fi connected but no internet", "Network", "wifi wi-fi internet router network offline",
     "1. Check whether other devices can use the same Wi-Fi.\n2. Turn Wi-Fi off and on again on your device.\n3. Restart the router: unplug for 30 seconds, then plug back in.\n4. Windows: open Command Prompt and run `ipconfig /flushdns`.\n5. Forget the network and reconnect with the password.\n6. If it still fails, contact your internet provider or create a ticket."),
    ("Forgot password or cannot log in", "Account", "password login reset locked account sign in",
     "1. Check Caps Lock and the keyboard language.\n2. Use the 'Forgot password' link on the login page.\n3. Try a private/incognito window to rule out saved-cookie problems.\n4. After 5 wrong attempts accounts may lock for 15 minutes, so wait and retry.\n5. If no reset email arrives, check spam and then raise a ticket."),
    ("Printer is offline or not printing", "Hardware", "printer print offline queue spooler",
     "1. Check power, paper, ink and cable or Wi-Fi connection.\n2. Clear the print queue (Settings > Printers > Open queue > Cancel all).\n3. Restart the Print Spooler service (services.msc).\n4. Set the printer as default and untick 'Use printer offline'.\n5. Reinstall the driver from the manufacturer's website."),
    ("Computer is running slow", "Software", "slow performance lag freeze startup memory disk",
     "1. Restart the computer.\n2. Open Task Manager (Ctrl+Shift+Esc) and close apps using high CPU or memory.\n3. Disable unnecessary startup apps.\n4. Keep at least 15% of the disk free.\n5. Run a full antivirus scan and install pending updates."),
    ("Application crashes or shows an error on start", "Software", "app crash error software install freeze not opening",
     "1. Restart the application, then the computer.\n2. Install the latest update of the app.\n3. Run it as administrator.\n4. Repair or reinstall the app from Settings > Apps.\n5. Note the exact error message and attach it to a ticket if the problem continues."),
    ("VPN will not connect", "Network", "vpn remote connect tunnel work",
     "1. Make sure your normal internet works first.\n2. Check your username, password and any authenticator code.\n3. Switch to a different network (for example a mobile hotspot).\n4. Update or reinstall the VPN client.\n5. Check that date and time on your computer are correct."),
    ("Blue screen (BSOD) on Windows", "Hardware", "blue screen bsod crash restart windows driver",
     "1. Write down the stop code shown on the screen.\n2. Remove newly connected devices (USB, docks).\n3. Boot into Safe Mode and uninstall recent drivers or updates.\n4. Run `sfc /scannow` in an admin Command Prompt.\n5. Frequent blue screens may mean faulty RAM or disk, so create a High priority ticket."),
    ("Bluetooth device will not pair", "Hardware", "bluetooth pair headphones mouse keyboard wireless",
     "1. Charge the device and put it in pairing mode.\n2. Turn Bluetooth off and on on your computer.\n3. Remove the device from the paired list and add it again.\n4. Update the Bluetooth driver in Device Manager.\n5. Move closer and away from other wireless devices."),
]


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(e=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db(admin_email=None, admin_password=None):
    """Create tables, seed knowledge base and (optionally) the admin user."""
    from werkzeug.security import generate_password_hash
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    if conn.execute("SELECT COUNT(*) FROM kb_articles").fetchone()[0] == 0:
        conn.executemany("INSERT INTO kb_articles (title, category, keywords, content) VALUES (?,?,?,?)", KB_SEED)
    if admin_email and admin_password:
        exists = conn.execute("SELECT 1 FROM users WHERE email = ?", (admin_email.lower(),)).fetchone()
        if not exists:
            conn.execute("INSERT INTO users (name, email, password_hash, role) VALUES (?,?,?, 'admin')",
                         ("Administrator", admin_email.lower(), generate_password_hash(admin_password)))
    conn.commit()
    conn.close()
