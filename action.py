import os
import traceback

from qt.core import QMenu, QToolButton

from calibre.gui2.actions import InterfaceAction
from calibre.gui2 import error_dialog, info_dialog
from calibre.ebooks.oeb.polish.container import get_container
from calibre_plugins.epub3_pagelist.utils import get_icons

from calibre_plugins.epub3_pagelist.config import (plugin_prefs, get_page_count_source, get_existing_markers_mode,
                                                    MARKERS_ONLY, MARKERS_IGNORE)
from calibre_plugins.epub3_pagelist.core.paginator import Paginator, PaginationConfig
from calibre_plugins.epub3_pagelist.core.marker_injector import MarkerInjector
from calibre_plugins.epub3_pagelist.core.nav_builder import NavBuilder
from calibre_plugins.epub3_pagelist.core.existing_markers import ExistingMarkerDetector
from calibre_plugins.epub3_pagelist.core.page_count import create_page_count_source
from calibre_plugins.epub3_pagelist.core.page_count_column import (normalize_column_name, column_write_problem,
                                                                   column_value)
from calibre_plugins.epub3_pagelist.fetcher import CalibreFetcher

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
        
        page_count_source = create_page_count_source(get_page_count_source(), plugin_prefs, CalibreFetcher().fetch)
        markers_mode = get_existing_markers_mode()

        db = self.gui.current_db
        processed_count = 0
        skipped_non_epub3 = 0
        skipped_already_paginated = 0
        error_count = 0
        error_details = []
        skipped_no_page_count = []
        skipped_no_markers = []
        skipped_details = []
        page_counts = []
        # Final page count of each processed book, saved to the column after the loop
        saved_page_counts = {}

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
                config = PaginationConfig(
                    chars_per_page=plugin_prefs['chars_per_page'],
                    snap_to_paragraph=plugin_prefs['snap_to_paragraph']
                )

                # Check if book already has page-list and overwrite is disabled
                nav_builder = NavBuilder(container)
                if not overwrite and nav_builder.has_existing_page_list():
                    skipped_already_paginated += 1
                    # Still save the existing page-list's count to the column
                    existing_count = nav_builder.existing_page_count()
                    if existing_count:
                        saved_page_counts[book_id] = existing_count
                    continue

                # f. Remove the plugin's own markers if overwriting.
                # Print page markers that came with the book are never removed.
                injector = MarkerInjector(container)
                if overwrite:
                    injector.remove_existing_markers()

                # g. Use the book's own print page markers if it has them
                pages = None
                target_pages = None
                if markers_mode != MARKERS_IGNORE:
                    detection = ExistingMarkerDetector(container).detect()
                    if detection.found:
                        pages = detection.markers
                    elif markers_mode == MARKERS_ONLY:
                        skipped_no_markers.append(db.new_api.field_for('title', book_id))
                        continue

                from_markers = pages is not None
                if not from_markers:
                    # Asked after the overwrite check so skipped books cost no web request
                    page_count = page_count_source.get_page_count(db.new_api, book_id)
                    if page_count.skipped:
                        title = db.new_api.field_for('title', book_id)
                        skipped_no_page_count.append(f'{title}: {page_count.skip_reason}')
                        if page_count.details:
                            skipped_details.append(f'Book: {title} (ID {book_id})\n{page_count.details}\n' + '-' * 40)
                        continue
                    target_pages = page_count.pages

                    # h. Run Paginator
                    paginator = Paginator(container, config)
                    pages = paginator.fit_to_page_count(target_pages) if target_pages else paginator.paginate()

                    if not pages:
                        continue

                    # i. Inject page break markers
                    injector.inject_markers(pages)

                # j. Run NavBuilder
                nav_builder.build_page_list(pages, overwrite=overwrite, synthetic=not from_markers)

                # k. Commit changes
                container.commit()

                # l. Save back to library if working with temp copy
                if temp_file_used and temp_file_path:
                    with open(temp_file_path, 'rb') as f:
                        db.new_api.set_format(book_id, 'EPUB', f)

                processed_count += 1
                saved_page_counts[book_id] = len(pages)
                title = db.new_api.field_for('title', book_id)
                if from_markers:
                    page_counts.append(f"{title}: {len(pages)} pages (from the book's page markers)")
                elif target_pages and target_pages != len(pages):
                    page_counts.append(f'{title}: {len(pages)} pages (target {target_pages})')
                else:
                    page_counts.append(f'{title}: {len(pages)} pages')
                
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
        
        # 4. Save the page counts to the custom column, if enabled
        save_note = self.save_page_counts(db, saved_page_counts)

        # 5. Show completion dialog
        summary = page_count_source.summary()
        if summary:
            info_dialog(self.gui, summary[0], summary[1], show=True)

        page_count_note = ''
        if skipped_no_page_count:
            page_count_note = (f'Skipped {len(skipped_no_page_count)} book(s) with no page count:\n'
                               + '\n'.join(f'    {n}' for n in skipped_no_page_count))

        if skipped_no_markers:
            markers_note = (f'Skipped {len(skipped_no_markers)} book(s) with no page markers:\n'
                            + '\n'.join(f'    {t}' for t in skipped_no_markers))
            page_count_note = page_count_note + '\n' + markers_note if page_count_note else markers_note

        page_counts_note = '\n'.join(f'    {c}' for c in page_counts)

        if error_count > 0:
            msg = f'Encountered errors on {error_count} book(s). Click "Show details" for the full traceback.'
            if page_counts:
                msg += f'\n\nGenerated page list for {processed_count} book(s):\n' + page_counts_note
            if page_count_note:
                msg += '\n\n' + page_count_note
            if save_note:
                msg += '\n\n' + save_note
            error_dialog(
                self.gui,
                'Errors during processing',
                msg,
                det_msg='\n\n'.join(error_details + skipped_details),
                show=True,
            )
        elif processed_count > 0 or skipped_no_page_count or skipped_no_markers:
            notes = []
            if skipped_already_paginated > 0:
                notes.append(f'Skipped {skipped_already_paginated} book(s) that already had a page list (overwrite is disabled)')
            if skipped_non_epub3 > 0:
                notes.append(f'Skipped {skipped_non_epub3} book(s) because they are not EPUB 3')
            if page_count_note:
                notes.append(page_count_note)
            if save_note:
                notes.append(save_note)
            msg = f'Successfully generated page list for {processed_count} book(s).'
            if page_counts:
                msg += '\n' + page_counts_note
            if notes:
                msg += '\n\n' + '\n'.join(f'• {n}' for n in notes)
            if skipped_details:
                msg += '\n\nClick "Show details" to see the responses for skipped books.'
            info_dialog(self.gui, 'Processing Complete', msg,
                        det_msg='\n\n'.join(skipped_details), show=True)
        elif skipped_already_paginated > 0:
            msg = (f'Selected {skipped_already_paginated} book(s) already have a page list.\n\n'
                   'To re-generate or overwrite it, enable "Overwrite existing page-list" in plugin preferences.')
            if save_note:
                msg += '\n\n' + save_note
            info_dialog(self.gui, 'Already Paginated', msg, show=True)
        elif skipped_non_epub3 > 0:
            info_dialog(
                self.gui,
                'No EPUB3 files found',
                f'Selected {skipped_non_epub3} book(s) are in EPUB 2 format.\n\nThis plugin only operates on EPUB 3 files (which support standard <nav epub:type="page-list"> navigation).',
                show=True,
            )
        else:
            info_dialog(self.gui, 'Processing Complete', 'No EPUB files found among the selected books.', show=True)

    def save_page_counts(self, db, page_counts):
        """
        Write each processed book's page count to the custom column set in the
        settings, in one batch. ``page_counts`` maps book id to page count.
        Returns a note for the summary dialog, or None if saving is disabled
        or there is nothing to save.
        """
        if not plugin_prefs['save_page_count'] or not page_counts:
            return None
        column = normalize_column_name(plugin_prefs['save_page_count_column'])
        if column is None:
            return 'Page counts were not saved: no column name is set'

        try:
            field_metadata = db.new_api.field_metadata
            metadata = field_metadata[column] if column in field_metadata else None
        except Exception:
            metadata = None
        problem = column_write_problem(column, metadata)
        if problem:
            return f'Page counts were not saved: {problem}'

        try:
            db.new_api.set_field(column, {book_id: column_value(metadata, pages)
                                          for book_id, pages in page_counts.items()})
        except Exception as e:
            return f"Page counts were not saved to '{column}': {e}"

        # Show the new values in the book list
        try:
            self.gui.library_view.model().refresh_ids(list(page_counts))
        except Exception:
            pass
        return f"Saved the page count of {len(page_counts)} book(s) to '{column}'"
