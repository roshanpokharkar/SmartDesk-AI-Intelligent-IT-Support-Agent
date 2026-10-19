"""SmartDesk AI - Flask application (routes, validation, Gemini integration)."""
import os
import re
import secrets
import sqlite3
from functools import wraps

import requests
from dotenv import load_dotenv
from flask import (Flask, abort, flash, g, jsonify, redirect, render_template,
                   request, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

from db import close_db, get_db, init_db

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY") or secrets.token_hex(32)
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax")
app.teardown_appcontext(close_db)

CATEGORIES = ["Network", "Hardware", "Software", "Account", "Other"]
PRIORITIES = ["Low", "Medium", "High"]
STATUSES = ["Open", "In Progress", "Resolved"]
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
STOP_WORDS = {"the", "and", "for", "not", "with", "how", "why", "can", "does", "was", "are",
              "this", "that", "have", "has", "but", "you", "your", "my", "is", "it", "to", "on"}

SYSTEM_PROMPT = (
    "You are SmartDesk AI, a friendly IT support agent. Help with Wi-Fi, software errors, login "
    "problems, printers, hardware and general computer troubleshooting. Give short, simple, "
    "numbered step-by-step solutions that a non-technical person can follow. Ask one clarifying "
    "question if the problem is unclear. If the topic is not IT-related, politely say you only "
    "help with IT problems. If the steps do not fix the issue, suggest creating a support ticket. "
    "Never ask for passwords."
)


# ---------- Helpers ----------
class AIError(Exception):
    """Raised when the Gemini service cannot answer."""


def ask_gemini(history, message):
    """Send the conversation to Gemini (REST API) and return the reply text."""
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key or key == "your_gemini_api_key_here":
        raise AIError("The AI service is not configured. Add GEMINI_API_KEY to the .env file.")
    model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    contents = [{"role": "user" if m["role"] == "user" else "model", "parts": [{"text": m["content"]}]}
                for m in history]
    contents.append({"role": "user", "parts": [{"text": message}]})
    body = {"systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]}, "contents": contents}
    try:
        r = requests.post(url, json=body, timeout=40,
                          headers={"x-goog-api-key": key, "Content-Type": "application/json"})
    except requests.exceptions.Timeout:
        raise AIError("The AI service took too long to respond. Please try again.")
    except requests.exceptions.RequestException:
        raise AIError("Could not reach the AI service. Check your internet connection.")
    if r.status_code in (400, 401, 403):
        raise AIError("The AI service rejected the request. Check that your Gemini API key is valid.")
    if r.status_code == 429:
        raise AIError("AI usage limit reached. Please wait a minute and try again.")
    if r.status_code != 200:
        raise AIError(f"The AI service is unavailable right now (error {r.status_code}).")
    try:
        parts = r.json()["candidates"][0]["content"]["parts"]
        text = "".join(p.get("text", "") for p in parts).strip()
    except (KeyError, IndexError, ValueError):
        text = ""
    if not text:
        raise AIError("The AI returned an empty answer. Try rephrasing your question.")
    return text


def search_kb(query, limit=10, strict=False):
    """Keyword search in the knowledge base. strict=True searches title/keywords only."""
    terms = [t for t in re.findall(r"[\w-]+", query.lower()) if len(t) > 2 and t not in STOP_WORDS][:8]
    if not terms:
        return []
    fields = ["title", "keywords"] if strict else ["title", "keywords", "content"]
    one = "(" + " OR ".join(f"{f} LIKE ?" for f in fields) + ")"
    clause = " OR ".join([one] * len(terms))
    params = []
    for t in terms:
        params += [f"%{t}%"] * len(fields)
    return get_db().execute(f"SELECT * FROM kb_articles WHERE {clause} LIMIT ?", params + [limit]).fetchall()


def login_required(view):
    @wraps(view)
    def wrapped(*a, **kw):
        if g.user is None:
            if request.path.startswith("/api/"):
                return jsonify(error="Please log in again."), 401
            flash("Please log in to continue.", "error")
            return redirect(url_for("login"))
        return view(*a, **kw)
    return wrapped


def admin_required(view):
    @wraps(view)
    @login_required
    def wrapped(*a, **kw):
        if g.user["role"] != "admin":
            abort(403)
        return view(*a, **kw)
    return wrapped


@app.before_request
def load_user_and_csrf():
    session.setdefault("csrf", secrets.token_hex(16))
    g.user = None
    if "user_id" in session:
        g.user = get_db().execute("SELECT * FROM users WHERE id = ?", (session["user_id"],)).fetchone()
        if g.user is None:
            session.pop("user_id", None)
    if request.method == "POST":
        token = request.form.get("csrf") or request.headers.get("X-CSRF-Token") or ""
        if not secrets.compare_digest(token, session["csrf"]):
            if request.path.startswith("/api/"):
                return jsonify(error="Session expired. Please refresh the page."), 400
            flash("Your session expired. Please try again.", "error")
            return redirect(request.referrer or url_for("login"))


@app.context_processor
def inject_globals():
    return {"user": g.get("user"), "csrf": session.get("csrf", ""),
            "categories": CATEGORIES, "priorities": PRIORITIES, "statuses": STATUSES,
            "code": lambda i: f"TKT-{i:04d}"}


@app.errorhandler(403)
def forbidden(e):
    return render_template("error.html", title="Access denied", msg="You do not have permission to view this page."), 403


@app.errorhandler(404)
def not_found(e):
    return render_template("error.html", title="Page not found", msg="That page or record does not exist."), 404


# ---------- Authentication ----------
@app.route("/")
def index():
    return redirect(url_for("dashboard" if g.user else "login"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if g.user:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        pw = request.form.get("password", "")
        error = None
        if not 2 <= len(name) <= 60:
            error = "Name must be 2-60 characters."
        elif not EMAIL_RE.match(email) or len(email) > 120:
            error = "Enter a valid email address."
        elif len(pw) < 8 or not re.search(r"[A-Za-z]", pw) or not re.search(r"\d", pw):
            error = "Password needs at least 8 characters, with a letter and a number."
        elif pw != request.form.get("confirm", ""):
            error = "Passwords do not match."
        if error:
            flash(error, "error")
            return render_template("register.html", name=name, email=email), 400
        try:
            get_db().execute("INSERT INTO users (name, email, password_hash) VALUES (?,?,?)",
                             (name, email, generate_password_hash(pw)))
            get_db().commit()
        except sqlite3.IntegrityError:
            flash("An account with this email already exists.", "error")
            return render_template("register.html", name=name, email=email), 400
        flash("Account created. You can log in now.", "success")
        return redirect(url_for("login"))
    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if g.user:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        row = get_db().execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if row and check_password_hash(row["password_hash"], request.form.get("password", "")):
            session.clear()
            session["user_id"] = row["id"]
            flash(f"Welcome back, {row['name']}!", "success")
            return redirect(url_for("admin" if row["role"] == "admin" else "dashboard"))
        flash("Incorrect email or password.", "error")
        return render_template("login.html", email=email), 401
    return render_template("login.html")


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("login"))


# ---------- User dashboard ----------
@app.route("/dashboard")
@login_required
def dashboard():
    db, uid = get_db(), g.user["id"]
    counts = {r["status"]: r["n"] for r in db.execute(
        "SELECT status, COUNT(*) n FROM tickets WHERE user_id=? GROUP BY status", (uid,))}
    cats = {r["category"]: r["n"] for r in db.execute(
        "SELECT category, COUNT(*) n FROM tickets WHERE user_id=? GROUP BY category", (uid,))}
    stats = {"total": sum(counts.values()), "open": counts.get("Open", 0),
             "progress": counts.get("In Progress", 0), "resolved": counts.get("Resolved", 0)}
    convos = db.execute("""SELECT c.*, (SELECT COUNT(*) FROM messages m WHERE m.conversation_id=c.id) n
                           FROM conversations c WHERE user_id=? ORDER BY c.id DESC LIMIT 5""", (uid,)).fetchall()
    tickets = db.execute("SELECT * FROM tickets WHERE user_id=? ORDER BY id DESC LIMIT 5", (uid,)).fetchall()
    return render_template("dashboard.html", stats=stats, convos=convos, tickets=tickets,
                           status_data=[stats["open"], stats["progress"], stats["resolved"]],
                           cat_labels=list(cats.keys()), cat_data=list(cats.values()))


# ---------- AI chat ----------
@app.route("/chat")
@login_required
def chat():
    db, uid = get_db(), g.user["id"]
    convos = db.execute("SELECT * FROM conversations WHERE user_id=? ORDER BY id DESC", (uid,)).fetchall()
    current, messages = None, []
    cid = request.args.get("c", type=int)
    if cid:
        current = db.execute("SELECT * FROM conversations WHERE id=? AND user_id=?", (cid, uid)).fetchone()
        if current is None:
            abort(404)
        messages = db.execute("SELECT * FROM messages WHERE conversation_id=? ORDER BY id", (cid,)).fetchall()
    return render_template("chat.html", convos=convos, current=current, messages=messages)


@app.route("/api/chat", methods=["POST"])
@login_required
def api_chat():
    data = request.get_json(silent=True) or {}
    message = str(data.get("message", "")).strip()
    if not message:
        return jsonify(error="Please type a message."), 400
    if len(message) > 2000:
        return jsonify(error="Message is too long (max 2000 characters)."), 400
    db, uid = get_db(), g.user["id"]
    cid = data.get("conversation_id")
    history = []
    if cid:
        convo = db.execute("SELECT * FROM conversations WHERE id=? AND user_id=?", (cid, uid)).fetchone()
        if convo is None:
            return jsonify(error="Conversation not found."), 404
        rows = db.execute("SELECT role, content FROM messages WHERE conversation_id=? ORDER BY id DESC LIMIT 12",
                          (cid,)).fetchall()
        history = [dict(r) for r in reversed(rows)]
    try:
        reply = ask_gemini(history, message)
    except AIError as e:
        return jsonify(error=str(e)), 503
    if not cid:
        cid = db.execute("INSERT INTO conversations (user_id, title) VALUES (?,?)",
                         (uid, message[:60])).lastrowid
    db.execute("INSERT INTO messages (conversation_id, role, content) VALUES (?, 'user', ?)", (cid, message))
    db.execute("INSERT INTO messages (conversation_id, role, content) VALUES (?, 'assistant', ?)", (cid, reply))
    db.commit()
    related = [{"id": a["id"], "title": a["title"]} for a in search_kb(message, 3, strict=True)]
    return jsonify(reply=reply, conversation_id=cid, title=message[:60], related=related)


@app.route("/api/conversations/<int:cid>/delete", methods=["POST"])
@login_required
def delete_conversation(cid):
    db = get_db()
    db.execute("DELETE FROM conversations WHERE id=? AND user_id=?", (cid, g.user["id"]))
    db.commit()
    return jsonify(ok=True)


# ---------- Tickets ----------
@app.route("/tickets")
@login_required
def tickets():
    status = request.args.get("status", "")
    sql, params = "SELECT * FROM tickets WHERE user_id=?", [g.user["id"]]
    if status in STATUSES:
        sql += " AND status=?"
        params.append(status)
    rows = get_db().execute(sql + " ORDER BY id DESC", params).fetchall()
    return render_template("tickets.html", tickets=rows, selected=status)


@app.route("/tickets/new", methods=["GET", "POST"])
@login_required
def new_ticket():
    db, uid = get_db(), g.user["id"]
    if request.method == "POST":
        f = request.form
        subject, desc = f.get("subject", "").strip(), f.get("description", "").strip()
        category, priority = f.get("category", ""), f.get("priority", "")
        cid = f.get("conversation_id", type=int)
        error = None
        if not 5 <= len(subject) <= 120:
            error = "Subject must be 5-120 characters."
        elif not 10 <= len(desc) <= 3000:
            error = "Description must be 10-3000 characters."
        elif category not in CATEGORIES or priority not in PRIORITIES:
            error = "Choose a valid category and priority."
        if cid and not db.execute("SELECT 1 FROM conversations WHERE id=? AND user_id=?", (cid, uid)).fetchone():
            cid = None  # never link another user's conversation
        if error:
            flash(error, "error")
            return render_template("ticket_new.html", form=f), 400
        tid = db.execute("""INSERT INTO tickets (user_id, conversation_id, subject, description, category, priority)
                            VALUES (?,?,?,?,?,?)""", (uid, cid, subject, desc, category, priority)).lastrowid
        db.commit()
        flash(f"Ticket TKT-{tid:04d} created. Our team will review it soon.", "success")
        return redirect(url_for("tickets"))
    form = {}
    cid = request.args.get("conversation_id", type=int)
    if cid:
        convo = db.execute("SELECT * FROM conversations WHERE id=? AND user_id=?", (cid, uid)).fetchone()
        if convo:
            msgs = db.execute("SELECT role, content FROM messages WHERE conversation_id=? ORDER BY id", (cid,)).fetchall()
            form = {"conversation_id": cid, "subject": convo["title"],
                    "description": "Chat summary:\n" + "\n".join(
                        f"{'Me' if m['role'] == 'user' else 'AI'}: {m['content'][:300]}" for m in msgs)[:2500]}
    return render_template("ticket_new.html", form=form)


# ---------- Knowledge base ----------
@app.route("/kb")
@login_required
def kb():
    q = request.args.get("q", "").strip()[:100]
    if q:
        articles = search_kb(q, 30)
    else:
        articles = get_db().execute("SELECT * FROM kb_articles ORDER BY category, title").fetchall()
    return render_template("kb.html", articles=articles, q=q)


# ---------- Admin ----------
@app.route("/admin")
@admin_required
def admin():
    db = get_db()
    stats = {k: db.execute(sql).fetchone()[0] for k, sql in {
        "tickets": "SELECT COUNT(*) FROM tickets",
        "open": "SELECT COUNT(*) FROM tickets WHERE status='Open'",
        "progress": "SELECT COUNT(*) FROM tickets WHERE status='In Progress'",
        "resolved": "SELECT COUNT(*) FROM tickets WHERE status='Resolved'",
        "users": "SELECT COUNT(*) FROM users"}.items()}
    status = request.args.get("status", "")
    sql, params = """SELECT t.*, u.name user_name, u.email user_email FROM tickets t
                     JOIN users u ON u.id=t.user_id""", []
    if status in STATUSES:
        sql += " WHERE t.status=?"
        params.append(status)
    all_tickets = db.execute(sql + " ORDER BY t.id DESC", params).fetchall()
    users = db.execute("""SELECT u.*, (SELECT COUNT(*) FROM tickets t WHERE t.user_id=u.id) n
                          FROM users u ORDER BY u.id""").fetchall()
    return render_template("admin.html", stats=stats, tickets=all_tickets, users=users, selected=status)


@app.route("/admin/tickets/<int:tid>", methods=["POST"])
@admin_required
def admin_update_ticket(tid):
    status, priority = request.form.get("status"), request.form.get("priority")
    if status not in STATUSES or priority not in PRIORITIES:
        flash("Invalid status or priority.", "error")
    else:
        db = get_db()
        cur = db.execute("UPDATE tickets SET status=?, priority=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                         (status, priority, tid))
        db.commit()
        flash(f"Ticket TKT-{tid:04d} updated." if cur.rowcount else "Ticket not found.",
              "success" if cur.rowcount else "error")
    return redirect(request.referrer or url_for("admin"))


@app.route("/admin/kb", methods=["POST"])
@admin_required
def admin_add_article():
    f = request.form
    title, content = f.get("title", "").strip(), f.get("content", "").strip()
    category, keywords = f.get("category", ""), f.get("keywords", "").strip()[:200]
    if not 5 <= len(title) <= 120 or len(content) < 20 or category not in CATEGORIES:
        flash("Provide a title (5+ chars), a category and content (20+ chars).", "error")
    else:
        get_db().execute("INSERT INTO kb_articles (title, category, keywords, content) VALUES (?,?,?,?)",
                         (title, category, keywords, content))
        get_db().commit()
        flash("Knowledge base article added.", "success")
    return redirect(url_for("admin"))


if __name__ == "__main__":
    # Safe to run every start: creates missing tables only (admin is created by init_db.py).
    init_db()
    app.run(debug=True)
