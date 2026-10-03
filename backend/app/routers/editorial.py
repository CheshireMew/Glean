from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ..composition import app_services
from ..core.response import APIEnvelope, APIResponse, ErrorEnvelope
from ..models.intelligence import (
    CorrectionCreateRequest,
    DraftCreateRequest,
    DraftUpdateRequest,
    EditorialEditRequest,
    EditorialFeedbackRequest,
    EventUpdatePatchRequest,
    EventUpdateRequest,
    EventFactPatchRequest,
    EventFactRequest,
    EventRelationRequest,
    EvidenceUpdateRequest,
)
from ..models.responses import (
    EditorialEntryData,
    EventDetailData,
    MutationResultData,
    PublicationDraftData,
    PublicationDraftPreviewData,
)
from .auth import get_current_user


router = APIRouter(
    responses={
        400: {"model": ErrorEnvelope},
        404: {"model": ErrorEnvelope},
        409: {"model": ErrorEnvelope},
        422: {"model": ErrorEnvelope},
        500: {"model": ErrorEnvelope},
    }
)


@router.get("/editorial/entries/{entry_id}", response_model=APIEnvelope[EditorialEntryData])
def get_editorial_entry(entry_id: int, user: str = Depends(get_current_user)):
    return APIResponse.success(data=app_services.editorial_workbench.get_entry(entry_id))


@router.put("/editorial/entries/{entry_id}", response_model=APIEnvelope[EditorialEntryData])
def update_editorial_entry(
    entry_id: int,
    request: EditorialEditRequest,
    user: str = Depends(get_current_user),
):
    return APIResponse.success(
        data=app_services.editorial_workbench.update_entry(
            entry_id, request.model_dump(exclude_unset=True), user
        ),
        message="编辑内容已保存并生成修订记录",
    )


@router.post(
    "/editorial/entries/{entry_id}/revisions/{revision_number}/restore",
    response_model=APIEnvelope[EditorialEntryData],
)
def restore_editorial_revision(
    entry_id: int,
    revision_number: int,
    user: str = Depends(get_current_user),
):
    return APIResponse.success(
        data=app_services.editorial_workbench.restore_revision(entry_id, revision_number, user),
        message="已恢复指定修订并保留新的修订记录",
    )


@router.post(
    "/editorial/entries/{entry_id}/feedback",
    response_model=APIEnvelope[MutationResultData],
)
def add_editorial_feedback(
    entry_id: int,
    request: EditorialFeedbackRequest,
    user: str = Depends(get_current_user),
):
    return APIResponse.success(
        data=app_services.editorial_workbench.add_feedback(
            entry_id, request.model_dump(), user
        )
    )


@router.get("/editorial/events/{event_id}", response_model=APIEnvelope[EventDetailData])
def get_editorial_event(event_id: int, user: str = Depends(get_current_user)):
    return APIResponse.success(data=app_services.event_intelligence.get_detail(event_id))


@router.patch(
    "/editorial/events/{event_id}/sources/{news_id}/evidence",
    response_model=APIEnvelope[EventDetailData],
)
def update_event_source_evidence(
    event_id: int,
    news_id: int,
    request: EvidenceUpdateRequest,
    user: str = Depends(get_current_user),
):
    return APIResponse.success(
        data=app_services.event_intelligence.update_source_evidence(
            event_id, news_id, request.model_dump(exclude_unset=True)
        )
    )


@router.post(
    "/editorial/events/{event_id}/updates",
    response_model=APIEnvelope[MutationResultData],
)
def add_event_update(
    event_id: int,
    request: EventUpdateRequest,
    user: str = Depends(get_current_user),
):
    result = app_services.event_intelligence.add_update(event_id, request.model_dump(), user)
    return APIResponse.success(data={"id": result["id"]})


@router.patch(
    "/editorial/event-updates/{update_id}",
    response_model=APIEnvelope[MutationResultData],
)
def update_event_update(
    update_id: int,
    request: EventUpdatePatchRequest,
    user: str = Depends(get_current_user),
):
    return APIResponse.success(
        data=app_services.event_intelligence.update_event_update(
            update_id, request.model_dump(exclude_unset=True), user
        )
    )


@router.post(
    "/editorial/events/{event_id}/facts",
    response_model=APIEnvelope[MutationResultData],
)
def add_event_fact(
    event_id: int,
    request: EventFactRequest,
    user: str = Depends(get_current_user),
):
    result = app_services.event_intelligence.add_fact(event_id, request.model_dump(), user)
    return APIResponse.success(data={"id": result["id"]})


@router.patch(
    "/editorial/event-facts/{fact_id}",
    response_model=APIEnvelope[MutationResultData],
)
def update_event_fact(
    fact_id: int,
    request: EventFactPatchRequest,
    user: str = Depends(get_current_user),
):
    return APIResponse.success(
        data=app_services.event_intelligence.update_fact(
            fact_id, request.model_dump(exclude_unset=True), user
        )
    )


@router.post(
    "/editorial/events/{event_id}/relations",
    response_model=APIEnvelope[MutationResultData],
)
def add_event_relation(
    event_id: int,
    request: EventRelationRequest,
    user: str = Depends(get_current_user),
):
    result = app_services.event_intelligence.add_relation(
        event_id, request.model_dump(), user
    )
    return APIResponse.success(data={"id": result["id"]})


@router.get("/editorial/drafts", response_model=APIEnvelope[list[PublicationDraftData]])
def list_publication_drafts(
    status: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    user: str = Depends(get_current_user),
):
    return APIResponse.success(data=app_services.editorial_workbench.list_drafts(status, limit))


@router.post("/editorial/drafts", response_model=APIEnvelope[PublicationDraftData])
def create_publication_draft(
    request: DraftCreateRequest,
    user: str = Depends(get_current_user),
):
    return APIResponse.success(
        data=app_services.editorial_workbench.create_draft(request.model_dump(), user)
    )


@router.get("/editorial/drafts/{draft_id}", response_model=APIEnvelope[PublicationDraftData])
def get_publication_draft(draft_id: int, user: str = Depends(get_current_user)):
    return APIResponse.success(data=app_services.editorial_workbench.get_draft(draft_id))


@router.patch("/editorial/drafts/{draft_id}", response_model=APIEnvelope[PublicationDraftData])
def update_publication_draft(
    draft_id: int,
    request: DraftUpdateRequest,
    user: str = Depends(get_current_user),
):
    return APIResponse.success(
        data=app_services.editorial_workbench.update_draft(
            draft_id, request.model_dump(exclude_unset=True)
        )
    )


@router.get(
    "/editorial/drafts/{draft_id}/preview",
    response_model=APIEnvelope[PublicationDraftPreviewData],
)
def preview_publication_draft(draft_id: int, user: str = Depends(get_current_user)):
    return APIResponse.success(data=app_services.publication_workflow.preview_draft(draft_id))


@router.post("/editorial/drafts/{draft_id}/publish", response_model=APIEnvelope[dict])
async def publish_publication_draft(draft_id: int, website_only: bool = False, user: str = Depends(get_current_user)):
    return APIResponse.success(data=await app_services.publication_workflow.publish_draft(draft_id, website_only=website_only))


@router.post("/editorial/drafts/publish-due", response_model=APIEnvelope[dict])
async def publish_due_drafts(
    limit: int = Query(default=100, ge=1, le=500),
    user: str = Depends(get_current_user),
):
    return APIResponse.success(data=await app_services.publication_workflow.publish_due_drafts(limit))


@router.get("/editorial/corrections", response_model=APIEnvelope[list[dict]])
def list_publication_corrections(
    published: bool | None = None,
    limit: int = Query(default=200, ge=1, le=1000),
    user: str = Depends(get_current_user),
):
    return APIResponse.success(data=app_services.publication_workflow.list_corrections(published, limit))


@router.post("/editorial/corrections", response_model=APIEnvelope[MutationResultData])
def create_publication_correction(
    request: CorrectionCreateRequest,
    user: str = Depends(get_current_user),
):
    return APIResponse.success(
        data=app_services.editorial_workbench.add_correction(request.model_dump(), user)
    )


@router.post("/editorial/corrections/{correction_id}/publish", response_model=APIEnvelope[dict])
async def publish_publication_correction(correction_id: int, user: str = Depends(get_current_user)):
    return APIResponse.success(data=await app_services.publication_workflow.publish_correction(correction_id))
