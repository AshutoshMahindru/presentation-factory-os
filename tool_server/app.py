from fastapi import FastAPI

app = FastAPI(title="PFOS Tool Server", version="3.2.4")

@app.get("/health")
def health():
    return {"service": "tool-server", "status": "ok"}
