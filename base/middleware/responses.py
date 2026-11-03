from fastapi import Request
from fastapi.responses import JSONResponse

from base.models.view_models import ErrorResponse
from base.services.common.meta import scope_id


def _error_response(_request: Request, message: str, status_code: int) -> JSONResponse:
    response = JSONResponse(
        content=ErrorResponse(
            error=message,
            debug=None,
        ).serialize(exclude_none=True),
        status_code=status_code,
    )
    try:
        response.headers["X-Correlation-ID"] = str(scope_id.get())
    except LookupError:
        pass
    return response
