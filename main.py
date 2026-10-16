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
from calibre_plugins.epub3_pagelist.core.goodreads import book_url, parse_page_count

# Seconds to wait for a Goodreads book page before giving up on that book
GOODREADS_TIMEOUT = 30
# Characters of the response body shown in the "Show details" text
GOODREADS_BODY_PREVIEW = 3000

def describe_response(url, user_agent, status=None, headers=None, body=None, error=None):
    """
    Return a readable description of a Goodreads request and its response,
    for the "Show details" section of the summary dialog.
    """
    lines = [f'URL: {url}', f'User agent: {user_agent}']
    if error is not None:
        lines.append(f'Error: {error!r}')
    if status is not None:
        lines.append(f'Status: {status}')
    if headers is not None:
        lines.append('Headers:')
        lines.extend(f'    {line}' for line in str(headers).strip().splitlines())
    if body is not None:
        text = body.decode('utf-8', errors='replace') if isinstance(body, bytes) else str(body)
        lines.append(f'Body ({len(text)} characters, first {min(len(text), GOODREADS_BODY_PREVIEW)} shown):')
        lines.append(text[:GOODREADS_BODY_PREVIEW])
    return '\n'.join(lines)

def fetch_goodreads_page_count(goodreads_id):
    """
    Fetch the Goodreads book page for an ID and return (page_count, None, None),
    or (None, reason, details) if the ID is invalid, the fetch fails or no count is found.
    details describes the request and response, or is None if no request was made.
    """
    url = book_url(goodreads_id)
    if not url:
        return None, f'invalid Goodreads ID "{goodreads_id}"', None
    from calibre import browser
    from calibre.utils.random_ua import random_common_chrome_user_agent
    # Same browser identity calibre's metadata sources and the Count Pages plugin use
    user_agent = random_common_chrome_user_agent()
    try:
        br = browser(user_agent=user_agent)
        response = br.open_novisit(url, timeout=GOODREADS_TIMEOUT)
        status = getattr(response, 'code', None)
        headers = response.info()
        raw = response.read()
    except Exception as e:
        # HTTP errors carry their own status, headers and body
        info = getattr(e, 'info', None)
        try:
            body = e.read() if callable(getattr(e, 'read', None)) else None
        except Exception:
            body = None
        details = describe_response(url, user_agent, status=getattr(e, 'code', None),
                                    headers=info() if callable(info) else None, body=body, error=e)
        return None, f'could not fetch {url} ({e})', details
    page_count = parse_page_count(raw)
    if not page_count:
        details = describe_response(url, user_agent, status=status, headers=headers, body=raw)
        return None, f'no page count found on {url}', details
    return page_count, None, None

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
        
        page_count_source = get_page_count_source()

        db = self.gui.current_db
        processed_count = 0
        skipped_non_epub3 = 0
        skipped_already_paginated = 0
        error_count = 0
        error_details = []
        column_values = []
        skipped_goodreads = []
        goodreads_details = []

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

                # Fetched after the overwrite check so skipped books cost no request
                if page_count_source == SOURCE_GOODREADS_ID:
                    title = db.new_api.field_for('title', book_id)
                    identifiers = db.new_api.field_for('identifiers', book_id) or {}
                    goodreads_id = identifiers.get('goodreads')
                    if not goodreads_id:
                        skipped_goodreads.append(f'{title}: no Goodreads ID in its identifiers')
                        continue
                    target_pages, reason, details = fetch_goodreads_page_count(goodreads_id)
                    if not target_pages:
                        skipped_goodreads.append(f'{title}: {reason}')
                        if details:
                            goodreads_details.append(f'Book: {title} (ID {book_id})\n{details}\n' + '-' * 40)
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

        goodreads_note = ''
        if skipped_goodreads:
            goodreads_note = (f'Skipped {len(skipped_goodreads)} book(s) with no Goodreads page count:\n'
                              + '\n'.join(f'    {n}' for n in skipped_goodreads))

        if error_count > 0:
            msg = f'Encountered errors on {error_count} book(s). Click "Show details" for the full traceback.'
            if goodreads_note:
                msg += '\n\n' + goodreads_note
            error_dialog(
                self.gui,
                'Errors during processing',
                msg,
                det_msg='\n\n'.join(error_details + goodreads_details),
                show=True,
            )
        elif processed_count > 0 or skipped_goodreads:
            notes = []
            if skipped_already_paginated > 0:
                notes.append(f'Skipped {skipped_already_paginated} book(s) that already had a page list (overwrite is disabled)')
            if skipped_non_epub3 > 0:
                notes.append(f'Skipped {skipped_non_epub3} book(s) because they are not EPUB 3')
            if goodreads_note:
                notes.append(goodreads_note)
            msg = f'Successfully generated page list for {processed_count} book(s).'
            if notes:
                msg += '\n\n' + '\n'.join(f'• {n}' for n in notes)
            if goodreads_details:
                msg += '\n\nClick "Show details" to see the Goodreads responses.'
            info_dialog(self.gui, 'Processing Complete', msg,
                        det_msg='\n\n'.join(goodreads_details), show=True)
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
