from qt.core import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSpinBox, QCheckBox, QLineEdit,
                     QGroupBox, QRadioButton, QButtonGroup, QApplication)
from calibre.utils.config import JSONConfig

from calibre_plugins.epub3_pagelist.core.page_count import (
    SOURCE_CHARS_PER_PAGE, SOURCE_CUSTOM_COLUMN, SOURCE_GOODREADS_ID, SOURCE_AMAZON_ID, SOURCE_MOBI_ASIN,
    PAGE_COUNT_SOURCES)

# Existing page marker modes
MARKERS_PREFER = 'prefer'  # use the book's markers, generate pages for books without them
MARKERS_ONLY = 'only'      # use the book's markers, skip books without them
MARKERS_IGNORE = 'ignore'  # always generate pages
EXISTING_MARKERS_MODES = (MARKERS_PREFER, MARKERS_ONLY, MARKERS_IGNORE)

# Persistent config storage for the plugin
plugin_prefs = JSONConfig('plugins/epub3_pagelist')
plugin_prefs.defaults['chars_per_page'] = 1850
plugin_prefs.defaults['snap_to_paragraph'] = True
plugin_prefs.defaults['overwrite_existing'] = False
plugin_prefs.defaults['page_count_source'] = SOURCE_CHARS_PER_PAGE
# What to do with print page markers already in the book, one of EXISTING_MARKERS_MODES
plugin_prefs.defaults['existing_markers_mode'] = MARKERS_PREFER
# Save each processed book's final page count to this custom column
plugin_prefs.defaults['save_page_count'] = False
plugin_prefs.defaults['save_page_count_column'] = ''
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

def get_existing_markers_mode():
    """
    Return the configured existing page marker mode, one of EXISTING_MARKERS_MODES.
    """
    mode = plugin_prefs['existing_markers_mode']
    if mode in EXISTING_MARKERS_MODES:
        return mode
    return MARKERS_PREFER

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

        # Amazon Id
        self.amazon_radio = QRadioButton('Use Amazon Id')
        self.amazon_radio.setToolTip('Fetch the page count from the book\'s Amazon product page, using the "amazon" '
                                     'identifier (ASIN). Books without one, or whose page count can\'t be read, are skipped.')
        source_layout.addWidget(self.amazon_radio)

        # mobi-asin
        self.mobi_asin_radio = QRadioButton('Use mobi-asin')
        self.mobi_asin_radio.setToolTip('Fetch the page count from the book\'s Amazon product page, using the "mobi-asin" '
                                        'identifier (ASIN). Books without one, or whose page count can\'t be read, are skipped.')
        source_layout.addWidget(self.mobi_asin_radio)

        self.source_radios = {
            SOURCE_CHARS_PER_PAGE: self.cpp_radio,
            SOURCE_CUSTOM_COLUMN: self.custom_column_radio,
            SOURCE_GOODREADS_ID: self.goodreads_radio,
            SOURCE_AMAZON_ID: self.amazon_radio,
            SOURCE_MOBI_ASIN: self.mobi_asin_radio,
        }
        for radio in self.source_radios.values():
            self.source_group.addButton(radio)
            radio.toggled.connect(self.update_source_inputs)
        self.source_radios[get_page_count_source()].setChecked(True)
        self.update_source_inputs()

        layout.addWidget(source_box)

        # Existing print page markers: one radio button per mode
        markers_box = QGroupBox('Existing page markers')
        markers_box.setToolTip(
            'Retail ePubs often already mark their print pages (epub:type="pagebreak" / role="doc-pagebreak" '
            'markers, page ids such as "page_12", or an existing page-list).')
        markers_layout = QVBoxLayout()
        markers_box.setLayout(markers_layout)
        self.markers_group = QButtonGroup(self)

        self.markers_prefer_radio = QRadioButton('Use the book\'s page markers, generate pages if it has none')
        self.markers_prefer_radio.setToolTip(
            'Build the page-list from the book\'s real print page numbers when it has them. '
            'Books without markers are paginated with the page count source above.')
        self.markers_only_radio = QRadioButton('Use the book\'s page markers, skip books without them')
        self.markers_only_radio.setToolTip(
            'Only build page-lists from real print page numbers. Books without markers are skipped '
            'and listed in the summary.')
        self.markers_ignore_radio = QRadioButton('Ignore page markers, always generate pages')
        self.markers_ignore_radio.setToolTip(
            'Always paginate with the page count source above, even if the book has print page markers.')

        self.markers_radios = {
            MARKERS_PREFER: self.markers_prefer_radio,
            MARKERS_ONLY: self.markers_only_radio,
            MARKERS_IGNORE: self.markers_ignore_radio,
        }
        for radio in self.markers_radios.values():
            self.markers_group.addButton(radio)
            markers_layout.addWidget(radio)
        self.markers_radios[get_existing_markers_mode()].setChecked(True)

        layout.addWidget(markers_box)

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

        # Save page count to a custom column; the name box is only enabled when ticked
        save_layout = QHBoxLayout()
        self.save_count_checkbox = QCheckBox('Save page count to column:')
        self.save_count_checkbox.setChecked(plugin_prefs['save_page_count'])
        self.save_count_checkbox.setToolTip(
            'After a book is processed, write its number of pages to a custom column. '
            'Skipped books are not written.')
        self.save_column_input = QLineEdit()
        self.save_column_input.setText(plugin_prefs['save_page_count_column'])
        self.save_column_input.setPlaceholderText('e.g., #pages')
        self.save_column_input.setToolTip('Lookup name of an integer, floating point or text custom column (e.g., #pages)')
        save_layout.addWidget(self.save_count_checkbox)
        save_layout.addWidget(self.save_column_input)
        layout.addLayout(save_layout)
        self.save_count_checkbox.toggled.connect(self.save_column_input.setEnabled)
        self.save_column_input.setEnabled(self.save_count_checkbox.isChecked())

        layout.addStretch(1)

        self._fitted_to_contents = False

    def showEvent(self, event):
        """
        Set the settings dialog's minimum size the first time this widget is shown.
        """
        super().showEvent(event)
        if not self._fitted_to_contents:
            self._fitted_to_contents = True
            self.set_dialog_minimum_size()

    def set_dialog_minimum_size(self):
        """
        Stop the dialog holding this widget from being smaller than its contents.
        Calibre puts the widget in a scroll area, which can shrink to almost
        nothing, and restores the dialog's last saved size, so a small saved size
        would clip the widget behind scroll bars. Qt grows the dialog to the new
        minimum. The minimum is capped to the screen so the dialog still fits.
        """
        dialog = self.window()
        if dialog is self:
            return
        minimum = dialog.sizeHint()
        screen = dialog.screen() or QApplication.primaryScreen()
        if screen is not None:
            # Leave room for the window frame, which the dialog's size excludes
            frame = dialog.frameGeometry().size() - dialog.geometry().size()
            minimum = minimum.boundedTo(screen.availableGeometry().size() - frame)
        dialog.setMinimumSize(minimum)

    def selected_source(self):
        """
        Return the page count source of the checked radio button.
        """
        for source, radio in self.source_radios.items():
            if radio.isChecked():
                return source
        return SOURCE_CHARS_PER_PAGE

    def selected_markers_mode(self):
        """
        Return the existing page marker mode of the checked radio button.
        """
        for mode, radio in self.markers_radios.items():
            if radio.isChecked():
                return mode
        return MARKERS_PREFER

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
        plugin_prefs['existing_markers_mode'] = self.selected_markers_mode()
        plugin_prefs['save_page_count'] = self.save_count_checkbox.isChecked()
        plugin_prefs['save_page_count_column'] = self.save_column_input.text().strip()
        # Kept in sync so an older plugin version still reads a sensible value
        plugin_prefs['use_custom_column'] = source == SOURCE_CUSTOM_COLUMN
        plugin_prefs['custom_column_name'] = self.column_input.text().strip()
