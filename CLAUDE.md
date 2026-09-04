# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Layout

This is the 虎哥截图 (HuGeScreenshot) monorepo. The top-level README still describes the legacy PySide6 app, but the active codebase is the Tauri rewrite. Treat it as the source of truth.

- `HuGeScreenshot-tauri/` — **active application**. Tauri 2.0 + Rust + Vue 3 (no Python sidecar). See `HuGeScreenshot-tauri/CLAUDE.md` for detailed, app-level guidance (architecture, commands, conventions, performance targets).
- `website/` — static landing/update site. `latest.json` served from `https://hugescreenshot.hudawang.cn/latest.json` drives the Tauri updater.
- `build/` — legacy PyInstaller/Inno Setup packaging for the retired PySide6 version. Scripts such as `build_installer.py`, `build.py`, `sync_release_to_r2.py`, `虎哥截图-dir.spec`, and `虎哥截图.iss` target that version, not the Tauri app. Do not use them for the current app — use the Tauri scripts below.
- `scripts/sync_to_public.py` — helper to sync subset of files to a public mirror.
- `docs/` — design notes, plan dumps, and standards references (e.g. 党政机关公文格式).
- `resources/` — shared icons and assets.
- `_backup/`, `_tool/`, `bin/`, `dist/`, `image/`, `临时截图/`, `规章/`, `日志/`, `网页markdown/`, `下载测速/`, `备案/`, `开发经验/` — scratch, asset, and generated folders. Gitignored or historical; avoid modifying unless explicitly asked.

The original PySide6 source (`screenshot_tool/`, `虎哥截图.pyw`) referenced in the root README has been removed from the tree. Ignore those paths when planning work; the legacy README is retained for release-notes history and feature inventory only.

## Working in the Active App

All day-to-day development happens in `HuGeScreenshot-tauri/`. Commands below assume you `cd HuGeScreenshot-tauri/` first.

```bash
npm run tauri:dev         # full stack (Vite + Rust) with hot reload
npm run dev               # frontend only on port 1425
npm run build             # vue-tsc + vite build (type-check + bundle)
npm run test:run          # Vitest once
npm run test:coverage     # Vitest with coverage

cd src-tauri
cargo test                                   # Rust unit/integration tests
cargo test --features proptest               # enable property-based tests
cargo clippy                                 # lint
cargo bench                                  # criterion benches (annotation/screenshot)
```

Single-test examples:
- Vitest: `npx vitest run src/stores/__tests__/history.test.ts`
- Rust: `cargo test -p hugescreenshot-tauri screenshot::capture -- --nocapture`

## Release and Distribution

Releases are driven locally — the old GitHub Actions release workflow is retired. From `HuGeScreenshot-tauri/`:

```bash
npm run release:local     # CI-parity local build (NSIS installer + updater artifacts)
npm run release:r2        # build locally, then publish artifacts and latest.json to Cloudflare R2
```

`release:r2` uploads versioned artifacts first and overwrites `latest.json` last so clients never see a stale pointer. Required env vars: `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_ACCOUNT_ID` (or `R2_ENDPOINT`), `R2_BUCKET` (or `R2_BUCKET_NAME`), `R2_PUBLIC_URL`. Optional: `CF_ZONE_ID`, `CF_API_TOKEN`.

Ignore `build/build_installer.py` and related PyInstaller/Inno scripts — they only built the retired Python version.

## Architecture (Big Picture)

Two layers in `HuGeScreenshot-tauri/`:

1. **Vue 3 frontend** (`src/`) — eight HTML entry points in `vite.config.ts` (`main`, `overlay`, `pin`, `workbench`, `mouseHighlight`, `ocrResult`, `recordingControl`, `recordingPreview`). Each HTML loads its own `*-main.ts` Vue app. Pinia stores live in `src/stores/`, composables in `src/composables/`, services in `src/services/`.
2. **Rust core** (`src-tauri/src/`) — Tauri 2.0 commands in `commands/` (one file per feature area), with domain modules: `screenshot/` (WGC/DXGI/GDI capture), `ocr/` (OpenVINO + PP-OCRv4 background cache), `recording/` (DXGI + FFmpeg), `converter/` (Rust-native PDF/DOCX/HTML → Markdown via pdfium-render, docx-rs, htmd), `file_search/` (client to separate `file-search-service` crate), `hotkey/`, `window/` (overlay/pin windows), `database/`, `mouse_highlight/`, `tray/`, `crash_report/`, `logging/`.

Separate Cargo crate `src-tauri/file-search-service/` builds a standalone Windows Service for NTFS MFT / USN Journal indexing; the main app talks to it over a named pipe.

OpenVINO (`openvino/*.dll`) and PDFium (`pdfium/pdfium.dll`) ship as Tauri `resources` and are dynamically loaded at runtime (`runtime-linking` feature on the `openvino` crate).

Rust lib name is `hugescreenshot_tauri_lib` to avoid a Windows multi-crate-type name collision with the `hugescreenshot-tauri` bin. Doctest is disabled for the same reason.

## Conventions

- **Comments, UI text, commit messages**: Chinese. Commit format `<type>: <description>` — `feat:`, `fix:`, `chore:`, `ci:`, `refactor:`, `docs:`.
- **Indentation**: Rust 4 spaces; Vue, TS, JS, JSON, HTML, CSS 2 spaces. LF line endings.
- **Naming**: Vue components PascalCase (`OcrResultPanel.vue`); composables `useX.ts`; Rust modules `snake_case`.
- **Env vars**: Vite reads `.env` from the repo root via `envDir: ".."`. Rust `load_dotenv()` walks up from the exe for bundled runs.
- **High DPI**: Frontend works in logical pixels only — never multiply by DPR in frontend code. Rust `CaptureResult` carries `dpr`; exports use physical pixels (logical × DPR).
- **Linting**: `rustfmt` + `cargo clippy` (unwrap/expect allowed only in tests per `clippy.toml`); ESLint flat config + Prettier for frontend (no `console` except `warn`/`error`).

## Testing

- Frontend: Vitest in `src/**/__tests__/` with `.test.ts` / `.spec.ts`, jsdom environment.
- Rust: inline `#[cfg(test)]` modules; proptest regressions under `src-tauri/proptest-regressions/`; criterion benches under `src-tauri/benches/` (`annotation_bench`, `screenshot_bench`).
- Add or update tests for behavior changes, especially around OCR, capture scaling, and settings persistence.

## Performance Targets (enforced)

| Metric | Target | Red line |
|---|---|---|
| Startup | <500ms | <1000ms |
| Screenshot latency | <50ms | <100ms |
| UI response | <16ms (60fps) | <33ms (30fps) |
| Memory | 30-50MB | <200MB |

## Security Notes

Treat `.env`, updater signing keys, and R2 credentials as sensitive — never commit them. When changing updater endpoints, document rollout steps in `docs/` or the PR description.
