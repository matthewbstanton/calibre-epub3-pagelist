from qt.core import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSpinBox, QCheckBox, QLineEdit,
                     QGroupBox, QRadioButton, QButtonGroup)
from calibre.utils.config import JSONConfig

# Values for the 'page_count_source' pref
SOURCE_CHARS_PER_PAGE = 'chars_per_page'
SOURCE_CUSTOM_COLUMN = 'custom_column'
SOURCE_GOODREADS_ID = 'goodreads_id'
PAGE_COUNT_SOURCES = (SOURCE_CHARS_PER_PAGE, SOURCE_CUSTOM_COLUMN, SOURCE_GOODREADS_ID)

# Persistent config storage for the plugin
plugin_prefs = JSONConfig('plugins/epub3_pagelist')
plugin_prefs.defaults['chars_per_page'] = 1850
plugin_prefs.defaults['snap_to_paragraph'] = True
plugin_prefs.defaults['overwrite_existing'] = False
plugin_prefs.defaults['page_count_source'] = SOURCE_CHARS_PER_PAGE
# Superseded by 'page_count_source'; still read to migrate older settings
plugin_prefs.defaults['use_custom_column'] = False
plugin_prefs.defaults['custom_column_name'] = ''

def get_page_count_source():
    """
    Return the configured page count source, one of PAGE_COUNT_SOURCES.
    Settings saved before 'page_count_source' existed fall back to the
    old 'use_custom_column' checkbox.
    """
    # JSONConfig's `in` only sees saved values, not defaults
    if 'page_count_source' in plugin_prefs:
        source = plugin_prefs['page_count_source']
        if source in PAGE_COUNT_SOURCES:
            return source
        return SOURCE_CHARS_PER_PAGE
    if plugin_prefs['use_custom_column']:
        return SOURCE_CUSTOM_COLUMN
    return SOURCE_CHARS_PER_PAGE

class ConfigWidget(QWidget):
    """
    Configuration widget used by Calibre to display plugin settings.
    """
    def __init__(self):
        super().__init__()

        layout = QVBoxLayout()
        self.setLayout(layout)

        # Page count source: one radio button per source, each with its own inputs below it
        source_box = QGroupBox('Page count source')
        source_layout = QVBoxLayout()
        source_box.setLayout(source_layout)
        self.source_group = QButtonGroup(self)

        # Characters per page
        self.cpp_radio = QRadioButton('Characters per page')
        self.cpp_radio.setToolTip('Split the book into pages of a fixed number of characters.')
        source_layout.addWidget(self.cpp_radio)
        cpp_layout = QHBoxLayout()
        cpp_layout.setContentsMargins(24, 0, 0, 0)
        self.cpp_label = QLabel('Characters per page:')
        self.cpp_spinbox = QSpinBox()
        self.cpp_spinbox.setRange(500, 5000)
        self.cpp_spinbox.setSingleStep(100)
        self.cpp_spinbox.setValue(plugin_prefs['chars_per_page'])
        cpp_layout.addWidget(self.cpp_label)
        cpp_layout.addWidget(self.cpp_spinbox)
        source_layout.addLayout(cpp_layout)

        # Custom column
        self.custom_column_radio = QRadioButton('Custom column')
        self.custom_column_radio.setToolTip('Read the page count from a custom column instead of auto-calculating.')
        source_layout.addWidget(self.custom_column_radio)
        column_layout = QHBoxLayout()
        column_layout.setContentsMargins(24, 0, 0, 0)
        self.column_label = QLabel('Custom column name:')
        self.column_input = QLineEdit()
        self.column_input.setText(plugin_prefs['custom_column_name'])
        self.column_input.setPlaceholderText('e.g., #pages, #page_count')
        self.column_input.setToolTip('Name of the custom column containing the page count (e.g., #pages)')
        column_layout.addWidget(self.column_label)
        column_layout.addWidget(self.column_input)
        source_layout.addLayout(column_layout)

        # Goodreads Id
        self.goodreads_radio = QRadioButton('Use Goodreads Id')
        self.goodreads_radio.setToolTip('Fetch the page count from the book\'s Goodreads page, using the "goodreads" '
                                        'identifier. Books without one, or whose page count can\'t be read, are skipped.')
        source_layout.addWidget(self.goodreads_radio)

        self.source_radios = {
            SOURCE_CHARS_PER_PAGE: self.cpp_radio,
            SOURCE_CUSTOM_COLUMN: self.custom_column_radio,
            SOURCE_GOODREADS_ID: self.goodreads_radio,
        }
        for radio in self.source_radios.values():
            self.source_group.addButton(radio)
            radio.toggled.connect(self.update_source_inputs)
        self.source_radios[get_page_count_source()].setChecked(True)
        self.update_source_inputs()

        layout.addWidget(source_box)

        # Snap to paragraph setting
        self.snap_checkbox = QCheckBox('Snap to paragraph boundaries')
        self.snap_checkbox.setChecked(plugin_prefs['snap_to_paragraph'])
        self.snap_checkbox.setToolTip('Attempt to snap page breaks to the nearest paragraph boundary.')
        layout.addWidget(self.snap_checkbox)

        # Overwrite existing setting
        self.overwrite_checkbox = QCheckBox('Overwrite existing page-list')
        self.overwrite_checkbox.setChecked(plugin_prefs['overwrite_existing'])
        self.overwrite_checkbox.setToolTip('Overwrite page-list if it already exists in the EPUB.')
        layout.addWidget(self.overwrite_checkbox)

        layout.addStretch(1)

    def selected_source(self):
        """
        Return the page count source of the checked radio button.
        """
        for source, radio in self.source_radios.items():
            if radio.isChecked():
                return source
        return SOURCE_CHARS_PER_PAGE

    def update_source_inputs(self, *args):
        """
        Enable only the inputs that belong to the selected page count source.
        """
        cpp_selected = self.cpp_radio.isChecked()
        self.cpp_label.setEnabled(cpp_selected)
        self.cpp_spinbox.setEnabled(cpp_selected)
        column_selected = self.custom_column_radio.isChecked()
        self.column_label.setEnabled(column_selected)
        self.column_input.setEnabled(column_selected)

    def save_settings(self):
        """
        Save the current settings from the UI to the persistent config.
        """
        source = self.selected_source()
        plugin_prefs['chars_per_page'] = self.cpp_spinbox.value()
        plugin_prefs['snap_to_paragraph'] = self.snap_checkbox.isChecked()
        plugin_prefs['overwrite_existing'] = self.overwrite_checkbox.isChecked()
        plugin_prefs['page_count_source'] = source
        # Kept in sync so an older plugin version still reads a sensible value
        plugin_prefs['use_custom_column'] = source == SOURCE_CUSTOM_COLUMN
        plugin_prefs['custom_column_name'] = self.column_input.text().strip()
