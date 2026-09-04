# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

HuGeScreenshot (虎哥截图) is a Windows desktop screenshot tool built with **Tauri 2.0 + Rust + Vue 3**. It's a rewrite of the original PySide6 version targeting <500ms startup and <50MB memory.

## Architecture

Two-layer architecture communicating via Tauri IPC (frontend↔Rust):

- **Vue 3 Frontend** (`src/`): Multi-page app with 8 HTML entry points (main, overlay, pin, workbench, mouse-highlight-overlay, ocr-result, recording-control, recording-preview). Each has its own Vue app instance. Uses Pinia for state management.
- **Rust Core** (`src-tauri/src/`): Tauri 2.0 commands in `commands/`, with modules for screenshot capture (WGC/DXGI/GDI), OCR (OpenVINO PP-OCRv4), recording (DXGI + FFmpeg), document conversion (Rust-native PDF/DOCX/HTML→Markdown via pdfium-render, docx-rs, htmd), hotkey management, window management, SQLite database, full-text search (Tantivy + Jieba), and file search (named-pipe client to a separate `file-search-service` crate).

## Common Commands

```bash
# Development (full stack with hot reload)
npm run tauri:dev

# Frontend only (Vite dev server on port 1425)
npm run dev

# Production build (NSIS installer)
npm run tauri build

# Local CI-parity release build
npm run release:local

# Frontend type check + build
npm run build

# Frontend tests
npm run test          # watch mode
npm run test:run      # single run
npm run test:coverage # with coverage

# Rust tests
cd src-tauri && cargo test
cd src-tauri && cargo test --features proptest   # property-based tests
cd src-tauri && cargo bench                       # benchmarks (criterion)
cd src-tauri && cargo clippy                      # lint
```

## Key Configuration

- **Vite**: Multi-entry build in `vite.config.ts`, port 1425, path alias `@/` → `src/`
- **Tauri**: `src-tauri/tauri.conf.json` — borderless 800x600 window, NSIS bundler, OpenVINO and pdfium DLLs as resources
- **Env vars**: `.env` loaded from parent directory (`../`), not project root
- **Rust lib**: crate name is `hugescreenshot_tauri_lib` (avoids Windows name collision), doctest disabled due to multi crate-type linking issues

## Conventions

- **Comments & commit messages**: Chinese. Commit format: `<type>: <description>` (e.g., `feat: 添加马赛克工具`)
- **Indentation**: Rust 4 spaces, Vue/TS/JS/JSON/HTML/CSS 2 spaces
- **Line endings**: LF
- **High DPI**: Frontend uses logical pixels only — never multiply by DPR in frontend code. Rust `CaptureResult` includes `dpr`; export uses physical pixels (logical × DPR).
- **Rust linting**: rustfmt + clippy enforced. `clippy.toml` allows unwrap/expect in tests only.
- **Frontend linting**: ESLint (flat config) + Prettier. No console except warn/error.

## CI/CD

Release publishing is local-first:
- Run `npm run release:local` for a CI-parity local release build.
- Run `npm run release:r2` to build locally and publish versioned artifacts plus `latest.json` to Cloudflare R2.
- The app updater reads `https://hugescreenshot.hudawang.cn/latest.json`.

If old GitHub Actions release runs still exist on GitHub, treat them as historical only and remove them from the repository / Actions UI rather than reviving the workflow.

## Performance Targets

| Metric | Target | Red line |
|--------|--------|----------|
| Startup | <500ms | <1000ms |
| Screenshot latency | <50ms | <100ms |
| UI response | <16ms (60fps) | <33ms (30fps) |
| Memory | 30-50MB | <200MB |
