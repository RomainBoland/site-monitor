import sqlite3
from collections.abc import Iterator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, HttpUrl, field_validator

from site_monitor import db
from site_monitor.ssrf import UnsafeURLError, check_url_is_public


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Runs once at startup: make sure the table exists before serving requests.
    conn = db.connect(db.get_database_path())
    db.init_db(conn)
    conn.close()
    yield


app = FastAPI(title="site-monitor", lifespan=lifespan)


def get_conn() -> Iterator[sqlite3.Connection]:
    # One connection per request, always closed, even if the endpoint raises.
    conn = db.connect(db.get_database_path())
    try:
        yield conn
    finally:
        conn.close()


Conn = Annotated[sqlite3.Connection, Depends(get_conn)]


class TargetIn(BaseModel):
    # HttpUrl only accepts http/https, rejects malformed URLs and normalizes them
    # (lowercase host, trailing slash), so near-duplicates hit the UNIQUE constraint.
    url: HttpUrl

    @field_validator("url")
    @classmethod
    def no_credentials(cls, url: HttpUrl) -> HttpUrl:
        # Credentials would be stored in plain text and later exposed in /metrics.
        if url.username or url.password:
            raise ValueError("URLs with credentials (user:password@) are not allowed")
        return url


class TargetOut(BaseModel):
    id: int
    url: str
    created_at: str


@app.get("/health")
def health() -> dict[str, str]:
    # Liveness only: answers "is the process up?". It must stay cheap and must not
    # depend on the monitored sites, or one slow site would make the container unhealthy.
    return {"status": "ok"}


@app.post("/targets", status_code=201)
def create_target(target: TargetIn, conn: Conn) -> TargetOut:
    url = str(target.url)
    try:
        check_url_is_public(url)
    except UnsafeURLError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    try:
        row = db.add_target(conn, url)
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="Target already exists") from None
    return TargetOut(**row)


@app.get("/targets")
def list_targets(conn: Conn) -> list[TargetOut]:
    return [TargetOut(**row) for row in db.list_targets(conn)]


@app.delete("/targets/{target_id}", status_code=204)
def delete_target(target_id: int, conn: Conn) -> None:
    if not db.delete_target(conn, target_id):
        raise HTTPException(status_code=404, detail="Target not found")
