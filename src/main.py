from fastapi import FastAPI
from workers import WorkerEntrypoint
import asgi

app = FastAPI()

DB = None


@app.get("/")
async def root():
    return {
        "status": "ok",
        "message": "FE Portal is running on Cloudflare Workers"
    }


@app.get("/db-test")
async def db_test():
    global DB

    if DB is None:
        return {
            "status": "error",
            "message": "D1 database is not connected"
        }

    result = await DB.prepare(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).all()

    tables = []

    for row in result.results:
        try:
            tables.append(row["name"])
        except Exception:
            tables.append(row.name)

    return {
        "status": "ok",
        "database": "connected",
        "tables": tables
    }


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        global DB
        DB = self.env.DB

        return await asgi.fetch(app, request, self.env)
