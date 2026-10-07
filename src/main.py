from fastapi import FastAPI
from workers import WorkerEntrypoint
import asgi

app = FastAPI()


@app.get("/")
async def root():
    return {
        "status": "ok",
        "message": "FE Portal is running on Cloudflare Workers"
    }


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        return await asgi.fetch(app, request, self.env)
