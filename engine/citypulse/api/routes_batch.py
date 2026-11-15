"""Upload endpoints. All processing is done by citypulse.batch (another module); this file only receives the file and
passes answers on. If the batch module cannot be imported the answer is HTTP 503 {"error": {"code": "batch_unavailable"}}."""
import os, re, tempfile

from fastapi import APIRouter, File, UploadFile

from .common import ApiError, S, batch_module, clean, log

router = APIRouter(prefix="/api")
MAX_UPLOAD_BYTES = int(os.environ.get("CITYPULSE_MAX_UPLOAD_MB", "100")) * 1024 * 1024


def _call(fn: str, *args):
    b = batch_module()
    try:
        return getattr(b, fn)(*args)
    except ApiError:
        raise
    except Exception as e:
        dup = getattr(b, "DuplicateUpload", None)
        if dup is not None and isinstance(e, dup):
            raise
        for name, status, code in (("InvalidUpload", 422, "invalid_upload"), ("UnknownRun", 404, "unknown_run")):
            cls = getattr(b, name, None)
            if cls is not None and isinstance(e, cls):
                raise ApiError(status, code, str(e))
        if isinstance(e, (KeyError, FileNotFoundError)) and fn == "get_run":
            raise ApiError(404, "unknown_run", f"No batch run with id '{args[0]}'.")
        log.exception("batch call %s failed", fn)
        raise ApiError(503, "batch_unavailable", f"The batch processor failed in {fn}: {type(e).__name__}: {e}")


def _safe(st_getter=S):
    try:
        return st_getter()
    except Exception:
        return None


@router.post("/batches", tags=["batches"])
async def upload(file: UploadFile = File(..., description="JSON array or CSV of posts")):
    b = batch_module()                      # fail early with 503 before reading the upload
    filename = os.path.basename(file.filename or "upload")
    data = await file.read()
    if not data:
        raise ApiError(422, "empty_file", "The uploaded file is empty.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise ApiError(413, "file_too_large", f"The file has {len(data)} bytes; the limit is {MAX_UPLOAD_BYTES}.")
    suffix = re.sub(r"[^A-Za-z0-9.]", "", os.path.splitext(filename)[1])[:10]
    fd, path = tempfile.mkstemp(prefix="citypulse_upload_", suffix=suffix)
    with os.fdopen(fd, "wb") as fh:
        fh.write(data)
    try:
        run = _call("submit", path, filename)
    except Exception as e:
        dup = getattr(b, "DuplicateUpload", None)
        if dup is not None and isinstance(e, dup):
            run_id = getattr(e, "run_id", None)
            raise ApiError(409, "duplicate_upload", f"This exact file was already uploaded (run {run_id}). Open that run instead of processing it again.", run_id=run_id)
        raise
    log.info("upload %s (%d bytes) -> run %s", filename, len(data), (run or {}).get("run_id") if isinstance(run, dict) else run)
    return clean(run, _safe())


@router.get("/batches", tags=["batches"])
def runs():
    out = clean(_call("list_runs"), _safe())
    return out if isinstance(out, dict) and "runs" in out else {"runs": out or []}


@router.get("/batches/template", tags=["batches"])
def template():
    # the template documents the upload format, which may contain an `author` column (hashed on ingest, never stored or shown)
    return clean(_call("template"), drop=())


@router.get("/batches/{run_id}", tags=["batches"])
def run(run_id: str):
    out = _call("get_run", run_id)
    if out is None:
        raise ApiError(404, "unknown_run", f"No batch run with id '{run_id}'.")
    return clean(out, _safe())
