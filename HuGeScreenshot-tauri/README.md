# 虎哥截图 - Tauri 应用

完整项目说明、Release 与构建信息请查看仓库根目录 [README.md](../README.md)。

## 常用命令

```bash
npm install
npm run tauri:dev
npm run build
npm run test:run

cd src-tauri
cargo test
cargo test --features proptest
```

## 结构

- `src/`：Vue 3 + TypeScript 前端
- `src-tauri/`：Rust 后端
- `scripts/`：构建与发布脚本
- `infra/`：Cloudflare / R2 辅助
- `website/`：网站相关静态文件
