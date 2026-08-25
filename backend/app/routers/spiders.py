from fastapi import APIRouter, Depends

from ..composition import app_services
from ..core.response import APIEnvelope, APIResponse, ErrorEnvelope
from ..models.responses import ScraperCommandData, ScraperConfigData, ScraperRuntimeData, ScrapersData
from ..models.operations import RunScraperRequest, ScraperConfigRequest
from .auth import get_current_user


router = APIRouter(responses={400: {"model": ErrorEnvelope}, 422: {"model": ErrorEnvelope}, 500: {"model": ErrorEnvelope}})


@router.post("/spiders/run/{name}", status_code=202, response_model=APIEnvelope[ScraperCommandData])
async def run_spider(name: str, req: RunScraperRequest, user: str = Depends(get_current_user)):
    result = await app_services.scraper_commands.request_run(name, req.items)
    return APIResponse.success(data=result, message=result["message"], code=202)


@router.post("/spiders/stop/{name}", status_code=202, response_model=APIEnvelope[ScraperCommandData])
async def stop_scraper(name: str, user: str = Depends(get_current_user)):
    result = await app_services.scraper_commands.request_stop(name)
    return APIResponse.success(data=result, message=result["message"], code=202)


@router.get("/spiders/commands/{command_id}", response_model=APIEnvelope[ScraperCommandData])
def get_scraper_command(command_id: int, user: str = Depends(get_current_user)):
    return APIResponse.success(data=app_services.scraper_commands.get_command(command_id))


@router.get("/spiders", response_model=APIEnvelope[ScrapersData])
def get_spiders(user: str = Depends(get_current_user)):
    return APIResponse.success(data=app_services.scraper_runtime_state.get_spiders())


@router.get("/spiders/status", response_model=APIEnvelope[dict[str, ScraperRuntimeData]])
def get_spider_status(user: str = Depends(get_current_user)):
    return APIResponse.success(data=app_services.scraper_runtime_state.get_spider_status())


@router.post("/spiders/config/{name}", response_model=APIEnvelope[ScraperConfigData])
def config_scraper(name: str, req: ScraperConfigRequest, user: str = Depends(get_current_user)):
    return APIResponse.success(
        data=app_services.scraper_runtime_state.update_scraper_config(name, req.interval, req.limit)
    )
