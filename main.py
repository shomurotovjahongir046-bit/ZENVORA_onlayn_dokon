import os, sqlite3, secrets, hashlib, hmac, json, time
from pathlib import Path
from typing import Optional
from contextlib import contextmanager
from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, EmailStr

ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "static"
DB_PATH = os.getenv("DATABASE_PATH", str(ROOT / "commerce.db"))
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
SESSION_DAYS = int(os.getenv("SESSION_DAYS", "14"))

app = FastAPI(title="ZENVORA Store API", version="2.0.0", description="ZENVORA onlayn do'koni API")

@contextmanager
def db():
    # WAL + busy_timeout help short concurrent reads/writes, but SQLite is not
    # the recommended database for a high-volume production shop.
    conn = sqlite3.connect(DB_PATH, timeout=30, isolation_level="DEFERRED")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=30000")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def init_db():
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    with db() as c:
        c.execute("PRAGMA journal_mode=WAL")
        c.executescript("""
        CREATE TABLE IF NOT EXISTS products(
          id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, category TEXT NOT NULL,
          price INTEGER NOT NULL CHECK(price >= 0), old_price INTEGER, badge TEXT DEFAULT 'TAVSIYA',
          rating REAL DEFAULT 4.8, image TEXT DEFAULT '', description TEXT DEFAULT '', created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_products_category ON products(category);
        CREATE INDEX IF NOT EXISTS idx_products_name ON products(name);
        CREATE TABLE IF NOT EXISTS users(
          id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, email TEXT UNIQUE NOT NULL,
          password_hash TEXT NOT NULL, salt TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS sessions(
          token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          expires_at INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_sessions_expiry ON sessions(expires_at);
        CREATE TABLE IF NOT EXISTS orders(
          id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
          customer_name TEXT NOT NULL, phone TEXT NOT NULL, address TEXT NOT NULL, note TEXT DEFAULT '',
          items_json TEXT NOT NULL, total INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'Yangi',
          created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_orders_user ON orders(user_id, id DESC);
        CREATE INDEX IF NOT EXISTS idx_orders_created ON orders(id DESC);
        """)
        if c.execute("SELECT COUNT(*) FROM products").fetchone()[0] == 0:
            seed = [
              ("Nova X Pro smartfon","Telefonlar",3899000,4299000,"TOP TANLOV",4.9,"https://images.unsplash.com/photo-1592899677977-9c10ca588bbd?auto=format&fit=crop&w=700&q=80","Kundalik foydalanish, surat va videolar uchun zamonaviy smartfon."),
              ("AirBook Slim 14","Noutbuklar",7499000,7999000,"YANGI",4.8,"https://images.unsplash.com/photo-1496181133206-80ce9b88a853?auto=format&fit=crop&w=700&q=80","Yengil, ixcham va o‘qish hamda ish uchun qulay noutbuk."),
              ("Studio simsiz quloqchin","Aksessuarlar",459000,529000,"-13%",4.7,"https://images.unsplash.com/photo-1505740420928-5e560c06d30e?auto=format&fit=crop&w=700&q=80","Kundalik tinglash uchun qulay simsiz quloqchin."),
              ("4K Smart televizor 55″","TV va uy",5299000,5799000,"CHEGIRMA",4.9,"https://images.unsplash.com/photo-1593359677879-a4bb92f829d1?auto=format&fit=crop&w=700&q=80","Yorqin tasvir va sevimli kontentingiz uchun katta ekran."),
              ("Minimal smart soat","Aksessuarlar",699000,799000,"TOP",4.6,"https://images.unsplash.com/photo-1523275335684-37898b6baf30?auto=format&fit=crop&w=700&q=80","Vaqt va kundalik bildirishnomalar uchun zamonaviy soat."),
              ("ProBook 15 noutbuk","Noutbuklar",8999000,None,"YANGI",4.8,"https://images.unsplash.com/photo-1517336714731-489689fd1ca8?auto=format&fit=crop&w=700&q=80","Ko‘p vazifali ishlar va o‘qish uchun noutbuk."),
              ("Mobil quvvatlagich 20K","Aksessuarlar",249000,299000,"-17%",4.5,"https://images.unsplash.com/photo-1609091839311-d5365f9ff1c5?auto=format&fit=crop&w=700&q=80","Safarda qurilmalaringizni quvvatlantirish uchun ixcham aksessuar."),
              ("Smartfon Lite","Telefonlar",2199000,None,"QULAY NARX",4.6,"https://images.unsplash.com/photo-1511707171634-5f897ff02aa9?auto=format&fit=crop&w=700&q=80","Asosiy vazifalar va kundalik aloqa uchun qulay telefon.")]
            c.executemany("INSERT INTO products(name,category,price,old_price,badge,rating,image,description) VALUES(?,?,?,?,?,?,?,?)", seed)

init_db()

def rowdict(row): return dict(row) if row else None
def public_user(row): return {"id": row["id"], "name": row["name"], "email": row["email"]} if row else None
def hash_password(password: str, salt: Optional[str] = None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 240000).hex()
    return salt, digest
def verify_password(password, salt, digest):
    return hmac.compare_digest(hash_password(password, salt)[1], digest)
def token_hash(token): return hashlib.sha256(token.encode()).hexdigest()
def create_session(user_id):
    token = secrets.token_urlsafe(36)
    with db() as c:
        c.execute("DELETE FROM sessions WHERE expires_at <= ?", (int(time.time()),))
        c.execute("INSERT INTO sessions(token_hash,user_id,expires_at) VALUES(?,?,?)", (token_hash(token), user_id, int(time.time()) + 60*60*24*SESSION_DAYS))
    return token

def current_user(authorization: Optional[str] = Header(default=None)):
    if not authorization or not authorization.startswith("Bearer "): return None
    with db() as c:
        row = c.execute("SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=? AND s.expires_at>?", (token_hash(authorization[7:]), int(time.time()))).fetchone()
    return rowdict(row)
def require_user(user=Depends(current_user)):
    if not user: raise HTTPException(401, "Davom etish uchun akkauntga kiring.")
    return user
def require_admin(x_admin_token: Optional[str] = Header(default=None)):
    if not ADMIN_EMAIL or not ADMIN_PASSWORD:
        raise HTTPException(503, "Admin sozlanmagan. Hosting muhitida ADMIN_EMAIL va ADMIN_PASSWORD ni belgilang.")
    expected = hashlib.sha256((ADMIN_EMAIL + ":" + ADMIN_PASSWORD).encode()).hexdigest()
    if not x_admin_token or not hmac.compare_digest(x_admin_token, expected):
        raise HTTPException(401, "Admin ma’lumotlari noto‘g‘ri.")
    return True

class AuthIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    name: str = Field(default="", max_length=80)
class ProductIn(BaseModel):
    name: str = Field(min_length=2, max_length=180)
    category: str = Field(min_length=2, max_length=60)
    price: int = Field(ge=0)
    old_price: Optional[int] = Field(default=None, ge=0)
    badge: str = Field(default="TAVSIYA", max_length=40)
    image: str = Field(default="", max_length=1000)
    description: str = Field(default="", max_length=2000)
class OrderItem(BaseModel):
    product_id: int = Field(gt=0)
    quantity: int = Field(ge=1, le=50)
class OrderIn(BaseModel):
    customer_name: str = Field(min_length=2, max_length=100)
    phone: str = Field(min_length=7, max_length=40)
    address: str = Field(min_length=5, max_length=500)
    note: str = Field(default="", max_length=1000)
    items: list[OrderItem] = Field(min_length=1, max_length=50)
class StatusIn(BaseModel): status: str

@app.get("/")
def home():
    index = STATIC_DIR / "index.html"
    if not index.exists(): raise HTTPException(404, "static/index.html topilmadi")
    return FileResponse(index)
@app.get("/api/health")
def health(): return {"status": "ok", "service": "zenvora-api"}
@app.get("/api/products")
def get_products(q: str = "", category: str = "", limit: int = Field(default=100, ge=1, le=500), offset: int = Field(default=0, ge=0)):
    sql = "SELECT * FROM products WHERE 1=1"; args = []
    if q.strip():
        term = "%" + q.strip().replace("%", "\\%").replace("_", "\\_") + "%"
        sql += " AND (name LIKE ? ESCAPE '\\' OR category LIKE ? ESCAPE '\\' OR description LIKE ? ESCAPE '\\')"; args += [term, term, term]
    if category.strip(): sql += " AND category = ?"; args.append(category.strip())
    sql += " ORDER BY id DESC LIMIT ? OFFSET ?"; args += [limit, offset]
    with db() as c: rows = c.execute(sql, args).fetchall()
    return [rowdict(r) for r in rows]
@app.post("/api/register")
def register(data: AuthIn):
    email = str(data.email).lower().strip(); salt, digest = hash_password(data.password)
    name = data.name.strip() or email.split("@")[0]
    try:
        with db() as c:
            cur = c.execute("INSERT INTO users(name,email,password_hash,salt) VALUES(?,?,?,?)", (name, email, digest, salt)); uid = cur.lastrowid
    except sqlite3.IntegrityError: raise HTTPException(409, "Bu email bilan akkaunt mavjud.")
    return {"access_token": create_session(uid), "user": {"id": uid, "name": name, "email": email}}
@app.post("/api/login")
def login(data: AuthIn):
    with db() as c: row = c.execute("SELECT * FROM users WHERE email=?", (str(data.email).lower().strip(),)).fetchone()
    if not row or not verify_password(data.password, row["salt"], row["password_hash"]): raise HTTPException(401, "Email yoki parol noto‘g‘ri.")
    return {"access_token": create_session(row["id"]), "user": public_user(row)}
@app.get("/api/me")
def me(user=Depends(require_user)): return public_user(user)
@app.post("/api/logout")
def logout(authorization: Optional[str] = Header(default=None)):
    if authorization and authorization.startswith("Bearer "):
        with db() as c: c.execute("DELETE FROM sessions WHERE token_hash=?", (token_hash(authorization[7:]),))
    return {"ok": True}
@app.post("/api/orders")
def create_order(data: OrderIn, user=Depends(current_user)):
    items = []; total = 0
    # One transaction ensures products are checked and the order is saved together.
    with db() as c:
        for item in data.items:
            p = c.execute("SELECT id,name,price FROM products WHERE id=?", (item.product_id,)).fetchone()
            if not p: raise HTTPException(400, f"Mahsulot topilmadi: {item.product_id}")
            total += int(p["price"]) * item.quantity
            items.append({"product_id": p["id"], "name": p["name"], "price": p["price"], "quantity": item.quantity})
        cur = c.execute("INSERT INTO orders(user_id,customer_name,phone,address,note,items_json,total) VALUES(?,?,?,?,?,?,?)", (user["id"] if user else None, data.customer_name.strip(), data.phone.strip(), data.address.strip(), data.note.strip(), json.dumps(items, ensure_ascii=False), total))
        order_id = cur.lastrowid
    return {"id": order_id, "total": total, "status": "Yangi"}
@app.post("/api/admin/login")
def admin_login(data: AuthIn):
    if not ADMIN_EMAIL or not ADMIN_PASSWORD: raise HTTPException(503, "Admin hosting muhitida sozlanmagan.")
    if str(data.email).lower().strip() != ADMIN_EMAIL.lower() or not hmac.compare_digest(data.password, ADMIN_PASSWORD): raise HTTPException(401, "Admin email yoki paroli noto‘g‘ri.")
    return {"token": hashlib.sha256((ADMIN_EMAIL + ":" + ADMIN_PASSWORD).encode()).hexdigest()}
@app.get("/api/admin/products")
def admin_products(_=Depends(require_admin)):
    with db() as c: return [rowdict(r) for r in c.execute("SELECT * FROM products ORDER BY id DESC").fetchall()]
@app.post("/api/admin/products")
def add_product(data: ProductIn, _=Depends(require_admin)):
    with db() as c:
        cur = c.execute("INSERT INTO products(name,category,price,old_price,badge,image,description) VALUES(?,?,?,?,?,?,?)", (data.name.strip(), data.category.strip(), data.price, data.old_price, data.badge, data.image, data.description))
        row = c.execute("SELECT * FROM products WHERE id=?", (cur.lastrowid,)).fetchone()
    return rowdict(row)
@app.delete("/api/admin/products/{product_id}")
def delete_product(product_id: int, _=Depends(require_admin)):
    with db() as c:
        cur = c.execute("DELETE FROM products WHERE id=?", (product_id,))
        if not cur.rowcount: raise HTTPException(404, "Mahsulot topilmadi.")
    return {"ok": True}
@app.get("/api/admin/orders")
def admin_orders(_=Depends(require_admin)):
    with db() as c: rows = c.execute("SELECT * FROM orders ORDER BY id DESC LIMIT 2000").fetchall()
    result = []
    for r in rows:
        item = rowdict(r); item["items"] = json.loads(item.pop("items_json")); result.append(item)
    return result
@app.patch("/api/admin/orders/{order_id}")
def update_order(order_id: int, data: StatusIn, _=Depends(require_admin)):
    allowed = {"Yangi", "Jarayonda", "Yuborildi", "Yakunlandi", "Bekor qilindi"}
    if data.status not in allowed: raise HTTPException(400, "Holat noto‘g‘ri.")
    with db() as c:
        cur = c.execute("UPDATE orders SET status=? WHERE id=?", (data.status, order_id))
        if not cur.rowcount: raise HTTPException(404, "Buyurtma topilmadi.")
    return {"ok": True, "status": data.status}
@app.get("/api/profile")
def get_profile(user=Depends(current_user)):
    if not user: return {"name": "Mehmon", "email": "Tizimga kiritilmagan", "avatar": "/static/default-avatar.png"}
    return {"name": user["name"], "email": user["email"], "avatar": "/static/default-avatar.png"}
@app.get("/api/my-orders")
def get_my_orders(user=Depends(require_user)):
    with db() as c:
        orders = c.execute("SELECT id,total,status,created_at FROM orders WHERE user_id=? ORDER BY id DESC LIMIT 200", (user["id"],)).fetchall()
    return {"orders": [{"id": o["id"], "price": o["total"], "status": o["status"] or "Yangi", "date": o["created_at"]} for o in orders]}

app.mount("/static", StaticFiles(directory=STATIC_DIR, check_dir=True), name="static")

if __name__ == "__main__":
    import uvicorn
    # Use localhost for local development; production host runs the ASGI app itself.
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", "8000")), reload=False)
