Calibre GUI plugin that injects synthetic page-list navigation (EPUB3 `nav` page-list, NCX `pageList`, Adobe `page-map.xml`) into EPUB 3 books. See `README.md` for user-facing behaviour and settings.

## Development

Read `dev.md` for development, testing and build instructions, the project layout, the rules for changing the code (including that `core/` must not import Calibre or Qt) and the design principles. Keep `dev.md` up to date instead of repeating its content here.

## Agent skills

### Issue tracker

Issues live as local markdown files under `.scratch/<feature-slug>/`. See `docs/agents/issue-tracker.md`.

### Triage labels

Default canonical labels: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: `CONTEXT.md` + `docs/adr/` at the repo root. See `docs/agents/domain.md`.
