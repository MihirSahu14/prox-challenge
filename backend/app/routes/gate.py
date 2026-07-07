"""Optional access gate for hosted deployments.

When ACCESS_CODE is set, endpoints that spend the host's API credits require
a matching X-Access-Code header. No-op when unset (local dev, evaluator runs).
"""

import hmac

from fastapi import Header, HTTPException

from ..config import ACCESS_CODE


async def require_access_code(x_access_code: str | None = Header(default=None)) -> None:
    if not ACCESS_CODE:
        return
    if not x_access_code or not hmac.compare_digest(x_access_code, ACCESS_CODE):
        raise HTTPException(401, "Access code required")
