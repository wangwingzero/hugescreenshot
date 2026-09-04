# Repository Guidelines

## Project Structure & Module Organization

The active application lives in `HuGeScreenshot-tauri/`, a Tauri app with three layers:

- `src/`: Vue 3 + TypeScript multi-entry frontend (`App.vue`, `WorkbenchApp.vue`, feature components, Pinia stores, composables).
- `src-tauri/src/`: Rust backend modules for screenshot capture, OCR, file search, updates, recording, translation, and Tauri commands.
- `resources/`: shared icons and frontend assets used by the Tauri workspace.

Support folders include `scripts/` for release automation, `infra/` for Cloudflare/R2 helpers, `website/` for the update site, and `docs/` for design notes and bug writeups.

## Build, Test, and Development Commands

Run commands from `HuGeScreenshot-tauri/` unless noted otherwise.

- `npm run tauri:dev`: start the full desktop app with Vite + Tauri hot reload.
- `npm run dev`: frontend-only Vite dev server.
- `npm run build`: type-check and produce the frontend bundle.
- `npm run test:run`: run Vitest once.
- `npm run test:coverage`: run frontend tests with coverage.
- `cargo test` in `src-tauri/`: run Rust tests.
- `cargo test --features proptest` in `src-tauri/`: enable property-based Rust tests.
- `npm run release:local`: build the Windows installer locally.

## Coding Style & Naming Conventions

Use LF line endings. Indent Rust and Python with 4 spaces; Vue, TypeScript, JSON, HTML, and CSS with 2 spaces. Follow existing naming: Vue components in PascalCase (`OcrResultPanel.vue`), composables as `useX.ts`, and Rust modules in `snake_case`.

Use `rustfmt`, `cargo clippy`, and the existing ESLint flat config.

## Testing Guidelines

Frontend tests use Vitest in `src/**/__tests__/` with `.test.ts` or `.spec.ts`. Rust tests are inline or module-adjacent; property regressions live under `proptest-regressions/`.

Add or update tests for behavior changes, especially around OCR, capture scaling, settings persistence, and translation.

## Commit & Pull Request Guidelines

Recent history uses Conventional Commit prefixes: `feat:`, `fix:`, `chore:`, `ci:`. Keep subjects short and imperative, for example `fix: stabilize recording encoder fallback`.

PRs should include a clear summary, affected layers (`frontend`, `rust`, `build`), linked issues when applicable, and screenshots or recordings for UI changes. Mention any config, migration, or packaging impact explicitly.

## Security & Configuration Tips

Do not commit real secrets from `.env`, updater signing keys, or R2 credentials. When changing updater endpoints, document rollout steps in `docs/` or the PR description.
