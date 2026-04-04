from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes.metrics import router as metrics_router
from app.api.routes.sessions import router as sessions_router
from app.core.config import get_settings
from app.core.errors import AppError
from app.db.session import init_db

settings = get_settings()
app = FastAPI(title=settings.app_name, version='1.0.0')
init_db()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins(),
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)


@app.exception_handler(AppError)
async def handle_app_error(_: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={'code': exc.code, 'message': exc.message, 'details': exc.details},
    )


@app.get('/health')
def health() -> dict:
    return {'status': 'ok'}


app.include_router(sessions_router)
app.include_router(metrics_router)
