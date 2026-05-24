from fastapi import FastAPI

app = FastAPI(title="PFOS Retrieval Engine", version="3.2.4")

@app.get("/health")
def health():
    return {"service": "retrieval-engine", "status": "ok"}
