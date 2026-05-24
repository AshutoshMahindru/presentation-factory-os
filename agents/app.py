from fastapi import FastAPI

app = FastAPI(title="PFOS Agent Service", version="3.2.4")

@app.get("/health")
def health():
    return {"service": "agent-service", "status": "ok"}
