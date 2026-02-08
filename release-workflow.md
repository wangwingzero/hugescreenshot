---
inclusion: manual
---
# 发布工作流

代码修改完成后，按以下步骤执行发布流程。

## 1. 更新版本号（自动判断）

根据 [语义化版本](https://semver.org/lang/zh-CN/) 规范自动判断版本号：

| 改动类型            | 版本变化 | 示例           |
| ------------------- | -------- | -------------- |
| 重大变更/不兼容 API | MAJOR +1 | 1.4.5 → 2.0.0 |
| 新功能（feat）      | MINOR +1 | 1.4.5 → 1.5.0 |
| Bug 修复（fix）     | PATCH +1 | 1.4.5 → 1.4.6 |
| 性能优化（perf）    | PATCH +1 | 1.4.5 → 1.4.6 |
| 重构/文档/测试      | PATCH +1 | 1.4.5 → 1.4.6 |

**⚠️ 强制规则：用户要求执行发布流程时，必须至少升级 PATCH 版本号。**

**判断规则：**

1. 查看 `git diff` 或 `git status` 确定改动内容
2. 根据改动类型决定是否升级版本
3. 如需升级，同步更新以下文件：

```
screenshot_tool/__init__.py                      → __version__ = "x.x.x"
build/虎哥截图-dir.spec                          → APP_VERSION = "x.x.x"
build/虎哥截图.iss                               → #define MyAppVersion "x.x.x"
.kiro/steering/product.md                        → 当前版本 vx.x.x
docs/README-public.md                            → version badge（如有新功能需同步更新）
website/index.html                               → 版本号和下载链接（CI 自动更新）
```

## 2. 更新 README（按需）

如果本次修改涉及新功能、重大 Bug 修复、依赖变更或使用方式变更，需更新 README。

**更新规则**：

- 修改功能描述、快捷键、使用方式 → 更新 `README.md`
- 版本号变更 → version badge 需要更新

## 3. 同步 guide.html（自动）

`website/guide.html` 是使用说明页面，版本号需要与 README 保持同步。

### 自动同步脚本

```powershell
cd D:\hugescreenshot
python scripts/readme_to_guide.py
```

脚本会自动：
1. 从 `README.md` 提取版本号
2. 更新 `website/guide.html` 中的版本号

### 手动更新（备选）

如果脚本不可用，手动修改 `website/guide.html` 中的：
```html
<span class="version">vX.X.X</span>
```

## 4. 运行测试

提交前运行相关测试，确保代码质量：

```powershell
# 运行所有测试
python -m pytest screenshot_tool/tests/ -v

# 或只运行核心测试（更快）
python -m pytest screenshot_tool/tests/test_version_consistency.py screenshot_tool/tests/test_ocr_backend_compatibility.py -v
```

确保所有测试通过后再提交。

## 5. 提交代码

```bash
git add .
git commit -m "<type>: <简短描述>

<详细说明（可选）>"
git push origin main
```

### Commit 类型规范

| 类型     | 说明                   |
| -------- | ---------------------- |
| feat     | 新功能                 |
| fix      | Bug 修复               |
| perf     | 性能优化               |
| refactor | 代码重构（不影响功能） |
| docs     | 文档更新               |
| style    | 代码格式调整           |
| test     | 测试相关               |
| chore    | 构建/工具变更          |

### Commit 示例

```
feat: 添加 AI 模式快捷键支持

- 新增 Alt+Q 触发 AI 截图模式
- 支持自动识别代码编辑器工作目录
- 集成 Cursor/Windsurf 等 AI IDE
```

```
perf: 优化截图绘制性能

- 预初始化绘制引擎，避免首次绘制卡顿
- 预初始化光标管理器和空间索引
- 添加异常处理确保组件初始化失败不影响整体功能
```

## 6. 构建安装包

从 v2.2.1 开始，使用 Inno Setup 生成安装包。

### 清理旧版本

打包前先删除 `dist/` 目录下的旧版本文件：

```powershell
# 删除旧版本
Remove-Item dist\HuGeScreenshot-*-Setup.exe -ErrorAction SilentlyContinue
Remove-Item dist\虎哥截图 -Recurse -ErrorAction SilentlyContinue
```

### 一键构建（推荐）

```powershell
cd D:\hugescreenshot
.venv\Scripts\activate
python build/build_installer.py
```

脚本会自动执行：
1. 检查版本号一致性（`__init__.py`、`虎哥截图-dir.spec`、`虎哥截图.iss`）
2. PyInstaller 目录模式打包
3. Inno Setup 编译安装包

### 分步构建

```powershell
# 1. PyInstaller 目录模式打包
pyinstaller build/虎哥截图-dir.spec --noconfirm --clean

# 2. Inno Setup 编译安装包
iscc build/虎哥截图.iss
```

### 打包产物

- 安装包：`dist/HuGeScreenshot-x.x.x-Setup.exe` - 约 150MB
- 目录包：`dist/虎哥截图/`

### 前置要求

- Python 3.11+
- PyInstaller
- Inno Setup 6（从 https://jrsoftware.org/isinfo.php 下载）

## 7. 发布到 GitHub

### 自动发布（推荐）

推送 tag 即可自动触发 GitHub Actions 构建并发布 Release：

```powershell
git tag vx.x.x
git push origin vx.x.x
```

CI 会自动：
1. 构建 Windows + macOS 安装包
2. 创建 GitHub Release 并上传安装包
3. 更新 README 和 website 中的版本号和下载链接
4. 同步 guide.html

### 手动发布（备选）

```powershell
# 创建 Release 并上传安装包
gh release create vx.x.x `
    dist/HuGeScreenshot-x.x.x-Setup.exe `
    --repo wangwingzero/hugescreenshot `
    --title "vx.x.x - <简短描述>" `
    --notes-file release-notes.md
```

或在 GitHub 网页操作：

1. 访问 https://github.com/wangwingzero/hugescreenshot → Releases → Draft a new release
2. 填写信息：
   - Tag: `vx.x.x`（如 v2.2.1）
   - Title: `vx.x.x - <简短描述>`
   - Description: 本次更新内容
3. 上传文件：
   - `HuGeScreenshot-x.x.x-Setup.exe` - 安装包
4. 点击 Publish release

### 安装目录

- 默认安装目录：`D:\虎哥截图\`
- 用户数据目录：`~/.screenshot_tool/`（与安装目录分离）

### Release Notes 模板

```markdown
## 🐛 Bug 修复 / ⚡ 性能优化 / ✨ 新功能
- 具体改动内容

## 📦 下载

下载 `HuGeScreenshot-x.x.x.exe` 即可使用。

## 使用说明

1. 下载 EXE 文件
2. 双击运行（首次启动需要几秒钟解压）
3. 默认热键 `Alt+A` 开始截图
4. 系统托盘会显示虎哥截图图标
```

## 快速检查清单

发布前运行以下检查脚本：

```powershell
# 版本一致性检查
python build/check_version_sync.py

# 运行后端相关测试
python -m pytest screenshot_tool/tests/test_ocr_backend_compatibility.py screenshot_tool/tests/test_backend_selector_properties.py screenshot_tool/tests/test_version_consistency.py -v
```

- [ ] 版本号已按语义化版本规范处理（5 个文件 + website/index.html 由 CI 自动更新）
- [ ] 版本一致性检查通过（`check_version_sync.py`）
- [ ] README 已更新
- [ ] guide.html 版本号已同步（运行 `python scripts/readme_to_guide.py`）
- [ ] 代码已提交并推送
- [ ] 旧版本 EXE 已删除
- [ ] EXE 已打包测试
- [ ] Release 已创建并上传安装包（仅版本升级时）

## 产品首页说明

产品首页托管在腾讯云轻量服务器上：

| URL                                        | 内容         | 说明                   |
| ------------------------------------------ | ------------ | ---------------------- |
| `https://hudawang.cn/`             | index.html   | 产品首页（国内可访问） |
| `https://hudawang.cn/confirm.html` | confirm.html | 邮箱验证成功页面       |
| `https://hudawang.cn/guide.html`   | guide.html   | 使用说明页面           |

**更新首页流程：**

```powershell
cd D:\hugescreenshot

# 1. 修改 website/ 目录下的文件
# 2. 提交到 GitHub
git add website/
git commit -m "更新网站"
git push origin main

# 3. 部署到腾讯云服务器
.\scripts\deploy_website.ps1
```

修改内容：
- 版本号（如 v2.0.0 → v2.1.0）
- 下载链接中的版本号

**架构说明：**

- 托管平台：腾讯云轻量服务器（宝塔面板 + Nginx）
- 服务器 IP：122.51.187.21
- 网站目录：`/www/wwwroot/hudawang`
- SSL 证书：Let's Encrypt（自动续签）
- 部署方式：本地脚本上传（`scripts/deploy_website.ps1`）
- 下载加速：自动选择最快的 GitHub 代理（支持多代理备份）

**首次部署前置条件：**

需要配置 SSH 免密登录（只需配置一次）：

```powershell
# 生成 SSH 密钥（如果没有）
ssh-keygen -t rsa -b 4096

# 复制公钥到服务器
type $env:USERPROFILE\.ssh\id_rsa.pub | ssh root@122.51.187.21 "cat >> ~/.ssh/authorized_keys"

# 测试连接
ssh root@122.51.187.21 "echo 连接成功"
```

## 注意事项

- 重构、文档更新、测试等不影响功能的改动，无需升级版本号
- feat/fix/perf 类型的改动需要升级版本并创建 Release
- 打包时会自动检查版本号一致性
- 新增模块或功能时，记得同步更新 steering 文档
