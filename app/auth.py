import os
import secrets

from fastapi import Depends, HTTPException
from fastapi.security import HTTPBasic, HTTPBasicCredentials

APP_TOKEN = os.environ.get("APP_TOKEN")
security = HTTPBasic()


def verificar_credenciales(credentials: HTTPBasicCredentials = Depends(security)):
    if not APP_TOKEN or not secrets.compare_digest(credentials.password, APP_TOKEN):
        raise HTTPException(
            status_code=401,
            detail="No autorizado",
            headers={"WWW-Authenticate": "Basic"},
        )
