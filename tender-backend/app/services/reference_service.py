"""CRUD for the reference tables: categories and sites.

Both are simple named lookups with a unique name, so the logic is shared.
"""

from typing import TypeVar

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.category import Category
from app.models.site import Site

ModelT = TypeVar("ModelT", Category, Site)


class NameAlreadyExists(Exception):
    """Raised when a create or update would duplicate an existing name."""


class NotFound(Exception):
    """Raised when the requested row does not exist."""


async def _name_taken(
    db: AsyncSession, model: type[ModelT], name: str, exclude_id: int | None = None
) -> bool:
    stmt = select(model.id).where(func.lower(model.name) == name.strip().lower())
    if exclude_id is not None:
        stmt = stmt.where(model.id != exclude_id)
    return (await db.execute(stmt.limit(1))).scalar_one_or_none() is not None


async def list_all(
    db: AsyncSession, model: type[ModelT], *, active_only: bool = False
) -> list[ModelT]:
    stmt = select(model).order_by(model.name)
    if active_only and model is Site:
        stmt = stmt.where(Site.active.is_(True))
    return list((await db.execute(stmt)).scalars().all())


async def get_one(db: AsyncSession, model: type[ModelT], row_id: int) -> ModelT:
    row = await db.get(model, row_id)
    if row is None:
        raise NotFound()
    return row


async def create(db: AsyncSession, model: type[ModelT], data: dict) -> ModelT:
    if await _name_taken(db, model, data["name"]):
        raise NameAlreadyExists()
    row = model(**data)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def update(
    db: AsyncSession, model: type[ModelT], row_id: int, data: dict
) -> ModelT:
    row = await get_one(db, model, row_id)

    if "name" in data and await _name_taken(db, model, data["name"], exclude_id=row_id):
        raise NameAlreadyExists()

    for field, value in data.items():
        setattr(row, field, value)

    await db.commit()
    await db.refresh(row)
    return row


async def delete(db: AsyncSession, model: type[ModelT], row_id: int) -> None:
    row = await get_one(db, model, row_id)
    await db.delete(row)
    await db.commit()
