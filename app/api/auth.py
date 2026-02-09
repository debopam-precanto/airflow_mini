from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader
from app import config

api_key_header = APIKeyHeader(name="X-API-Key")


async def verify_api_key(api_key: str = Security(api_key_header)):
    if api_key != config.API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return api_key
