from fastapi import FastAPI
from .catalog import EXPERTS, SKILLS
from .models import RouteRequest, RouteResponse
from .router import RuleRouter

app = FastAPI(title="Agent Router", version="0.1.0")
router = RuleRouter(EXPERTS, SKILLS)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/catalog")
def catalog() -> dict[str, list[object]]:
    return {"experts": EXPERTS, "skills": SKILLS}


@app.post("/route", response_model=RouteResponse)
def route(request: RouteRequest) -> RouteResponse:
    return router.route(request)
