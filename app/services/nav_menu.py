from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.constants.nav_menu import NAV_MENU
from app.services.permission import permission_matches


def _item_visible(item: dict[str, Any], have: set[str]) -> bool:
    required = item.get("required_permissions") or []
    if not required:
        return True
    return any(permission_matches(have, code) for code in required)


def filter_nav_menu(have_permissions: set[str], items: list[dict] | None = None) -> list[dict]:
    source = items if items is not None else NAV_MENU
    out: list[dict] = []
    for raw in source:
        item = deepcopy(raw)
        children = item.get("children")
        if children:
            filtered_children = filter_nav_menu(have_permissions, children)
            if not filtered_children:
                continue
            item["children"] = filtered_children
            out.append(item)
            continue
        if _item_visible(item, have_permissions):
            out.append(item)
    return out
