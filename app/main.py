import os

from fastapi import FastAPI, Header, HTTPException

app = FastAPI(title="Facturas Amazon")

CRON_SECRET = os.environ.get("CRON_SECRET")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/descarga-mensual")
def descarga_mensual(x_cron_secret: str = Header(default=None)):
    if not CRON_SECRET or x_cron_secret != CRON_SECRET:
        raise HTTPException(status_code=401, detail="No autorizado")
    return {"status": "pendiente", "detalle": "Módulo de conexión (3.1) aún no implementado"}
