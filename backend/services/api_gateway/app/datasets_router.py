"""
Dataset list / get endpoints — replaces the Phase 0 stub with real Firestore-
backed reads.

Multi-tenancy v1: filter by principal.tenant_id. Phase 1.5 swaps in the
real tenant_access lookup.
"""
from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from services.api_gateway.app.auth import Principal, current_principal
from services.api_gateway.app.datasets import (
    Dataset,
    get_dataset as fs_get_dataset,
    list_datasets_for_tenant,
)

router = APIRouter(tags=["datasets"])


class DatasetListItem(BaseModel):
    id: str
    label: str
    locale_hint: Literal["US", "IN"]
    status: str
    row_count: int | None = None
    column_count: int | None = None
    last_refreshed: str
    scopes: list[str] = Field(default_factory=list)


@router.get("/v1/me/datasets", response_model=list[DatasetListItem])
def list_my_datasets(
    principal: Annotated[Principal, Depends(current_principal)],
) -> list[DatasetListItem]:
    items = list_datasets_for_tenant(principal.tenant_id)
    return [
        DatasetListItem(
            id=d.id,
            label=d.label,
            locale_hint=d.locale_hint,
            status=d.status,
            row_count=d.row_count,
            column_count=d.column_count,
            last_refreshed=d.updated_at,
        )
        for d in items
    ]


@router.get("/v1/datasets/{dataset_id}", response_model=Dataset)
def get_dataset(
    dataset_id: str,
    principal: Annotated[Principal, Depends(current_principal)],
) -> Dataset:
    d = fs_get_dataset(dataset_id)
    if d is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "dataset not found")
    if d.tenant_id != principal.tenant_id:
        # Don't leak existence; same 404 as missing
        raise HTTPException(status.HTTP_404_NOT_FOUND, "dataset not found")
    return d
