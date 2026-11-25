from fastapi import FastAPI

app = FastAPI(title="site-monitor")


@app.get("/health")
def health() -> dict[str, str]:
    # Liveness only: answers "is the process up?". It must stay cheap and must not
    # depend on the monitored sites, or one slow site would make the container unhealthy.
    return {"status": "ok"}
