import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import models
from app.db import Base, engine, get_db

CRON_SECRET = os.environ.get("CRON_SECRET")


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="Facturas Amazon", lifespan=lifespan)


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
    return {"status": "pendiente", "detalle": "Módulo de Carga (3.1) aún no implementado"}
