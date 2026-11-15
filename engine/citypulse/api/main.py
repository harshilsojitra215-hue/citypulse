"""CityPulse API. Run: .venv/bin/python -m uvicorn citypulse.api.main:app --host 127.0.0.1 --port 8000

The contract is docs/API_CONTRACT.md. Statistics come from the store (citypulse.engine.store); matching, replay and
cross-city retrieval are delegated to the engine; uploads to citypulse.batch; human verification to citypulse.review.
Errors always have the shape {"error": {"code": "...", "message": "..."}}.
"""
import logging, time

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .. import __version__
from .common import ApiError, log

if not logging.getLogger("citypulse").handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logging.getLogger("citypulse").addHandler(_h)
    logging.getLogger("citypulse").setLevel(logging.INFO)
    logging.getLogger("citypulse").propagate = False

app = FastAPI(title="CityPulse API", version=__version__,
              description="Public-debate and argument intelligence for city officials. Observable online debate, not a poll. "
                          "Accuracy numbers are provisional (agreement with AI reference labels, not human-validated).")

HTTP_CODES = {400: "bad_request", 401: "unauthorized", 403: "forbidden", 404: "not_found", 405: "method_not_allowed",
              409: "conflict", 413: "payload_too_large", 415: "unsupported_media_type", 422: "invalid_request", 503: "unavailable"}


def error_response(status: int, code: str, message: str, **extra) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message, **extra}})


@app.exception_handler(ApiError)
async def _api_error(request: Request, exc: ApiError):
    log.warning("handled error %s %s -> %s %s: %s", request.method, request.url.path, exc.status, exc.code, exc.message)
    return JSONResponse(status_code=exc.status, content=exc.body())


@app.exception_handler(StarletteHTTPException)
async def _http_error(request: Request, exc: StarletteHTTPException):
    detail = exc.detail
    if isinstance(detail, dict) and isinstance(detail.get("error"), dict):       # already in the contract shape
        body = detail
    else:
        code = HTTP_CODES.get(exc.status_code, f"http_{exc.status_code}")
        msg = detail if isinstance(detail, str) else str(detail)
        if exc.status_code == 404 and msg == "Not Found":
            msg = f"No such endpoint: {request.method} {request.url.path}. See /docs for the list."
        body = {"error": {"code": code, "message": msg}}
    log.warning("handled error %s %s -> %s %s", request.method, request.url.path, exc.status_code, body["error"].get("code"))
    return JSONResponse(status_code=exc.status_code, content=body, headers=getattr(exc, "headers", None))


@app.exception_handler(RequestValidationError)
async def _validation_error(request: Request, exc: RequestValidationError):
    parts = []
    for e in exc.errors():
        loc = ".".join(str(x) for x in e.get("loc", []) if x not in ("query", "body", "path"))
        parts.append(f"{loc or 'request'}: {e.get('msg')}")
    msg = "Invalid request: " + "; ".join(parts)
    log.warning("handled error %s %s -> 422 invalid_request: %s", request.method, request.url.path, msg)
    return error_response(422, "invalid_request", msg, fields=[{"field": ".".join(str(x) for x in e.get("loc", [])), "problem": e.get("msg")} for e in exc.errors()])


@app.middleware("http")
async def _log_requests(request: Request, call_next):
    """One log line per request; an unexpected exception becomes a contract-shaped 500 (inside CORS, so the browser can read it)."""
    t0 = time.perf_counter()
    line = f"{request.method} {request.url.path}" + (f"?{request.url.query}" if request.url.query else "")
    try:
        response = await call_next(request)
    except Exception as exc:
        log.exception("unhandled error on %s", line)
        response = error_response(500, "internal_error", f"Unexpected server error ({type(exc).__name__}). It was logged on the server.")
    log.info("%s -> %s (%.0f ms)", line, response.status_code, (time.perf_counter() - t0) * 1000)
    return response


# added after the logging middleware, so CORS is the outermost layer and also covers error answers
# any port on this machine: the web app may start on 3001 when 3000 is busy; nothing outside localhost is allowed
app.add_middleware(CORSMiddleware, allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:\d+)?", allow_methods=["*"],
                   allow_headers=["*"], expose_headers=["Content-Disposition"])


def _include(module: str, attr: str = "router", required: bool = False):
    """Include a router. A router owned by another builder must never stop the API from starting."""
    try:
        import importlib
        app.include_router(getattr(importlib.import_module(module), attr))
        log.info("router %s included", module)
        return True
    except Exception as e:
        if required:
            raise
        log.warning("router %s not included: %r", module, e)
        return False


# order matters: fixed paths (/api/batches/template, /api/replay/cutoffs) are declared before their {id} siblings inside each module
_include("citypulse.api.routes_engine", required=True)
_include("citypulse.api.routes_batch", required=True)
_include("citypulse.api.routes_export", required=True)
_include("citypulse.api.routes_data", required=True)
REVIEW_INCLUDED = _include("citypulse.review")


@app.get("/api", tags=["status"])
def index():
    """List of the endpoints this server answers."""
    routes = sorted((path, method.upper()) for path, ops in app.openapi()["paths"].items() if path.startswith("/api")
                    for method in ops if method in ("get", "post", "put", "patch", "delete"))
    return {"name": "CityPulse API", "version": __version__, "docs": "/docs", "review_router": REVIEW_INCLUDED,
            "endpoints": [{"method": m, "path": p} for p, m in routes]}
