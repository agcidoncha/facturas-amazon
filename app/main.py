import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import models
from app.carga import router as carga_router
from app.db import Base, engine, get_db
from app.vista import router as vista_router

CRON_SECRET = os.environ.get("CRON_SECRET")


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="Facturas Amazon", lifespan=lifespan)
app.include_router(carga_router)
app.include_router(vista_router)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/health/db")
def health_db(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"status": "ok", "tablas": list(Base.metadata.tables.keys())}


@app.post("/api/descarga-mensual")
def descarga_mensual(x_cron_secret: str = Header(default=None)):
    if not CRON_SECRET or x_cron_secret != CRON_SECRET:
        raise HTTPException(status_code=401, detail="No autorizado")
    # No existe descarga automática desde Amazon (sección 3.1 revisada): la SP-API
    # no expone estas facturas. Este disparador mensual queda como recordatorio.
    return {"status": "recordatorio", "detalle": "Toca subir manualmente las facturas del mes en /subir"}
