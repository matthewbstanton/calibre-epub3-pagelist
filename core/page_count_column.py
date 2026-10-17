"""
Saving each book's final page count to a Calibre custom column.

action.py does the writing with Calibre's db API. This module holds the
parts that don't need Calibre: normalising the column name the user typed,
checking that the column can hold a page count, and converting the count to
a value of the column's type. Column metadata is passed in as the dict
Calibre's ``field_metadata[column]`` returns.
"""
from typing import Optional

# Custom column datatypes that can hold a page count
WRITABLE_DATATYPES = ('int', 'float', 'text')


def normalize_column_name(name) -> Optional[str]:
    """
    Return the lookup name for a column name typed with or without the
    leading '#', e.g. 'pages' or ' #Pages ' -> '#pages'.
    Returns None if the name is empty.
    """
    if not name:
        return None
    name = str(name).strip().lstrip('#').strip()
    if not name:
        return None
    # Calibre lookup names are always lowercase
    return '#' + name.lower()


def column_write_problem(column: str, metadata) -> Optional[str]:
    """
    Return why page counts can't be saved to ``column``, or None if they can.
    ``metadata`` is the column's field metadata dict, or None if the library
    has no such column.
    """
    if metadata is None:
        return f"column '{column}' doesn't exist"
    if not metadata.get('is_custom', True):
        return f"'{column}' is not a custom column"
    datatype = metadata.get('datatype')
    if datatype not in WRITABLE_DATATYPES:
        return (f"column '{column}' is of type '{datatype}'; "
                f"it must be an integer, floating point or text column")
    if datatype == 'text' and metadata.get('is_multiple'):
        return f"column '{column}' holds multiple values; it must be a single-value text column"
    return None


def column_value(metadata, pages: int):
    """
    Convert a page count to a value for a column with this field metadata.
    """
    datatype = metadata.get('datatype')
    if datatype == 'float':
        return float(pages)
    if datatype == 'text':
        return str(pages)
    return int(pages)
