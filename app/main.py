from fastapi import FastAPI

app = FastAPI(title="Internship Radar")


@app.get("/")
def read_root() -> dict[str, str]:
    return {"message": "Internship Radar is running"}
