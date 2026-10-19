# SmartDesk AI - Intelligent IT Support Agent

An AI-powered IT help desk. Users chat with a Gemini-powered assistant to fix Wi-Fi, software, login, printer and hardware problems, search a knowledge base, and raise support tickets when the AI cannot solve the issue. Admins manage all tickets and users.

**Stack:** HTML/CSS/JavaScript, Python Flask, SQLite, Google Gemini API.

## Features
- Registration and login with hashed passwords (Werkzeug), session-based auth, CSRF protection
- AI chat with saved conversation history and friendly errors when Gemini is unavailable
- Tickets: auto IDs (TKT-0001), categories (Network, Hardware, Software, Account, Other), priorities (Low/Medium/High), statuses (Open/In Progress/Resolved)
- User dashboard: stat cards, charts, recent conversations and ticket history
- Admin panel: all tickets, update status/priority, list users, add knowledge base articles
- Knowledge base: searchable articles, plus related guides shown under AI replies
- Responsive dark-navy UI (desktop, tablet, mobile)

## Project structure
```
smartdesk-ai/
├── app.py              # Flask routes, validation, Gemini call
├── db.py               # SQLite connection, schema, seed articles
├── init_db.py          # Creates database + admin account
├── requirements.txt
├── .env.example        # Copy to .env and add your keys
├── templates/          # HTML (Jinja2) pages
└── static/
    ├── css/style.css
    └── js/main.js, chat.js
```

## Setup in VS Code
1. Install **Python 3.9+** and open the `smartdesk-ai` folder in VS Code (File > Open Folder).
2. Open the terminal (Ctrl + `) and create a virtual environment:
   - Windows: `python -m venv venv` then `venv\Scripts\activate`
   - macOS/Linux: `python3 -m venv venv` then `source venv/bin/activate`
3. Install dependencies: `pip install -r requirements.txt`
4. Get a free Gemini API key at https://aistudio.google.com/apikey
5. Copy `.env.example` to `.env` and edit it:
   - `GEMINI_API_KEY` = your key
   - `SECRET_KEY` = any long random text
   - `ADMIN_EMAIL` / `ADMIN_PASSWORD` = admin login you want
6. Create the database: `python init_db.py`
7. Run the app: `python app.py`
8. Open http://127.0.0.1:5000

Log in as the admin from step 5, or register a normal user account.

## Database tables
| Table | Purpose | Relationships |
|---|---|---|
| users | accounts and roles | - |
| conversations | one chat thread | user_id -> users |
| messages | chat history | conversation_id -> conversations |
| tickets | support tickets | user_id -> users, conversation_id -> conversations (optional) |
| kb_articles | troubleshooting articles | - |

## Security notes
- Passwords hashed with `generate_password_hash`; API key only in `.env`, used server-side only
- All pages except login/register require authentication; admin routes require the admin role
- Every ticket and conversation query is filtered by the logged-in user's id
- Inputs validated on the server; SQL uses parameters; Jinja auto-escapes output
- For production: set a fixed `SECRET_KEY`, turn off `debug=True`, and serve over HTTPS

## Troubleshooting
- **"AI service is not configured"**: check `GEMINI_API_KEY` in `.env` and restart the app.
- **"rejected the request"**: the key is invalid or the model name in `GEMINI_MODEL` is not available to you.
- **"usage limit reached"**: free tier limit; wait a minute.
- **Reset everything**: stop the app, delete `smartdesk.db`, run `python init_db.py` again.
