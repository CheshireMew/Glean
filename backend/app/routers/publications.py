from __future__ import annotations

from fastapi import APIRouter, Depends

from ..composition import app_services
from ..core.response import APIEnvelope, APIResponse, ErrorEnvelope
from ..models.intelligence import PublicationChannelRequest, PublicationUpdateRequest
from ..models.responses import PublicationChannelData, PublicationData
from .auth import get_current_user


router = APIRouter(
    responses={400: {"model": ErrorEnvelope}, 404: {"model": ErrorEnvelope}, 422: {"model": ErrorEnvelope}, 500: {"model": ErrorEnvelope}}
)


@router.get("/publications", response_model=APIEnvelope[list[PublicationData]])
def list_publications(user: str = Depends(get_current_user)):
    return APIResponse.success(data=app_services.publications.list_publications())


@router.patch("/publications/{publication_id}", response_model=APIEnvelope[PublicationData])
def update_publication(
    publication_id: int,
    request: PublicationUpdateRequest,
    user: str = Depends(get_current_user),
):
    return APIResponse.success(
        data=app_services.publications.update_publication(
            publication_id, request.model_dump(exclude_unset=True)
        )
    )


@router.get("/publication-channels", response_model=APIEnvelope[list[PublicationChannelData]])
def list_publication_channels(user: str = Depends(get_current_user)):
    return APIResponse.success(data=app_services.publications.list_channels())


@router.post("/publication-channels", response_model=APIEnvelope[PublicationChannelData])
def create_publication_channel(
    request: PublicationChannelRequest,
    user: str = Depends(get_current_user),
):
    return APIResponse.success(data=app_services.publications.save_channel(request.model_dump()))


@router.put("/publication-channels/{channel_id}", response_model=APIEnvelope[PublicationChannelData])
def update_publication_channel(
    channel_id: int,
    request: PublicationChannelRequest,
    user: str = Depends(get_current_user),
):
    return APIResponse.success(
        data=app_services.publications.save_channel(request.model_dump(), channel_id)
    )


@router.post("/publication-channels/{channel_id}/test", response_model=APIEnvelope[dict])
async def test_publication_channel(channel_id: int, user: str = Depends(get_current_user)):
    return APIResponse.success(
        data=await app_services.publication_channel_gateway.test_channel(channel_id)
    )
