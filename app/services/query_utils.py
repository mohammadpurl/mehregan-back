from sqlalchemy import or_


def _to_snake(name: str) -> str:
    """Normalize camelCase / PascalCase query params to snake_case column names."""
    if not name or "_" in name:
        return name or ""
    chars: list[str] = []
    for i, ch in enumerate(name):
        if ch.isupper() and i > 0:
            chars.append("_")
        chars.append(ch.lower())
    return "".join(chars)


def _get_column(model, column_name: str):
    if not column_name:
        return None
    col = getattr(model, column_name, None)
    if col is not None:
        return col
    snake = _to_snake(column_name)
    if snake != column_name:
        return getattr(model, snake, None)
    return None


def apply_sort(query, model, sort_by: str = "created_at", sort_order: str = "desc"):
    """
    Sort list queries. Default is newest-first (desc).

    - Accepts camelCase sortBy (e.g. createdAt → created_at).
    - Unknown columns fall back to created_at when present, else id.
    - Secondary id sort keeps order stable when timestamps tie.
    """
    column = _get_column(model, sort_by)
    if column is None:
        column = _get_column(model, "created_at") or _get_column(model, "id")
    if not column:
        return query

    descending = str(sort_order or "desc").lower() != "asc"
    primary = column.desc() if descending else column.asc()

    id_col = _get_column(model, "id")
    if id_col is not None and column is not id_col:
        secondary = id_col.desc() if descending else id_col.asc()
        return query.order_by(primary, secondary)
    return query.order_by(primary)


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
