from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import reconcile, validate, decisions, cases, events

app = FastAPI(title="EHR Reconciliation Engine", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(reconcile.router, prefix="/api")
app.include_router(validate.router, prefix="/api")
app.include_router(decisions.router, prefix="/api")
app.include_router(cases.router, prefix="/api")
app.include_router(events.router, prefix="/api")


@app.get("/health")
def health():
    return {"status": "ok"}
