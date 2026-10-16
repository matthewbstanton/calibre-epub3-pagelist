import os
import traceback

from qt.core import QMenu, QToolButton

from calibre.gui2.actions import InterfaceAction
from calibre.gui2 import error_dialog, info_dialog
from calibre.ebooks.oeb.polish.container import get_container
from calibre_plugins.epub3_pagelist.utils import get_icons

from calibre_plugins.epub3_pagelist.config import (plugin_prefs, get_page_count_source,
                                                   SOURCE_CUSTOM_COLUMN, SOURCE_GOODREADS_ID)
from calibre_plugins.epub3_pagelist.core.paginator import Paginator, PaginationConfig
from calibre_plugins.epub3_pagelist.core.marker_injector import MarkerInjector
from calibre_plugins.epub3_pagelist.core.nav_builder import NavBuilder

class EPUB3PageListAction(InterfaceAction):
    """
    Main InterfaceAction for the EPUB3 Page List plugin.
    Adds a toolbar button and triggers the generation process.
    """
    name = 'EPUB3 Page List'
    action_spec = ('Generate Page List', None, 'Generate synthetic page-list navigation for EPUB3 files', None)
    action_type = 'current'
    # Clicking the button runs the action; the arrow beside it opens the menu
    popup_type = QToolButton.ToolButtonPopupMode.MenuButtonPopup

    def genesis(self):
        """
        Called once during plugin initialization.
        Sets up the toolbar icon, the dropdown menu and connects the action.
        """
        icon = get_icons('images/icon.png', 'EPUB3 Page List Generator')
        self.qaction.setIcon(icon)
        self.qaction.triggered.connect(self.generate_page_list)

        # Dropdown menu, also shown as a submenu in menus and context menus
        menu = QMenu(self.gui)
        self.create_menu_action(menu, 'epub3-pagelist-generate', 'Generate Page List',
                                icon=icon, shortcut=False, triggered=self.generate_page_list)
        menu.addSeparator()
        self.create_menu_action(menu, 'epub3-pagelist-customize', 'Customize plugin…',
                                icon='config.png', shortcut=False, triggered=self.show_configuration)
        self.qaction.setMenu(menu)

    def show_configuration(self):
        """
        Opens the same settings dialog as Preferences → Plugins → Customize plugin.
        do_user_config() calls config_widget() and save_settings() from __init__.py.
        """
        self.interface_action_base_plugin.do_user_config(self.gui)

    def generate_page_list(self):
        """
        Main processing method called when the toolbar button is clicked.
        """
        # 1. Get selected book IDs from the GUI
        selected_ids = self.gui.library_view.get_selected_ids()
        
        # 2. If no books selected, show info dialog and return
        if not selected_ids:
            info_dialog(self.gui, 'No books selected', 'Please select at least one book to process.', show=True)
            return
        
        # Goodreads Id is selectable in settings but has no lookup yet, so skip every book
        page_count_source = get_page_count_source()
        if page_count_source == SOURCE_GOODREADS_ID:
            info_dialog(
                self.gui,
                'Not implemented yet',
                f'Skipped {len(selected_ids)} book(s): the Goodreads Id page count source is not implemented yet.\n\n'
                'Choose "Characters per page" or "Custom column" under "Page count source" in plugin preferences.',
                show=True,
            )
            return

        db = self.gui.current_db
        processed_count = 0
        skipped_non_epub3 = 0
        skipped_already_paginated = 0
        error_count = 0
        error_details = []
        column_values = []
        
        # 3. For each selected book
        for book_id in selected_ids:
            temp_file_used = False
            temp_file_path = None
            try:
                # a. Check if EPUB format exists in library
                if not db.new_api.has_format(book_id, 'EPUB'):
                    continue
                
                # b. Get the EPUB file path
                epub_path = db.new_api.format_abspath(book_id, 'EPUB')

                if not epub_path:
                    # If absolute path is not available, use format to get a temp copy
                    temp_file_path = db.new_api.format(book_id, 'EPUB', as_path=True)
                    epub_path = temp_file_path
                    temp_file_used = True

                if not epub_path:
                    continue

                # c. Open with get_container
                container = get_container(epub_path, tweak_mode=True)
                
                # d. Check EPUB version (skip if not EPUB3)
                opf_version = getattr(container.opf_version_parsed, 'major', None) if hasattr(container, 'opf_version_parsed') else None
                if opf_version is None:
                    try:
                        opf_version = int(float(str(getattr(container, 'opf_version', '2.0'))))
                    except Exception:
                        opf_version = 2

                if opf_version < 3:
                    skipped_non_epub3 += 1
                    continue
                
                # e. Load config
                overwrite = plugin_prefs['overwrite_existing']
                target_pages = None
                if page_count_source == SOURCE_CUSTOM_COLUMN:
                    column_name = '#' + plugin_prefs['custom_column_name'].strip().lstrip('#')
                    target_pages = int(db.new_api.field_for(column_name, book_id))
                    column_values.append(f"{db.new_api.field_for('title', book_id)}: {target_pages}")

                config = PaginationConfig(
                    chars_per_page=plugin_prefs['chars_per_page'],
                    snap_to_paragraph=plugin_prefs['snap_to_paragraph']
                )

                # Check if book already has page-list and overwrite is disabled
                nav_builder = NavBuilder(container)
                if not overwrite and nav_builder.has_existing_page_list():
                    skipped_already_paginated += 1
                    continue

                # f. Remove existing markers if overwriting
                injector = MarkerInjector(container)
                if overwrite:
                    injector.remove_existing_markers()

                # g. Run Paginator
                paginator = Paginator(container, config)
                pages = paginator.fit_to_page_count(target_pages) if target_pages else paginator.paginate()

                if not pages:
                    continue

                # h. Inject page break markers
                injector.inject_markers(pages)

                # i. Run NavBuilder
                nav_builder.build_page_list(pages, overwrite=overwrite)

                # j. Commit changes
                container.commit()

                # k. Save back to library if working with temp copy
                if temp_file_used and temp_file_path:
                    with open(temp_file_path, 'rb') as f:
                        db.new_api.set_format(book_id, 'EPUB', f)

                processed_count += 1
                
            except Exception as e:
                error_count += 1
                tb = traceback.format_exc()
                title = db.new_api.title(book_id) if hasattr(db.new_api, 'title') else f"ID {book_id}"
                error_details.append(f"Book: {title} (ID {book_id})\nError: {e}\n{tb}\n" + "-" * 40)
            finally:
                if temp_file_used and temp_file_path:
                    try:
                        os.remove(temp_file_path)
                    except Exception:
                        pass
        
        # 4. Show completion dialog
        if column_values:
            column_name = plugin_prefs['custom_column_name'].strip().lstrip('#')
            info_dialog(
                self.gui,
                'Custom column values',
                f"Values read from custom column '#{column_name}':\n\n" + '\n'.join(column_values),
                show=True,
            )

        if error_count > 0:
            error_dialog(
                self.gui,
                'Errors during processing',
                f'Encountered errors on {error_count} book(s). Click "Show details" for the full traceback.',
                det_msg='\n\n'.join(error_details),
                show=True,
            )
        elif processed_count > 0:
            msg = f'Successfully generated page list for {processed_count} book(s).'
            notes = []
            if skipped_already_paginated > 0:
                notes.append(f'Skipped {skipped_already_paginated} book(s) that already had a page list (overwrite is disabled)')
            if skipped_non_epub3 > 0:
                notes.append(f'Skipped {skipped_non_epub3} book(s) because they are not EPUB 3')
            if notes:
                msg += '\n\n' + '\n'.join(f'• {n}' for n in notes)
            info_dialog(self.gui, 'Processing Complete', msg, show=True)
        elif skipped_already_paginated > 0:
            info_dialog(
                self.gui,
                'Already Paginated',
                f'Selected {skipped_already_paginated} book(s) already have a page list.\n\nTo re-generate or overwrite it, enable "Overwrite existing page-list" in plugin preferences.',
                show=True,
            )
        elif skipped_non_epub3 > 0:
            info_dialog(
                self.gui,
                'No EPUB3 files found',
                f'Selected {skipped_non_epub3} book(s) are in EPUB 2 format.\n\nThis plugin only operates on EPUB 3 files (which support standard <nav epub:type="page-list"> navigation).',
                show=True,
            )
        else:
            info_dialog(self.gui, 'Processing Complete', 'No EPUB files found among the selected books.', show=True)
