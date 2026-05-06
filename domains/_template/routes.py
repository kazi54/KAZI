"""Domain routes — auto-mounted by the KAZI plugin loader.

Define your domain-specific API endpoints here.
The `router` attribute is required — the plugin loader imports it.
"""

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health():
    """Health check for this domain."""
    return {"status": "ok", "domain": "my-domain"}


# Add your domain-specific endpoints below:
# @router.post("/engagements")
# async def create_engagement(...):
#     ...
