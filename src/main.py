"""FE Portal D1 migration, stage 1: secure login and employee portal shell.
Requires D1 binding DB and Worker secret SESSION_SECRET.
Do not use as a full replacement for original sift.py functionality yet.
"""
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from workers import WorkerEntrypoint
import asgi
import hmac
import hashlib
import base64
import time
from html import escape

app = FastAPI()
DB = None
SESSION_SECRET = None
COOKIE = 'fe_session'


def page(title, body):
    return HTMLResponse('<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+escape(title)+'</title><style>body{font-family:system-ui,sans-serif;max-width:540px;margin:48px auto;padding:0 20px;color:#222}input,button{box-sizing:border-box;width:100%;padding:13px;margin:8px 0;font-size:16px}button{background:#1565c0;color:white;border:0;border-radius:7px}a{color:#1565c0}.card{padding:22px;border:1px solid #ddd;border-radius:12px}</style><h1>FE Portal</h1>'+body+'</html>')


def sign(data):
    return hmac.new(SESSION_SECRET.encode(), data.encode(), hashlib.sha256).hexdigest()


def make_token(uid):
    data = str(uid) + ':' + str(int(time.time()) + 12 * 3600)
    raw = data + ':' + sign(data)
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip('=')


def parse_token(token):
    if not SESSION_SECRET or not token:
        return None
    try:
        raw = base64.urlsafe_b64decode(token + '=' * (-len(token) % 4)).decode()
        uid, expiry, signature = raw.rsplit(':', 2)
        data = uid + ':' + expiry
        if int(expiry) < int(time.time()) or not hmac.compare_digest(signature, sign(data)):
            return None
        return uid
    except (ValueError, TypeError, UnicodeError):
        return None


async def current_user(request):
    uid = parse_token(request.cookies.get(COOKIE))
    if not uid or DB is None:
        return None
    result = await DB.prepare('SELECT id,login_id,name,is_admin,status FROM users WHERE id = ?').bind(uid).first()
    return result


def field(row, key):
    try:
        return row[key]
    except (KeyError, TypeError):
        return getattr(row, key, None)


@app.get('/', response_class=HTMLResponse)
async def index(request: Request):
    if await current_user(request):
        return RedirectResponse('/portal', status_code=303)
    return page('ログイン', '<div class="card"><h2>ログイン</h2><form action="/login" method="post"><label>ログインID<input name="login_id" required autocomplete="username"></label><label>パスワード<input name="password" type="password" required autocomplete="current-password"></label><button>ログイン</button></form></div>')


@app.post('/login')
async def login(login_id: str = Form(...), password: str = Form(...)):
    if DB is None or not SESSION_SECRET:
        return page('設定エラー', '<p>データベースまたはSESSION_SECRETが未設定です。</p>')
    result = await DB.prepare('SELECT id,password FROM users WHERE login_id = ?').bind(login_id).first()
    expected = field(result, 'password') if result else None
    if expected is None or not hmac.compare_digest(str(expected), password):
        return page('ログイン失敗', '<p>ログインIDまたはパスワードが違います。</p><a href="/">戻る</a>')
    response = RedirectResponse('/portal', status_code=303)
    response.set_cookie(COOKIE, make_token(field(result, 'id')), max_age=12*3600, httponly=True, secure=True, samesite='lax', path='/')
    return response


@app.get('/portal', response_class=HTMLResponse)
async def portal(request: Request):
    user = await current_user(request)
    if not user:
        return RedirectResponse('/', status_code=303)
    name = escape(str(field(user, 'name') or 'ユーザー'))
    return page('マイページ', '<div class="card"><h2>'+name+'さん、ようこそ</h2><p>D1から従業員情報を取得できました。</p><p>シフト提出・管理機能は移植途中です。</p><a href="/logout">ログアウト</a></div>')


@app.get('/logout')
async def logout():
    response = RedirectResponse('/', status_code=303)
    response.delete_cookie(COOKIE, path='/')
    return response


@app.get('/db-test')
async def db_test():
    if DB is None:
        return JSONResponse({'status':'error','message':'D1 database is not connected'}, status_code=503)
    result = await DB.prepare('SELECT COUNT(*) AS n FROM users').first()
    return {'status':'ok','database':'connected','user_count':field(result,'n')}


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        global DB, SESSION_SECRET
        DB = self.env.DB
        SESSION_SECRET = getattr(self.env, 'SESSION_SECRET', None)
        return await asgi.fetch(app, request, self.env)
