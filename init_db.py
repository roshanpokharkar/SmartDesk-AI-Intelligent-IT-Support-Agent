"""Run once: python init_db.py  -> creates smartdesk.db, KB articles and the admin account."""
import os
from dotenv import load_dotenv
from db import init_db, DB_PATH

load_dotenv()
email = os.getenv("ADMIN_EMAIL", "admin@smartdesk.com")
password = os.getenv("ADMIN_PASSWORD", "Admin@12345")
init_db(email, password)
print(f"Database ready at {DB_PATH}")
print(f"Admin login -> {email} / {password}")
