from fastapi import FastAPI
from starlette.requests import Request
from fastapi.responses import JSONResponse

from exceptions.sp_api_errors import SPAPIError, RetryableError, UnauthorizedError
from core.logging import configure_logging

configure_logging()

app = FastAPI(
    title="Amazon Vendor Core",
    version="1.0.0"
)

@app.exception_handler(SPAPIError)
async def spapi_exception_handler(request: Request, exc: SPAPIError):

    if isinstance(exc, RetryableError):
        return JSONResponse(
            status_code=503,
            content={
                "error": "temporary_failure",
                "reason": exc.reason,
                "retry_after": exc.retry_after
            }
        )

    if isinstance(exc, UnauthorizedError):
        return JSONResponse(
            status_code=401,
            content={
                "error": "unauthorized",
                "message": "Authentication failed"
            }
        )

    return JSONResponse(
        status_code=500,
        content={
            "error": "spapi_internal_error"
        }
    )

@app.get("/health")
def health_check():
    return {"status": "ok"}