from fastapi import FastAPI

from routes import router


app = FastAPI(title="Docling Parser Service")
app.include_router(router)
