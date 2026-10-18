from calibre.customize import InterfaceActionBase


class EPUB3PageListPlugin(InterfaceActionBase):
    name = 'EPUB3 Page List Generator'
    description = 'Generates synthetic page-list navigation for EPUB3 files'
    supported_platforms = ['windows', 'osx', 'linux']
    author = 'Matthew Stanton'
    version = (1, 0, 8)
    minimum_calibre_version = (6, 0, 0)
    actual_plugin = 'calibre_plugins.epub3_pagelist.action:EPUB3PageListAction'

    def is_customizable(self):
        return True

    def config_widget(self):
        from calibre_plugins.epub3_pagelist.config import ConfigWidget
        return ConfigWidget()

    def save_settings(self, config_widget):
        config_widget.save_settings()
