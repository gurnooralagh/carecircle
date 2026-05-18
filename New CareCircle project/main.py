from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import auth, onboarding, documents, longitudinal, dashboard

app = FastAPI(title="CareCircle Onboarding API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(auth.router)
app.include_router(onboarding.router)
app.include_router(documents.router)
app.include_router(longitudinal.router)
app.include_router(dashboard.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
