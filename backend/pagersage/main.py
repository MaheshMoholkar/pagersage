"""HTTP API: /health here, the rest in pagersage/routes/ (one module per area).

A ToolError (bad input the caller can fix, e.g. an unknown service id) becomes a 400 with
{"error": message}; a BrainError (no API key, or the Brain could not answer) a 503; validation
errors are FastAPI's usual 422.
"""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from redis.exceptions import RedisError

from pagersage import db
from pagersage.agents import orchestrator
from pagersage.agents.brain import BrainError
from pagersage.config import get_settings
from pagersage.contracts.tools import ToolError
from pagersage.routes import alerts, ask, graph, incidents, ingest, oncall

app = FastAPI(title="PagerSage API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origin_list,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(ingest.router)
app.include_router(alerts.router)
app.include_router(graph.router)
app.include_router(incidents.router)
app.include_router(ask.router)
app.include_router(oncall.router)
orchestrator.install()  # agents run on new and resolved incidents (needs ANTHROPIC_API_KEY)


@app.exception_handler(ToolError)
def tool_error(_: Request, exc: ToolError) -> JSONResponse:
    return JSONResponse(status_code=400, content={"error": str(exc)})


@app.exception_handler(BrainError)
def brain_error(_: Request, exc: BrainError) -> JSONResponse:
    return JSONResponse(status_code=503, content={"error": str(exc)})


@app.get("/health")
def health() -> JSONResponse:
    graph = get_settings().pagersage_graph
    try:
        db.ping()
    except (RedisError, OSError) as exc:
        return JSONResponse(
            status_code=503,
            content={
                "status": "degraded",
                "falkordb": "unreachable",
                "graph": graph,
                "error": type(exc).__name__,
            },
        )
    return JSONResponse({"status": "ok", "falkordb": "ok", "graph": graph})
