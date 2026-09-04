# Tauri Commands API 文档

本文档记录虎哥截图 Tauri 版本的所有 Rust 命令接口，供前端 Vue 调用。

---

## 目录

- [截图命令](#截图命令)
- [窗口检测命令](#窗口检测命令)
- [覆盖窗口命令](#覆盖窗口命令)
- [钉图窗口命令](#钉图窗口命令)
- [热键命令](#热键命令)
- [Sidecar 命令](#sidecar-命令)
- [数据类型](#数据类型)

---

## 截图命令

### `capture_screen`

捕获指定显示器的屏幕。

```typescript
import { invoke } from '@tauri-apps/api/core';

const result = await invoke<CaptureResult>('capture_screen', {
  monitor: 0  // 可选，默认主显示器
});
```

**参数**

| 名称 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `monitor` | `number \| null` | 否 | 显示器 ID，`null` 表示主显示器 |

**返回值**: `CaptureResult`

**注意事项**
- 返回的 `path` 是绝对路径，需使用 `convertFileSrc()` 转换
- `width` 和 `height` 是物理像素尺寸
- `dpr` 是设备像素比

---

### `capture_all_monitors`

捕获所有显示器的屏幕。

```typescript
const results = await invoke<CaptureResult[]>('capture_all_monitors');
```

**参数**: 无

**返回值**: `CaptureResult[]`（按 `monitor_id` 排序）

---

### `get_screen_info`

获取所有显示器信息（不截图）。

```typescript
const screens = await invoke<ScreenInfo[]>('get_screen_info');
```

**参数**: 无

**返回值**: `ScreenInfo[]`

---

### `capture_region` ⏳

截取指定区域（开发中）。

```typescript
const result = await invoke<CaptureResult>('capture_region', {
  rect: { x: 0, y: 0, width: 800, height: 600 }
});
```

**状态**: 未实现

---

### `capture_window` ⏳

截取指定窗口（开发中）。

```typescript
const result = await invoke<CaptureResult>('capture_window', {
  hwnd: 12345
});
```

**状态**: 未实现

---

## 窗口检测命令

### `detect_window_at`

检测指定坐标下的窗口。

```typescript
const window = await invoke<WindowInfo | null>('detect_window_at', {
  x: 500,
  y: 300
});
```

**参数**

| 名称 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `x` | `number` | 是 | X 坐标（物理像素） |
| `y` | `number` | 是 | Y 坐标（物理像素） |

**返回值**: `WindowInfo | null`

**注意事项**
- 返回最顶层可见窗口的根窗口
- 如果坐标下没有窗口，返回 `null`
- 使用 `DwmGetWindowAttribute` 获取真实边界（排除阴影）

---

### `get_all_windows`

获取所有可见窗口列表。

```typescript
const windows = await invoke<WindowInfo[]>('get_all_windows');
```

**参数**: 无

**返回值**: `WindowInfo[]`

**过滤规则**
- 只返回可见的顶级窗口
- 排除工具窗口（如任务栏按钮）
- 排除无标题的窗口
- 排除尺寸为 0 的窗口

---

## 覆盖窗口命令

### `create_overlay_window`

在指定显示器上创建全屏透明覆盖窗口。

```typescript
await invoke('create_overlay_window', { monitorId: 0 });
```

**参数**

| 名称 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `monitorId` | `number` | 是 | 目标显示器 ID |

**返回值**: `void`

**窗口属性**
- `transparent`: true
- `decorations`: false
- `always_on_top`: true
- `skip_taskbar`: true
- `resizable`: false

**事件**: 创建后发送 `overlay-init` 事件到前端

---

### `create_all_overlay_windows`

在所有显示器上创建覆盖窗口。

```typescript
const count = await invoke<number>('create_all_overlay_windows');
```

**参数**: 无

**返回值**: `number` - 成功创建的窗口数量

---

### `close_overlay_window`

关闭指定显示器的覆盖窗口。

```typescript
await invoke('close_overlay_window', { monitorId: 0 });
```

**参数**

| 名称 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `monitorId` | `number` | 是 | 目标显示器 ID |

---

### `close_all_overlays`

关闭所有覆盖窗口。

```typescript
await invoke('close_all_overlays');
```

---

### `get_overlay_windows`

获取所有覆盖窗口的标签列表。

```typescript
const labels = await invoke<string[]>('get_overlay_windows');
```

---

### `set_overlay_ignore_cursor`

设置覆盖窗口是否忽略鼠标事件。

```typescript
await invoke('set_overlay_ignore_cursor', {
  monitorId: 0,
  ignore: true
});
```

**参数**

| 名称 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `monitorId` | `number` | 是 | 目标显示器 ID |
| `ignore` | `boolean` | 是 | 是否忽略鼠标事件 |

---

## 钉图窗口命令

### `create_pin_window`

创建钉图窗口，将截图固定在屏幕上。

```typescript
const label = await invoke<string>('create_pin_window', {
  imagePath: '/tmp/screenshot.png',
  rect: { x: 100, y: 100, width: 400, height: 300 }
});
```

**参数**

| 名称 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `imagePath` | `string` | 是 | 截图文件路径 |
| `rect` | `Rect` | 是 | 窗口位置和大小 |

**返回值**: `string` - 窗口标签（如 `pin-0`）

**窗口属性**
- `decorations`: false
- `always_on_top`: true
- `resizable`: true
- `skip_taskbar`: true

**事件**: 创建后发送 `pin-init` 事件到前端

---

### `set_pin_opacity`

设置钉图窗口透明度。

```typescript
await invoke('set_pin_opacity', {
  label: 'pin-0',
  opacity: 0.5
});
```

**参数**

| 名称 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `label` | `string` | 是 | 窗口标签 |
| `opacity` | `number` | 是 | 透明度 (0.0 - 1.0) |

**事件**: 发送 `pin-opacity-changed` 事件到前端

---

### `close_pin_window`

关闭指定钉图窗口。

```typescript
await invoke('close_pin_window', { label: 'pin-0' });
```

---

### `close_all_pin_windows`

关闭所有钉图窗口。

```typescript
const count = await invoke<number>('close_all_pin_windows');
```

---

### `get_pin_windows`

获取所有钉图窗口的标签列表。

```typescript
const labels = await invoke<string[]>('get_pin_windows');
```

---

## 热键命令

### `get_hotkey_config`

获取当前热键配置。

```typescript
const config = await invoke<HotkeyConfig>('get_hotkey_config');
```

**返回值**: `HotkeyConfig`

---

### `set_hotkey_config`

更新所有热键配置。

```typescript
await invoke('set_hotkey_config', {
  config: {
    screenshot: 'Alt+A',
    ocr: 'Alt+O',
    recording: 'Alt+R',
    pin: 'Alt+P'
  }
});
```

**参数**

| 名称 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `config` | `HotkeyConfig` | 是 | 新的热键配置 |

---

### `check_hotkey_available`

检查热键是否可用。

```typescript
const available = await invoke<boolean>('check_hotkey_available', {
  shortcut: 'Alt+A'
});
```

**参数**

| 名称 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `shortcut` | `string` | 是 | 热键组合字符串 |

**返回值**: `boolean`

**注意**: 只能检测当前应用是否已注册该热键

---

### `update_single_hotkey`

更新单个热键绑定。

```typescript
await invoke('update_single_hotkey', {
  action: 'screenshot',
  oldShortcut: 'Alt+A',
  newShortcut: 'Alt+S'
});
```

**参数**

| 名称 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `action` | `string` | 是 | 热键动作（screenshot/ocr/recording/pin） |
| `oldShortcut` | `string \| null` | 否 | 旧的热键组合 |
| `newShortcut` | `string` | 是 | 新的热键组合 |

---

## Sidecar 命令

### `call_ocr` ⏳

调用 OCR 服务（开发中）。

```typescript
const result = await invoke<OcrResult>('call_ocr', {
  imagePath: '/tmp/screenshot.png'
});
```

**状态**: 未实现

---

### `call_translate` ⏳

调用翻译服务（开发中）。

```typescript
const result = await invoke<string>('call_translate', {
  text: 'Hello',
  targetLang: 'zh-CN',
  provider: 'google'  // 可选
});
```

**状态**: 未实现

---

### `call_anki` ⏳

调用 Anki 制卡服务（开发中）。

```typescript
const cardId = await invoke<number>('call_anki', {
  front: '单词',
  back: '翻译',
  deck: 'Default',
  imagePath: '/tmp/screenshot.png'  // 可选
});
```

**状态**: 未实现

---

### `check_sidecar_status`

检查 Sidecar 状态。

```typescript
const running = await invoke<boolean>('check_sidecar_status');
```

---

## 数据类型

### `CaptureResult`

截图捕获结果。

```typescript
interface CaptureResult {
  /** 临时文件路径 */
  path: string;
  /** 图像宽度（物理像素） */
  width: number;
  /** 图像高度（物理像素） */
  height: number;
  /** 设备像素比 (DPR) */
  dpr: number;
  /** 显示器 ID */
  monitor_id: number;
  /** 显示器 X 坐标（可能为负） */
  x: number;
  /** 显示器 Y 坐标（可能为负） */
  y: number;
}
```

---

### `ScreenInfo`

显示器信息。

```typescript
interface ScreenInfo {
  /** 显示器 ID */
  id: number;
  /** X 坐标（虚拟屏幕坐标系） */
  x: number;
  /** Y 坐标（虚拟屏幕坐标系） */
  y: number;
  /** 宽度（物理像素） */
  width: number;
  /** 高度（物理像素） */
  height: number;
  /** 缩放因子 (DPR) */
  scale_factor: number;
  /** 是否为主显示器 */
  is_primary: boolean;
}
```

---

### `Rect`

矩形区域。

```typescript
interface Rect {
  x: number;
  y: number;
  width: number;
  height: number;
}
```

---

### `WindowInfo`

窗口信息。

```typescript
interface WindowInfo {
  /** 窗口句柄 */
  hwnd: number;
  /** 窗口标题 */
  title: string;
  /** 窗口类名 */
  class_name: string;
  /** 窗口边界（逻辑像素） */
  rect: Rect;
  /** 窗口边界（物理像素） */
  physical_rect: Rect;
}
```

---

### `HotkeyConfig`

热键配置。

```typescript
interface HotkeyConfig {
  /** 截图热键 */
  screenshot: string;
  /** OCR 热键 */
  ocr: string;
  /** 录屏热键 */
  recording: string;
  /** 钉图热键 */
  pin: string;
}
```

---

### `OcrResult`

OCR 识别结果。

```typescript
interface OcrResult {
  /** 识别的文本 */
  text: string;
  /** 文本区域列表 */
  boxes: OcrBox[];
  /** 处理耗时（秒） */
  elapse: number;
}

interface OcrBox {
  /** 文本内容 */
  text: string;
  /** 置信度 (0.0 - 1.0) */
  confidence: number;
  /** 边界框坐标 */
  box_coords: number[][];
}
```

---

### `PinWindowInitInfo`

钉图窗口初始化信息。

```typescript
interface PinWindowInitInfo {
  /** 窗口标签 */
  label: string;
  /** 图像路径（asset:// 协议） */
  imagePath: string;
  /** 窗口宽度 */
  width: number;
  /** 窗口高度 */
  height: number;
  /** 初始透明度 */
  opacity: number;
}
```

---

## 前端事件

### `overlay-init`

覆盖窗口初始化事件。

```typescript
import { listen } from '@tauri-apps/api/event';

await listen('overlay-init', (event) => {
  const data = event.payload as {
    monitorId: number;
    position: { x: number; y: number };
    size: { width: number; height: number };
    scaleFactor: number;
    name: string;
  };
});
```

---

### `pin-init`

钉图窗口初始化事件。

```typescript
await listen('pin-init', (event) => {
  const data = event.payload as PinWindowInitInfo;
});
```

---

### `pin-opacity-changed`

钉图窗口透明度变更事件。

```typescript
await listen('pin-opacity-changed', (event) => {
  const opacity = event.payload as number;
});
```

---

## 错误处理

所有命令在失败时会返回错误信息，前端应使用 try-catch 处理：

```typescript
try {
  const result = await invoke('capture_screen');
} catch (error) {
  console.error('截图失败:', error);
}
```

常见错误类型：
- `CaptureError`: 截图相关错误
- `WindowError`: 窗口操作错误
- `HotkeyError`: 热键注册错误
- `SidecarError`: Sidecar 通信错误
- `FileError`: 文件操作错误

---

## 状态说明

- ✅ 已实现
- ⏳ 开发中
- 📋 计划中
