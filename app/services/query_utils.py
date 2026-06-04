from sqlalchemy import or_


def _get_column(model, column_name: str):
    if not column_name:
        return None
    return getattr(model, column_name, None)


def apply_sort(query, model, sort_by: str = "id", sort_order: str = "desc"):
    column = _get_column(model, sort_by) or _get_column(model, "id")
    if not column:
        return query

    if str(sort_order).lower() == "asc":
        return query.order_by(column.asc())
    return query.order_by(column.desc())


def apply_equal_filter(query, model, filter_by: str | None, filter_value: str | None):
    if not filter_by or filter_value is None:
        return query

    column = _get_column(model, filter_by)
    if not column:
        return query
    return query.filter(column == filter_value)


def apply_search_filter(query, model, search: str | None, search_fields: list[str]):
    if not search:
        return query

    clauses = []
    for field in search_fields:
        column = _get_column(model, field)
        if column is not None:
            clauses.append(column.ilike(f"%{search}%"))

    if not clauses:
        return query
    return query.filter(or_(*clauses))
