import os
import traceback

from qt.core import QMenu, QToolButton

from calibre.gui2.actions import InterfaceAction
from calibre.gui2 import error_dialog, info_dialog
from calibre.ebooks.oeb.polish.container import get_container
from calibre_plugins.epub3_pagelist.utils import get_icons

from calibre_plugins.epub3_pagelist.config import (plugin_prefs, get_page_count_source, get_existing_markers_mode,
                                                    MARKERS_ONLY, MARKERS_IGNORE)
from calibre_plugins.epub3_pagelist.core.paginator import PaginationConfig
from calibre_plugins.epub3_pagelist.core.marker_injector import MarkerInjector
from calibre_plugins.epub3_pagelist.core.nav_builder import NavBuilder
from calibre_plugins.epub3_pagelist.core.page_list_remover import PageListRemover
from calibre_plugins.epub3_pagelist.core.page_planner import (plan_pages, PLAN_EXISTING, PLAN_NO_MARKERS,
                                                              PLAN_NO_PAGE_COUNT, PLAN_EMPTY)
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
        self.save_count_action = self.create_menu_action(
            menu, 'epub3-pagelist-save-count', 'Save page count to column',
            shortcut=False, triggered=self.save_page_count_to_column,
            description='Write the page count of the selected books to the custom column set in the '
                        'settings, without changing the books')
        self.create_menu_action(
            menu, 'epub3-pagelist-remove', 'Remove page list',
            shortcut=False, triggered=self.remove_page_list,
            description='Remove the page-list, page markers and metadata the plugin added to the '
                        'selected books. The books\' own print page markers are kept')
        menu.addSeparator()
        self.create_menu_action(menu, 'epub3-pagelist-customize', 'Customize plugin…',
                                icon='config.png', shortcut=False, triggered=self.show_configuration)
        self.qaction.setMenu(menu)
        # The setting can change at any time, so check it each time the menu opens
        menu.aboutToShow.connect(self.update_menu_state)
        self.update_menu_state()

    def show_configuration(self):
        """
        Opens the same settings dialog as Preferences → Plugins → Customize plugin.
        do_user_config() calls config_widget() and save_settings() from __init__.py.
        """
        self.interface_action_base_plugin.do_user_config(self.gui)
        self.update_menu_state()

    def update_menu_state(self):
        """
        Enable "Save page count to column" only while the setting is ticked.
        Called before the menu shows and after the settings are saved, so a
        change takes effect without restarting Calibre.
        """
        self.save_count_action.setEnabled(bool(plugin_prefs['save_page_count']))

    def _settings(self):
        """
        Read the settings that plan_pages() needs.
        Returns (page_count_source, pagination config, overwrite, use_markers, markers_only).
        """
        page_count_source = create_page_count_source(get_page_count_source(), plugin_prefs, CalibreFetcher().fetch)
        markers_mode = get_existing_markers_mode()
        config = PaginationConfig(
            chars_per_page=plugin_prefs['chars_per_page'],
            snap_to_paragraph=plugin_prefs['snap_to_paragraph']
        )
        return (page_count_source, config, plugin_prefs['overwrite_existing'],
                markers_mode != MARKERS_IGNORE, markers_mode == MARKERS_ONLY)

    @staticmethod
    def _epub_path(db, book_id):
        """
        Return (path, temp_file_path) of the book's EPUB, or (None, None) if it has none.
        temp_file_path is set when the library gave a temporary copy; the
        caller must save it back (if changed) and delete it.
        """
        if not db.new_api.has_format(book_id, 'EPUB'):
            return None, None
        epub_path = db.new_api.format_abspath(book_id, 'EPUB')
        if epub_path:
            return epub_path, None
        # If absolute path is not available, use format to get a temp copy
        temp_file_path = db.new_api.format(book_id, 'EPUB', as_path=True)
        return temp_file_path, temp_file_path

    @staticmethod
    def _is_epub3(container):
        """
        Return True if the container's OPF is version 3 or later.
        """
        opf_version = getattr(container.opf_version_parsed, 'major', None) if hasattr(container, 'opf_version_parsed') else None
        if opf_version is None:
            try:
                opf_version = int(float(str(getattr(container, 'opf_version', '2.0'))))
            except Exception:
                opf_version = 2
        return opf_version >= 3

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
        
        page_count_source, config, overwrite, use_markers, markers_only = self._settings()

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
            temp_file_path = None
            try:
                # a. Get the EPUB file path, skipping books without an EPUB
                epub_path, temp_file_path = self._epub_path(db, book_id)
                if not epub_path:
                    continue

                # b. Open with get_container
                container = get_container(epub_path, tweak_mode=True)
                
                # c. Check EPUB version (skip if not EPUB3)
                if not self._is_epub3(container):
                    skipped_non_epub3 += 1
                    continue

                # d. Work out the pages: an existing page-list, the book's own
                # print page markers, or pages from the page count source
                plan = plan_pages(container, page_count_source, db.new_api, book_id, config,
                                  overwrite, use_markers=use_markers, markers_only=markers_only)

                if plan.outcome == PLAN_EXISTING:
                    skipped_already_paginated += 1
                    # Still save the existing page-list's count to the column
                    if plan.page_count:
                        saved_page_counts[book_id] = plan.page_count
                    continue
                if plan.outcome == PLAN_NO_MARKERS:
                    skipped_no_markers.append(db.new_api.field_for('title', book_id))
                    continue
                if plan.outcome == PLAN_NO_PAGE_COUNT:
                    title = db.new_api.field_for('title', book_id)
                    skipped_no_page_count.append(f'{title}: {plan.source_result.skip_reason}')
                    if plan.source_result.details:
                        skipped_details.append(f'Book: {title} (ID {book_id})\n{plan.source_result.details}\n' + '-' * 40)
                    continue
                if plan.outcome == PLAN_EMPTY:
                    continue

                pages = plan.pages
                from_markers = plan.from_markers
                target_pages = plan.target_pages

                # e. Inject page break markers
                if not from_markers:
                    MarkerInjector(container).inject_markers(pages)

                # f. Run NavBuilder
                NavBuilder(container).build_page_list(pages, overwrite=overwrite, synthetic=not from_markers)

                # g. Commit changes
                container.commit()

                # h. Save back to library if working with temp copy
                if temp_file_path:
                    with open(temp_file_path, 'rb') as f:
                        db.new_api.set_format(book_id, 'EPUB', f)

                processed_count += 1
                saved_page_counts[book_id] = len(pages)
                title = db.new_api.field_for('title', book_id)
                if target_pages and target_pages != len(pages):
                    page_counts.append(f'{title}: {len(pages)} pages (from {plan.origin}, target {target_pages})')
                else:
                    page_counts.append(f'{title}: {len(pages)} pages (from {plan.origin})')
                
            except Exception as e:
                error_count += 1
                tb = traceback.format_exc()
                title = db.new_api.title(book_id) if hasattr(db.new_api, 'title') else f"ID {book_id}"
                error_details.append(f"Book: {title} (ID {book_id})\nError: {e}\n{tb}\n" + "-" * 40)
            finally:
                if temp_file_path:
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

    def save_page_count_to_column(self):
        """
        Menu action: work out each selected book's page count, the same way
        generate_page_list() does, and only write it to the custom column.
        The EPUB is opened read-only in effect: the container is never
        committed, so no markers, page-list or metadata are added.
        """
        if not plugin_prefs['save_page_count']:
            info_dialog(self.gui, 'Saving page counts is disabled',
                        'Tick "Save page count to column" in the plugin settings and enter a column name.',
                        show=True)
            return

        selected_ids = self.gui.library_view.get_selected_ids()
        if not selected_ids:
            info_dialog(self.gui, 'No books selected', 'Please select at least one book to process.', show=True)
            return

        page_count_source, config, overwrite, use_markers, markers_only = self._settings()

        db = self.gui.current_db
        page_counts = {}
        counted = []
        skipped = []
        skipped_details = []
        error_details = []
        skipped_no_epub = 0
        skipped_non_epub3 = 0

        for book_id in selected_ids:
            temp_file_path = None
            title = db.new_api.field_for('title', book_id)
            try:
                epub_path, temp_file_path = self._epub_path(db, book_id)
                if not epub_path:
                    skipped_no_epub += 1
                    continue

                container = get_container(epub_path, tweak_mode=True)
                if not self._is_epub3(container):
                    skipped_non_epub3 += 1
                    continue

                plan = plan_pages(container, page_count_source, db.new_api, book_id, config,
                                  overwrite, use_markers=use_markers, markers_only=markers_only)
                if plan.page_count:
                    page_counts[book_id] = plan.page_count
                    counted.append(f'{title}: {plan.page_count} pages (from {plan.origin})')
                elif plan.outcome == PLAN_NO_MARKERS:
                    skipped.append(f'{title}: no page markers')
                elif plan.outcome == PLAN_NO_PAGE_COUNT:
                    skipped.append(f'{title}: {plan.source_result.skip_reason}')
                    if plan.source_result.details:
                        skipped_details.append(f'Book: {title} (ID {book_id})\n{plan.source_result.details}\n' + '-' * 40)
                else:
                    skipped.append(f'{title}: no pages')
            except Exception as e:
                tb = traceback.format_exc()
                error_details.append(f'Book: {title} (ID {book_id})\nError: {e}\n{tb}\n' + '-' * 40)
            finally:
                # Never saved back: this action doesn't change the book
                if temp_file_path:
                    try:
                        os.remove(temp_file_path)
                    except Exception:
                        pass

        save_note = self.save_page_counts(db, page_counts)

        summary = page_count_source.summary()
        if summary:
            info_dialog(self.gui, summary[0], summary[1], show=True)

        notes = []
        if save_note:
            notes.append(save_note)
        if skipped:
            notes.append(f'Skipped {len(skipped)} book(s) with no page count:\n'
                         + '\n'.join(f'    {n}' for n in skipped))
        if skipped_non_epub3:
            notes.append(f'Skipped {skipped_non_epub3} book(s) because they are not EPUB 3')
        if skipped_no_epub:
            notes.append(f'Skipped {skipped_no_epub} book(s) with no EPUB format')

        if page_counts:
            msg = f'Found the page count of {len(page_counts)} book(s):\n' + '\n'.join(f'    {c}' for c in counted)
        else:
            msg = 'No page counts were found for the selected books.'
        if notes:
            msg += '\n\n' + '\n'.join(f'• {n}' for n in notes)

        if error_details:
            msg = (f'Encountered errors on {len(error_details)} book(s). '
                   'Click "Show details" for the full traceback.\n\n' + msg)
            error_dialog(self.gui, 'Errors while saving page counts', msg,
                         det_msg='\n\n'.join(error_details + skipped_details), show=True)
        else:
            if skipped_details:
                msg += '\n\nClick "Show details" to see the responses for skipped books.'
            info_dialog(self.gui, 'Save Page Count to Column', msg,
                        det_msg='\n\n'.join(skipped_details), show=True)

    def remove_page_list(self):
        """
        Menu action: strip what the plugin added from each selected book
        (synthetic markers, nav page-list, NCX pageList, page-map.xml and
        accessibility metadata). Books without the plugin's footprint, and
        the books' own print page markers, are left alone.
        """
        selected_ids = self.gui.library_view.get_selected_ids()
        if not selected_ids:
            info_dialog(self.gui, 'No books selected', 'Please select at least one book to process.', show=True)
            return

        db = self.gui.current_db
        removed = []
        unchanged = 0
        skipped_no_epub = 0
        error_details = []

        for book_id in selected_ids:
            temp_file_path = None
            title = db.new_api.field_for('title', book_id)
            try:
                epub_path, temp_file_path = self._epub_path(db, book_id)
                if not epub_path:
                    skipped_no_epub += 1
                    continue

                container = get_container(epub_path, tweak_mode=True)
                result = PageListRemover(container).remove()
                if not result.changed:
                    unchanged += 1
                    continue

                container.commit()
                if temp_file_path:
                    with open(temp_file_path, 'rb') as f:
                        db.new_api.set_format(book_id, 'EPUB', f)
                removed.append(f'{title}: {result.markers} marker(s) removed')
            except Exception as e:
                tb = traceback.format_exc()
                error_details.append(f'Book: {title} (ID {book_id})\nError: {e}\n{tb}\n' + '-' * 40)
            finally:
                if temp_file_path:
                    try:
                        os.remove(temp_file_path)
                    except Exception:
                        pass

        msg = (f'Removed the page list from {len(removed)} book(s):\n' + '\n'.join(f'    {r}' for r in removed)
               if removed else 'No page lists added by the plugin were found in the selected books.')
        notes = []
        if unchanged:
            notes.append(f'{unchanged} book(s) had nothing added by the plugin')
        if skipped_no_epub:
            notes.append(f'Skipped {skipped_no_epub} book(s) with no EPUB format')
        if notes:
            msg += '\n\n' + '\n'.join(f'• {n}' for n in notes)

        if error_details:
            error_dialog(self.gui, 'Errors while removing page lists',
                         f'Encountered errors on {len(error_details)} book(s). '
                         'Click "Show details" for the full traceback.\n\n' + msg,
                         det_msg='\n\n'.join(error_details), show=True)
        else:
            info_dialog(self.gui, 'Remove Page List', msg, show=True)

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
