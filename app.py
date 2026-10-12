import os, sqlite3, secrets
from datetime import datetime, timedelta, timezone
from functools import wraps
import requests
from flask import Flask, jsonify, request, send_from_directory, session, redirect
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__, static_folder="static")
app.secret_key = os.environ.get("FLASK_SECRET_KEY") or secrets.token_hex(32)
DB = os.environ.get("DATABASE_PATH", "skalak_ai.db")
WAVE_API_KEY = os.environ.get("WAVE_API_KEY", "").strip()
MOOV_PAYMENT_INSTRUCTIONS = os.environ.get("MOOV_PAYMENT_INSTRUCTIONS", "Contactez l’administrateur pour les modalités de paiement Moov Money.")
ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "").strip()
API_FOOTBALL_KEY = os.environ.get("API_FOOTBALL_KEY", "").strip()
FOOTBALL_BASE = "https://v3.football.api-sports.io"
WAVE_BASE = "https://api.wave.com"

PLANS = {"pro": 1500, "vip": 4500}

def connect():
    db = sqlite3.connect(DB)
    db.row_factory = sqlite3.Row
    return db

def init_db():
    with connect() as db:
        db.execute("""CREATE TABLE IF NOT EXISTS users(
          id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT UNIQUE NOT NULL,
          password_hash TEXT NOT NULL, created_at TEXT NOT NULL)""")
        db.execute("""CREATE TABLE IF NOT EXISTS payments(
          id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
          plan TEXT NOT NULL, amount INTEGER NOT NULL, method TEXT NOT NULL,
          status TEXT NOT NULL, wave_checkout_id TEXT, reference TEXT UNIQUE NOT NULL,
          created_at TEXT NOT NULL, paid_at TEXT, expires_at TEXT)""")
init_db()

def now():
    return datetime.now(timezone.utc)

def iso(dt):
    return dt.isoformat()

def current_subscription(user_id):
    with connect() as db:
        row = db.execute("""SELECT * FROM payments WHERE user_id=? AND status='paid'
          AND expires_at>? ORDER BY expires_at DESC LIMIT 1""", (user_id, iso(now()))).fetchone()
        return dict(row) if row else None

def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("user_id"):
            return jsonify({"error":"Connecte-toi d’abord."}), 401
        return fn(*args, **kwargs)
    return wrapper

def wave_request(method, path, **kwargs):
    if not WAVE_API_KEY:
        return None, "Wave API non configurée. Ajoute WAVE_API_KEY dans les secrets du serveur."
    headers = kwargs.pop("headers", {})
    headers.update({"Authorization": "Bearer " + WAVE_API_KEY, "Content-Type":"application/json"})
    try:
        r = requests.request(method, WAVE_BASE + path, headers=headers, timeout=20, **kwargs)
        data = r.json() if r.content else {}
        if not r.ok:
            return None, "Erreur Wave (" + str(r.status_code) + "): " + str(data.get("message", data))
        return data, None
    except requests.RequestException as e:
        return None, "Connexion Wave impossible: " + str(e)

@app.get("/")
def home():
    return send_from_directory("static", "index.html")

@app.get("/api/config")
def config():
    return jsonify({"wave_configured": bool(WAVE_API_KEY), "moov_instructions": MOOV_PAYMENT_INSTRUCTIONS,
                    "plans": PLANS, "logged_in": bool(session.get("user_id"))})

@app.post("/api/register")
def register():
    body = request.get_json(silent=True) or {}
    email = str(body.get("email","")).strip().lower()
    password = str(body.get("password",""))
    if "@" not in email or len(email) > 190:
        return jsonify({"error":"Adresse e-mail invalide."}), 400
    if len(password) < 10:
        return jsonify({"error":"Choisis un mot de passe d’au moins 10 caractères."}), 400
    try:
        with connect() as db:
            cur = db.execute("INSERT INTO users(email,password_hash,created_at) VALUES(?,?,?)",
                             (email, generate_password_hash(password), iso(now())))
            session["user_id"] = cur.lastrowid
            session["email"] = email
        return jsonify({"ok":True, "email":email})
    except sqlite3.IntegrityError:
        return jsonify({"error":"Cette adresse e-mail est déjà inscrite. Connecte-toi."}), 409

@app.post("/api/login")
def login():
    body = request.get_json(silent=True) or {}
    email = str(body.get("email","")).strip().lower()
    password = str(body.get("password",""))
    with connect() as db:
        user = db.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
    if not user or not check_password_hash(user["password_hash"], password):
        return jsonify({"error":"Adresse e-mail ou mot de passe incorrect."}), 401
    session["user_id"] = user["id"]
    session["email"] = user["email"]
    return jsonify({"ok":True, "email":user["email"]})

@app.post("/api/logout")
def logout():
    session.clear()
    return jsonify({"ok":True})

@app.get("/api/me")
def me():
    if not session.get("user_id"):
        return jsonify({"logged_in":False})
    sub = current_subscription(session["user_id"])
    return jsonify({"logged_in":True, "email":session.get("email"), "subscription":sub})

@app.post("/api/pay/wave")
@login_required
def pay_wave():
    body = request.get_json(silent=True) or {}
    plan = str(body.get("plan","")).lower()
    if plan not in PLANS:
        return jsonify({"error":"Abonnement invalide."}), 400
    ref = "SKALAK-" + secrets.token_hex(8).upper()
    amount = PLANS[plan]
    base_url = request.url_root.rstrip("/")
    data, err = wave_request("POST", "/v1/checkout/sessions", json={
        "amount": str(amount), "currency":"XOF",
        "client_reference": ref,
        "success_url": base_url + "/?payment=return&ref=" + ref,
        "error_url": base_url + "/?payment=error&ref=" + ref
    })
    if err:
        return jsonify({"error":err}), 503
    checkout_id = data.get("id")
    if not checkout_id or not data.get("wave_launch_url"):
        return jsonify({"error":"Wave n’a pas renvoyé de lien de paiement valide."}), 502
    with connect() as db:
        db.execute("""INSERT INTO payments(user_id,plan,amount,method,status,wave_checkout_id,reference,created_at)
          VALUES(?,?,?,?,?,?,?,?)""", (session["user_id"],plan,amount,"wave","pending",checkout_id,ref,iso(now())))
    return jsonify({"checkout_url":data["wave_launch_url"], "reference":ref})

@app.post("/api/pay/moov")
@login_required
def pay_moov():
    body = request.get_json(silent=True) or {}
    plan = str(body.get("plan","")).lower()
    if plan not in PLANS:
        return jsonify({"error":"Abonnement invalide."}), 400
    ref = "SKALAK-" + secrets.token_hex(8).upper()
    with connect() as db:
        db.execute("""INSERT INTO payments(user_id,plan,amount,method,status,reference,created_at)
          VALUES(?,?,?,?,?,?,?)""", (session["user_id"],plan,PLANS[plan],"moov","pending",ref,iso(now())))
    return jsonify({"reference":ref, "amount":PLANS[plan], "instructions":MOOV_PAYMENT_INSTRUCTIONS,
                    "message":"La demande est créée, mais l’abonnement ne sera activé qu’après confirmation réelle du paiement par le marchand."})

@app.post("/api/payment/verify")
@login_required
def verify_payment():
    body = request.get_json(silent=True) or {}
    ref = str(body.get("reference","")).strip()
    with connect() as db:
        row = db.execute("SELECT * FROM payments WHERE reference=? AND user_id=?", (ref,session["user_id"])).fetchone()
    if not row:
        return jsonify({"error":"Référence de paiement introuvable."}), 404
    if row["status"] == "paid":
        return jsonify({"ok":True,"status":"paid","subscription":current_subscription(session["user_id"])})
    if row["method"] != "wave" or not row["wave_checkout_id"]:
        return jsonify({"ok":False,"status":row["status"],"message":"Ce paiement doit être confirmé par le marchand."}), 202
    data, err = wave_request("GET", "/v1/checkout/sessions/" + row["wave_checkout_id"])
    if err:
        return jsonify({"error":err}), 503
    if data.get("payment_status") == "succeeded":
        start = now()
        old = current_subscription(session["user_id"])
        if old:
            try:
                old_exp = datetime.fromisoformat(old["expires_at"])
                if old_exp > start: start = old_exp
            except Exception: pass
        expiry = start + timedelta(days=30)
        with connect() as db:
            db.execute("UPDATE payments SET status='paid',paid_at=?,expires_at=? WHERE id=?",
                       (iso(now()),iso(expiry),row["id"]))
        return jsonify({"ok":True,"status":"paid","subscription":current_subscription(session["user_id"])})
    return jsonify({"ok":False,"status":data.get("payment_status","pending"),"message":"Paiement pas encore confirmé par Wave."}), 202

@app.post("/admin/moov/confirm")
def admin_moov_confirm():
    if not ADMIN_TOKEN or request.headers.get("X-Admin-Token","") != ADMIN_TOKEN:
        return jsonify({"error":"Accès administrateur refusé."}), 403
    body = request.get_json(silent=True) or {}
    ref = str(body.get("reference","")).strip()
    with connect() as db:
        row = db.execute("SELECT * FROM payments WHERE reference=? AND method='moov' AND status='pending'", (ref,)).fetchone()
        if not row: return jsonify({"error":"Paiement Moov en attente introuvable."}), 404
        start=now()
        old=current_subscription(row["user_id"])
        if old:
            try:
                old_exp=datetime.fromisoformat(old["expires_at"])
                if old_exp>start: start=old_exp
            except Exception: pass
        expiry=start+timedelta(days=30)
        db.execute("UPDATE payments SET status='paid',paid_at=?,expires_at=? WHERE id=?", (iso(now()),iso(expiry),row["id"]))
    return jsonify({"ok":True,"reference":ref,"expires_at":iso(expiry)})

@app.get("/api/fixtures")
def fixtures():
    if not API_FOOTBALL_KEY:
        return jsonify({"error":"Clé API-Football non configurée."}), 503
    mode=request.args.get("mode","today")
    params={"live":"all"} if mode=="live" else {"date":request.args.get("date",now().strftime("%Y-%m-%d")),"timezone":"Africa/Abidjan"}
    try:
        r=requests.get(FOOTBALL_BASE+"/fixtures",headers={"x-apisports-key":API_FOOTBALL_KEY},params=params,timeout=20)
        r.raise_for_status(); return jsonify(r.json())
    except requests.RequestException as e: return jsonify({"error":str(e)}),503

@app.get("/api/<kind>")
def football_detail(kind):
    if kind not in ("predictions","odds","statistics"):
        return jsonify({"error":"Endpoint inconnu."}),404
    if not API_FOOTBALL_KEY: return jsonify({"error":"Clé API-Football non configurée."}),503
    fixture=request.args.get("fixture","")
    if not fixture.isdigit(): return jsonify({"error":"Identifiant de match invalide."}),400
    path={"predictions":"/predictions","odds":"/odds","statistics":"/fixtures/statistics"}[kind]
    try:
        r=requests.get(FOOTBALL_BASE+path,headers={"x-apisports-key":API_FOOTBALL_KEY},params={"fixture":fixture},timeout=20)
        r.raise_for_status(); return jsonify(r.json())
    except requests.RequestException as e: return jsonify({"error":str(e)}),503

@app.get("/health")
def health(): return jsonify({"ok":True})

if __name__=="__main__":
    app.run(host="0.0.0.0",port=int(os.environ.get("PORT","10000")),debug=False)
