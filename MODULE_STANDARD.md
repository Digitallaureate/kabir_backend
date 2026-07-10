# Backend Module Standard

This document defines the recommended pattern for creating new backend modules in this project.

## Goal

Keep every API module predictable, easy to extend, and easy to debug.

Use consistency over cleverness.

## Recommended Folder Structure

```text
src/modules/<module_name>/
  controller.py
  service.py
  model.py
  __init__.py
```

Add these only when needed:

```text
  repository.py
  constants.py
  utils.py
```

## Responsibility of Each File

### `model.py`

Use for:

- request schemas
- response schemas
- enums
- typed DTOs

Do not put business logic here.

### `controller.py`

Use for:

- FastAPI route definitions
- auth with `Depends(...)`
- request parsing
- calling the service layer
- converting exceptions to HTTP responses
- returning `success_response(...)`

Do not put database logic or large business logic here.

### `service.py`

Use for:

- business rules
- orchestration across collections/services
- calculations
- filtering and mapping
- Firestore writes

Keep HTTP-specific concerns out of the service layer.

### `repository.py`

Add this when the module grows.

Use for:

- Firestore queries
- repeated database access helpers
- persistence-only functions

This keeps `service.py` smaller when the module becomes large.

## Routing Standard

Inside the module router:

```python
router = APIRouter(
    prefix="/home",
    tags=["Home"],
)
```

Inside central route registration:

```python
app.include_router(home_router, prefix="/api")
```

Result:

```text
/api/home/feed
```

### Rule

- module router should define only the module-local prefix
- global `/api` prefix should be added centrally

## Authentication Standard

If the endpoint is authenticated:

```python
uid: str = Depends(verify_header_token)
```

### Rule

- do not take `user_id` from request body when the auth token already exists
- derive the authenticated user in the controller
- pass `user_id` into the service layer

## Response Standard

Always prefer the shared response wrapper:

```python
response_model=GenericResponse[SomeResponse]
```

and:

```python
return success_response(request=request, data=result)
```

### Rule

- outer envelope stays standard
- inner response model contains only business data

## Recommended Controller Template

```python
from fastapi import APIRouter, Depends, HTTPException, Request, status
import logging

from ...core.schemas import GenericResponse, success_response
from ...database.firebase import verify_header_token
from .model import SomeRequest, SomeResponse
from .service import SomeService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/some-module",
    tags=["Some Module"],
)


@router.post(
    "/action",
    response_model=GenericResponse[SomeResponse],
    status_code=status.HTTP_200_OK,
)
async def do_action(
    request: Request,
    body: SomeRequest,
    uid: str = Depends(verify_header_token),
):
    try:
        result = SomeService.do_action(body, user_id=uid)
        return success_response(request=request, data=result)
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as e:
        logger.error(f"Endpoint Error (do_action): {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to perform action: {str(e)}",
        )
```

## Recommended Service Template

```python
class SomeService:
    @staticmethod
    def do_action(body: SomeRequest, user_id: str) -> SomeResponse:
        # validate business rules
        # fetch data
        # calculate / filter / map
        # optionally persist data
        # return typed response
        ...
```

## Recommended Model Template

```python
from pydantic import BaseModel, Field
from typing import List, Optional


class SomeRequest(BaseModel):
    location: str
    latitude: float
    longitude: float


class ItemResponse(BaseModel):
    id: str
    title: str
    distance: Optional[str] = None


class SomeResponse(BaseModel):
    user_id: str
    location: str
    latitude: float
    longitude: float
    items: List[ItemResponse] = Field(default_factory=list)
```

## Growth Rule

When a module starts becoming large:

1. keep `controller.py` thin
2. move repeated Firestore queries to `repository.py`
3. keep mapping helpers in `service.py` or `utils.py`
4. avoid mixing routing, business logic, and persistence in one file

## Practical Rules for This Project

1. One module should have one clear responsibility.
2. Request models should contain only client-sent fields.
3. Authenticated identity should come from token.
4. Response models should be typed and explicit.
5. Database collections are source of truth.
6. Snapshot/cache collections should be treated as derived data.
7. Prefer helper methods over one huge service function.
8. Prefer boring consistency over inventing a new pattern per module.

## Current Recommended Direction for This Repo

Use this standard going forward:

- `controller.py` for routes and auth
- `service.py` for business logic
- `model.py` for schemas
- central `/api` prefixing in `src/core/api.py`
- token-derived `user_id`
- standard `GenericResponse[...]` wrapper

This will make future APIs easier to add and maintain.
