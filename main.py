from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def read_root():
    return {"message": "OK"}

# Для отладки: выводим в консоль
print("Server is starting on port", os.environ.get("PORT", "unknown"))
import os
