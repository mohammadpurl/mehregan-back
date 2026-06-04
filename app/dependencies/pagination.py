from dataclasses import dataclass

from fastapi import Query

# Admin dropdowns / user pickers often request 200+ rows in one page.
MAX_PAGE_SIZE = 500


@dataclass(frozen=True)
class ListQueryParams:
    page: int
    page_size: int
    sort_by: str
    sort_order: str
    search: str | None
    filter_by: str | None
    filter_value: str | None

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


def get_list_params(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=MAX_PAGE_SIZE, alias="pageSize"),
    sort_by: str = Query("id", alias="sortBy"),
    sort_order: str = Query("desc", alias="sortOrder"),
    search: str | None = Query(None),
    filter_by: str | None = Query(None, alias="filterBy"),
    filter_value: str | None = Query(None, alias="filterValue"),
) -> ListQueryParams:
    return ListQueryParams(
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_order=sort_order,
        search=search,
        filter_by=filter_by,
        filter_value=filter_value,
    )


def paginated_response(items, total: int, params: ListQueryParams) -> dict:
    return {
        "items": items,
        "total": total,
        "page": params.page,
        "pageSize": params.page_size,
    }
