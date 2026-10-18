"""
Custom column: the page count is read from a numeric Calibre custom column.
"""
from typing import Optional

from .base import PageCount, PageCountSource


class CustomColumnSource(PageCountSource):
    """
    Reads the page count from a numeric Calibre custom column.
    """
    def __init__(self, column_name: str):
        self.column = '#' + column_name.strip().lstrip('#')
        self.label = f'custom column {self.column}'
        self.values_read = []

    def get_page_count(self, db, book_id) -> PageCount:
        pages = _positive_int(db.field_for(self.column, book_id))
        if pages is None:
            return PageCount(skip_reason=f'no page count in {self.column}')
        self.values_read.append(f"{db.field_for('title', book_id)}: {pages}")
        return PageCount(pages=pages)

    def summary(self) -> Optional[tuple]:
        if not self.values_read:
            return None
        return ('Custom column values',
                f"Values read from custom column '{self.column}':\n\n" + '\n'.join(self.values_read))


def _positive_int(value) -> Optional[int]:
    """
    Convert a column value to a positive int, or None if it isn't one.
    """
    if value is None or isinstance(value, bool):
        return None
    try:
        count = int(value)
    except (TypeError, ValueError):
        return None
    return count if count > 0 else None
