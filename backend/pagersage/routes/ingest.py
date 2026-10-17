"""POST /ingest/deploy and /ingest/config-change (task B10). Kestrel Pay's injector, like a
CD system, reports deploys and config changes here; it never touches FalkorDB."""

from fastapi import APIRouter

from pagersage import ingest
from pagersage.contracts.ingest import ConfigChangeIn, DeployIn, IngestResult

router = APIRouter(prefix="/ingest", tags=["ingest"])


@router.post("/deploy")
def post_deploy(body: DeployIn) -> IngestResult:
    return ingest.ingest_deploy(body)


@router.post("/config-change")
def post_config_change(body: ConfigChangeIn) -> IngestResult:
    return ingest.ingest_config_change(body)
