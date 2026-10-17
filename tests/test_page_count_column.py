"""
Unit tests for core.page_count_column: saving page counts to a custom column.

No Calibre needed; column metadata is given as plain dicts.
"""
import os
import sys
import unittest

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.page_count_column import normalize_column_name, column_write_problem, column_value


def meta(datatype, is_multiple=None, is_custom=True):
    return {'datatype': datatype, 'is_multiple': is_multiple or {}, 'is_custom': is_custom}


class TestNormalizeColumnName(unittest.TestCase):

    def test_adds_hash(self):
        self.assertEqual(normalize_column_name('pages'), '#pages')

    def test_keeps_single_hash(self):
        self.assertEqual(normalize_column_name('#pages'), '#pages')
        self.assertEqual(normalize_column_name('##pages'), '#pages')

    def test_strips_whitespace_and_lowercases(self):
        self.assertEqual(normalize_column_name('  #Page_Count '), '#page_count')
        self.assertEqual(normalize_column_name('# pages'), '#pages')

    def test_empty(self):
        for name in (None, '', '   ', '#', ' # '):
            self.assertIsNone(normalize_column_name(name), repr(name))


class TestColumnWriteProblem(unittest.TestCase):

    def test_writable_types(self):
        for datatype in ('int', 'float', 'text'):
            self.assertIsNone(column_write_problem('#pages', meta(datatype)), datatype)

    def test_missing_column(self):
        self.assertIn("doesn't exist", column_write_problem('#pages', None))

    def test_unsupported_types(self):
        for datatype in ('bool', 'datetime', 'rating', 'comments', 'series', 'enumeration', 'composite'):
            problem = column_write_problem('#pages', meta(datatype))
            self.assertIsNotNone(problem, datatype)
            self.assertIn(datatype, problem)

    def test_multiple_value_text(self):
        problem = column_write_problem('#pages', meta('text', is_multiple={'ui_to_list': ','}))
        self.assertIn('multiple values', problem)

    def test_builtin_field(self):
        self.assertIn('not a custom column', column_write_problem('#pages', meta('int', is_custom=False)))


class TestColumnValue(unittest.TestCase):

    def test_values_by_type(self):
        self.assertEqual(column_value(meta('int'), 312), 312)
        self.assertIsInstance(column_value(meta('int'), 312), int)
        self.assertEqual(column_value(meta('float'), 312), 312.0)
        self.assertIsInstance(column_value(meta('float'), 312), float)
        self.assertEqual(column_value(meta('text'), 312), '312')


if __name__ == '__main__':
    unittest.main()
