import math
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Query
from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

DEFAULT_PAGE_SIZE = 10
MAX_PAGE_SIZE = 50


@dataclass
class PageParams:
    page: int
    page_size: int

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


def page_params(
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
) -> PageParams:
    return PageParams(page=page, page_size=page_size)


Pagination = Annotated[PageParams, Depends(page_params)]


@dataclass
class PageResult[T]:
    items: list[T]
    total: int
    page: int
    page_size: int

    @property
    def pages(self) -> int:
        return math.ceil(self.total / self.page_size)

    @property
    def has_next(self) -> bool:
        return self.page < self.pages

    @property
    def has_prev(self) -> bool:
        return self.page > 1


async def paginate(db: AsyncSession, query: Select, params: PageParams) -> PageResult:
    """Run `query` for one page. The query must have a deterministic ORDER BY."""
    total = await db.scalar(select(func.count()).select_from(query.order_by(None).subquery()))
    items = (await db.scalars(query.limit(params.page_size).offset(params.offset))).all()
    return PageResult(items=list(items), total=total or 0, page=params.page, page_size=params.page_size)
