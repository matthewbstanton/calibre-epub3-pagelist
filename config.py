from qt.core import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSpinBox, QCheckBox, QLineEdit
from calibre.utils.config import JSONConfig

# Persistent config storage for the plugin
plugin_prefs = JSONConfig('plugins/epub3_pagelist')
plugin_prefs.defaults['chars_per_page'] = 1850
plugin_prefs.defaults['snap_to_paragraph'] = True
plugin_prefs.defaults['overwrite_existing'] = True
plugin_prefs.defaults['use_custom_column'] = False
plugin_prefs.defaults['custom_column_name'] = ''

class ConfigWidget(QWidget):
    """
    Configuration widget used by Calibre to display plugin settings.
    """
    def __init__(self):
        super().__init__()
        
        layout = QVBoxLayout()
        self.setLayout(layout)
        
        # Characters per page setting
        cpp_layout = QHBoxLayout()
        self.cpp_label = QLabel('Characters per page:')
        self.cpp_spinbox = QSpinBox()
        self.cpp_spinbox.setRange(500, 5000)
        self.cpp_spinbox.setSingleStep(100)
        self.cpp_spinbox.setValue(plugin_prefs['chars_per_page'])
        cpp_layout.addWidget(self.cpp_label)
        cpp_layout.addWidget(self.cpp_spinbox)
        layout.addLayout(cpp_layout)
        
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

        # Custom column setting
        self.custom_column_checkbox = QCheckBox('Use custom column for page count')
        self.custom_column_checkbox.setChecked(plugin_prefs['use_custom_column'])
        self.custom_column_checkbox.setToolTip('Enable to read page count from a custom column instead of auto-calculating.')
        layout.addWidget(self.custom_column_checkbox)

        # Custom column name setting
        column_layout = QHBoxLayout()
        self.column_label = QLabel('Custom column name:')
        self.column_input = QLineEdit()
        self.column_input.setText(plugin_prefs['custom_column_name'])
        self.column_input.setPlaceholderText('e.g., #pages, #page_count')
        self.column_input.setToolTip('Name of the custom column containing the page count (e.g., #pages)')
        column_layout.addWidget(self.column_label)
        column_layout.addWidget(self.column_input)
        layout.addLayout(column_layout)

        layout.addStretch(1)

    def save_settings(self):
        """
        Save the current settings from the UI to the persistent config.
        """
        plugin_prefs['chars_per_page'] = self.cpp_spinbox.value()
        plugin_prefs['snap_to_paragraph'] = self.snap_checkbox.isChecked()
        plugin_prefs['overwrite_existing'] = self.overwrite_checkbox.isChecked()
        plugin_prefs['use_custom_column'] = self.custom_column_checkbox.isChecked()
        plugin_prefs['custom_column_name'] = self.column_input.text().strip()
