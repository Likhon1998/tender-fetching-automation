from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.capabilities import MANAGE_CATEGORIES
from app.core.deps import CurrentUser, require_capability
from app.db.session import get_db
from app.models.category import Category
from app.schemas.category import CategoryCreate, CategoryResponse, CategoryUpdate
from app.services import reference_service as svc

router = APIRouter(prefix="/categories", tags=["categories"])

DbSession = Annotated[AsyncSession, Depends(get_db)]
CanManage = Depends(require_capability(MANAGE_CATEGORIES))


@router.get("", response_model=list[CategoryResponse], summary="List all categories")
async def list_categories(db: DbSession, current_user: CurrentUser) -> list[Category]:
    """Readable by any logged in user, since the dashboard filters by category."""
    return await svc.list_all(db, Category)


@router.get("/{category_id}", response_model=CategoryResponse, summary="Get a category")
async def get_category(
    category_id: int, db: DbSession, current_user: CurrentUser
) -> Category:
    try:
        return await svc.get_one(db, Category, category_id)
    except svc.NotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Category not found")


@router.post(
    "",
    response_model=CategoryResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[CanManage],
    summary="Create a category",
)
async def create_category(payload: CategoryCreate, db: DbSession) -> Category:
    try:
        return await svc.create(db, Category, payload.model_dump())
    except svc.NameAlreadyExists:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "A category with that name already exists"
        )


@router.patch(
    "/{category_id}",
    response_model=CategoryResponse,
    dependencies=[CanManage],
    summary="Update a category",
)
async def update_category(
    category_id: int, payload: CategoryUpdate, db: DbSession
) -> Category:
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No fields to update")
    try:
        return await svc.update(db, Category, category_id, changes)
    except svc.NotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Category not found")
    except svc.NameAlreadyExists:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "A category with that name already exists"
        )


@router.delete(
    "/{category_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[CanManage],
    summary="Delete a category",
)
async def delete_category(category_id: int, db: DbSession) -> Response:
    try:
        await svc.delete(db, Category, category_id)
    except svc.NotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Category not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
