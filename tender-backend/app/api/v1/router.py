from fastapi import APIRouter

from app.api.v1 import (
    admin,
    auth,
    categories,
    schedules,
    searches,
    sites,
    tenders,
    users,
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(admin.router)
api_router.include_router(categories.router)
api_router.include_router(sites.router)
api_router.include_router(tenders.router)
api_router.include_router(searches.router)
api_router.include_router(schedules.router)
