# Jahongir Commerce

Zamonaviy, moslashuvchan Uzbek marketplace demo: HTML/CSS/JavaScript frontend + FastAPI backend + SQLite database.

## Nimalar bor
- Telefon, noutbuk, aksessuar va TV kategoriyalari
- Qidiruv, saralash, mahsulot tafsilotlari
- Savat va sevimlilar
- Ro‘yxatdan o‘tish/kirish (parollar PBKDF2-HMAC-SHA256 bilan xeshlanadi)
- Serverda buyurtmalar va serverdagi narxlar asosida hisoblash
- Admin login, mahsulot qo‘shish/o‘chirish, buyurtma holatini yangilash
- Moslashuvchan mobil dizayn va animatsiyalar

## Kompyuterda ishga tushirish (Windows)
1. Python 3.11+ o‘rnating.
2. Shu papkada terminal oching.
3. Buyruqlar:
   ```powershell
   py -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   copy .env.example .env
   ```
4. `.env` faylini ochib `ADMIN_EMAIL` va `ADMIN_PASSWORD` ni o‘zingizga mos, kuchli qiymatlarga almashtiring.
5. Ishga tushiring:
   ```powershell
   uvicorn main:app --reload
   ```
6. Sayt: http://127.0.0.1:8000  
   API hujjatlari: http://127.0.0.1:8000/docs

## Linux / macOS
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# .env ichida admin ma’lumotlarini sozlang
uvicorn main:app --reload
```

## Muhim sozlamalar va production
- `.env` faylini FastAPI avtomatik o‘qimaydi: hostingda `ADMIN_EMAIL` va `ADMIN_PASSWORD` ni environment variables sifatida kiriting. Lokal ishga tushirishdan oldin Windows PowerShell'da:
  ```powershell
  $env:ADMIN_EMAIL="admin@example.com"
  $env:ADMIN_PASSWORD="BU_YERGA_KUCHLI_PAROL"
  uvicorn main:app --reload
  ```
  Yoki `python-dotenv` qo‘shib `load_dotenv()` dan foydalaning.
- Public hostingga qo‘yish uchun HTTPS, environment variables, doimiy disk/production database, zaxira nusxa, rate limiting va monitoring sozlang.
- SQLite kichik demo uchun qulay; kattaroq loyiha uchun PostgreSQL tavsiya etiladi.
- Click/Payme to‘lovlari ulanmagan. Haqiqiy to‘lovni faqat rasmiy merchant hisob, server-side callback tekshiruvi va test rejimi bilan integratsiya qilish kerak.
- Hozirgi admin paneldagi token oddiy demo autentifikatsiyasi. Real savdoga chiqarishdan oldin admin session/JWT, CSRF/rate-limit va audit logni kuchaytiring.
- Rasm manbalari tashqi Unsplash URL'lari; offline rejimda ular ko‘rinmasligi mumkin.
