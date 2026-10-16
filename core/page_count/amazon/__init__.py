"""
Amazon: the page count is read from the book's Amazon product page.

source.py holds the page count source; parser.py builds URLs and parses
page counts out of the HTML without any network access.
"""
from .source import AmazonSource
