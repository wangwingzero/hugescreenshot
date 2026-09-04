//! 设置持久化
//!
//! 管理应用配置的存储和读取。
//!
//! # 功能
//!
//! - 从 JSON 配置文件加载应用设置
//! - 保存应用设置到 JSON 配置文件
//! - 支持配置文件不存在时使用默认值
//! - 线程安全的配置访问
//!
//! # 配置文件位置
//!
//! 配置文件存储在 Tauri 的 app_data_dir 目录下：
//! - Windows: `%APPDATA%/com.wangh.hugescreenshot/config.json`
//! - macOS: `~/Library/Application Support/com.wangh.hugescreenshot/config.json`
//! - Linux: `~/.config/com.wangh.hugescreenshot/config.json`
//!
//! # 使用示例
//!
//! ```ignore
//! use crate::database::settings::{load_config, save_config, get_config_path};
//!
//! // 获取配置文件路径
//! let config_path = get_config_path(&app)?;
//!
//! // 加载配置（文件不存在时返回默认配置）
//! let config = load_config(&config_path)?;
//!
//! // 修改配置
//! config.hotkeys.screenshot = "Ctrl+Alt+S".to_string();
//!
//! // 保存配置
//! save_config(&config_path, &config)?;
//! ```

use serde::{Deserialize, Serialize};
use std::fs;
use std::path::{Path, PathBuf};
use std::sync::RwLock;
use tauri::{AppHandle, Manager, Runtime};
use tracing::{debug, error, info, warn};

use crate::error::{HuGeError, HuGeResult};
use crate::hotkey::HotkeyConfig;

/// 配置文件名
const CONFIG_FILE_NAME: &str = "config.json";

/// 全局配置缓存
static CONFIG_CACHE: RwLock<Option<AppConfig>> = RwLock::new(None);

/// 应用配置
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct AppConfig {
    /// 通用设置
    pub general: GeneralConfig,
    /// 热键设置
    pub hotkeys: HotkeyConfig,
    /// 截图设置
    pub screenshot: ScreenshotConfig,
    /// 标注设置
    pub annotation: AnnotationConfig,
    /// OCR 设置
    pub ocr: OcrConfig,
    /// 贴图设置
    #[serde(default)]
    pub pin_image: PinImageConfig,
    /// 鼠标高亮设置
    #[serde(default)]
    pub mouse_highlight: MouseHighlightConfig,
    /// 网页转 Markdown 设置
    #[serde(default)]
    pub web_to_markdown: WebToMarkdownConfig,
    /// 文件转 Markdown 设置
    #[serde(default)]
    pub file_to_markdown: FileToMarkdownConfig,
    /// 通知设置
    #[serde(default)]
    pub notification: NotificationConfig,
    /// 更新设置
    #[serde(default)]
    pub update: UpdateConfig,
    /// 高级设置
    #[serde(default)]
    pub advanced: AdvancedConfig,
}

/// 通用设置
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct GeneralConfig {
    /// 界面语言
    pub language: String,
    /// 主题：light, dark, system
    pub theme: String,
    /// 开机自启动
    pub auto_start: bool,
    /// 关闭时最小化到托盘
    pub minimize_to_tray: bool,
    /// 是否启用自动更新
    #[serde(default = "default_auto_update_enabled")]
    pub auto_update_enabled: Option<bool>,
    /// 检查更新间隔（小时）
    #[serde(default)]
    pub update_check_interval_hours: Option<u32>,
    /// 是否在启动时检查更新
    #[serde(default = "default_check_update_on_startup")]
    pub check_update_on_startup: Option<bool>,
    /// 是否自动下载更新
    #[serde(default = "default_auto_download_update")]
    pub auto_download_update: Option<bool>,
    /// 是否自动安装更新
    #[serde(default)]
    pub auto_install_update: Option<bool>,
}

fn default_auto_update_enabled() -> Option<bool> {
    Some(true)
}

fn default_png() -> String {
    "png".to_string()
}

fn default_check_update_on_startup() -> Option<bool> {
    Some(true)
}

fn default_auto_download_update() -> Option<bool> {
    Some(true)
}

/// 截图设置
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ScreenshotConfig {
    /// 保存位置
    pub save_location: String,
    /// 默认格式（固定 png）
    #[serde(default = "default_png")]
    pub default_format: String,
    /// 是否包含鼠标光标
    pub include_mouse_cursor: bool,
    /// 截图后自动复制到剪贴板
    #[serde(default)]
    pub auto_copy: bool,
    /// 截图后自动保存到历史目录
    #[serde(default)]
    pub auto_save: bool,
}

/// 标注设置
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct AnnotationConfig {
    /// 默认描边颜色
    pub default_stroke_color: String,
    /// 默认描边宽度
    pub default_stroke_width: u32,
    /// 默认字体大小
    pub default_font_size: u32,
    /// 默认字体
    pub default_font_family: String,
}

/// OCR 设置
#[derive(Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct OcrConfig {
    /// OCR 引擎：local 或 baiduAccurate
    #[serde(default = "default_ocr_engine")]
    pub engine: String,
    /// 默认识别语言
    pub default_language: String,
    /// 自动翻译
    pub auto_translate: bool,
    /// 翻译提供商
    pub translate_provider: String,
    /// 翻译目标语言
    pub translate_target_lang: String,
    /// 百度 OCR API Key
    #[serde(default)]
    pub baidu_api_key: String,
    /// 百度 OCR Secret Key
    #[serde(default)]
    pub baidu_secret_key: String,
    /// 百度 OCR 是否检测文字方向
    #[serde(default = "default_true")]
    pub baidu_detect_direction: bool,
    /// 百度 OCR 是否返回置信度
    #[serde(default = "default_true")]
    pub baidu_probability: bool,
}

fn default_ocr_engine() -> String {
    "local".to_string()
}

impl std::fmt::Debug for OcrConfig {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("OcrConfig")
            .field("engine", &self.engine)
            .field("default_language", &self.default_language)
            .field("auto_translate", &self.auto_translate)
            .field("translate_provider", &self.translate_provider)
            .field("translate_target_lang", &self.translate_target_lang)
            .field("baidu_api_key", &redact_secret(&self.baidu_api_key))
            .field("baidu_secret_key", &redact_secret(&self.baidu_secret_key))
            .field("baidu_detect_direction", &self.baidu_detect_direction)
            .field("baidu_probability", &self.baidu_probability)
            .finish()
    }
}

fn redact_secret(value: &str) -> String {
    if value.is_empty() {
        String::new()
    } else {
        "********".to_string()
    }
}

/// 贴图设置
///
/// 配置贴图窗口的默认行为和外观。
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct PinImageConfig {
    /// 默认透明度 (0.1-1.0)
    #[serde(default = "default_pin_image_opacity")]
    pub default_opacity: f64,
    /// 鼠标穿透（允许点击穿过贴图窗口）
    #[serde(default)]
    pub mouse_through: bool,
    /// 记住窗口位置
    #[serde(default = "default_true")]
    pub remember_position: bool,
}

fn default_pin_image_opacity() -> f64 {
    1.0
}

fn default_true() -> bool {
    true
}

impl Default for PinImageConfig {
    fn default() -> Self {
        Self { default_opacity: 1.0, mouse_through: false, remember_position: true }
    }
}

/// 鼠标高亮设置
///
/// 配置截图和录屏时的鼠标高亮效果。
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct MouseHighlightConfig {
    /// 是否启用鼠标高亮
    #[serde(default)]
    pub enabled: bool,
    /// 高亮颜色（十六进制格式，如 #FFFF00）
    #[serde(default = "default_highlight_color")]
    pub color: String,
    /// 高亮半径（像素，范围 20-200）
    #[serde(default = "default_highlight_radius")]
    pub radius: u32,
    /// 高亮透明度 (0.1-1.0)
    #[serde(default = "default_highlight_opacity")]
    pub opacity: f64,
}

fn default_highlight_color() -> String {
    "#FFFF00".to_string()
}

fn default_highlight_radius() -> u32 {
    50
}

fn default_highlight_opacity() -> f64 {
    0.3
}

impl Default for MouseHighlightConfig {
    fn default() -> Self {
        Self { enabled: false, color: "#FFFF00".to_string(), radius: 50, opacity: 0.3 }
    }
}

/// 网页转 Markdown 设置
///
/// 配置网页内容转换为 Markdown 的行为。
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct WebToMarkdownConfig {
    /// 是否包含图片
    #[serde(default = "default_true")]
    pub include_images: bool,
    /// 是否包含链接
    #[serde(default = "default_true")]
    pub include_links: bool,
    /// 超时时间（秒，范围 5-120）
    #[serde(default = "default_web_timeout")]
    pub timeout: u32,
    /// 默认保存目录
    #[serde(default)]
    pub save_dir: String,
}

fn default_web_timeout() -> u32 {
    30
}

impl Default for WebToMarkdownConfig {
    fn default() -> Self {
        Self { include_images: true, include_links: true, timeout: 30, save_dir: String::new() }
    }
}

/// 文件转 Markdown 设置
///
/// 配置使用 MinerU API 将文件转换为 Markdown 的行为。
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct FileToMarkdownConfig {
    /// MinerU API Token
    #[serde(default)]
    pub api_token: String,
    /// 模型版本：pipeline 或 vlm
    #[serde(default = "default_model_version")]
    pub model_version: String,
    /// 默认保存目录
    #[serde(default)]
    pub save_dir: String,
}

fn default_model_version() -> String {
    "vlm".to_string()
}

impl Default for FileToMarkdownConfig {
    fn default() -> Self {
        Self { api_token: String::new(), model_version: "vlm".to_string(), save_dir: String::new() }
    }
}

/// 通知设置
///
/// 配置各种操作的通知显示。
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct NotificationConfig {
    /// 启动时显示通知
    #[serde(default = "default_true")]
    pub startup: bool,
    /// 截图保存时显示通知
    #[serde(default = "default_true")]
    pub screenshot_save: bool,
    /// 贴图时显示通知
    #[serde(default = "default_true")]
    pub pin_image: bool,
    /// 录屏完成时显示通知
    #[serde(default = "default_true")]
    pub recording_complete: bool,
    /// 软件更新时显示通知
    #[serde(default = "default_true")]
    pub software_update: bool,
}

impl Default for NotificationConfig {
    fn default() -> Self {
        Self {
            startup: true,
            screenshot_save: true,
            pin_image: true,
            recording_complete: true,
            software_update: true,
        }
    }
}

/// 更新设置
///
/// 配置应用程序的自动更新行为。
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct UpdateConfig {
    /// 自动检查更新
    #[serde(default = "default_true")]
    pub auto_check: bool,
    /// 上次检查时间（ISO 8601 格式）
    #[serde(default)]
    pub last_check_time: String,
    /// 跳过的版本号
    #[serde(default)]
    pub skip_version: String,
}

impl Default for UpdateConfig {
    fn default() -> Self {
        Self { auto_check: true, last_check_time: String::new(), skip_version: String::new() }
    }
}

/// 高级设置
///
/// 配置代理、调试日志和便携模式等高级选项。
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct AdvancedConfig {
    /// 是否启用代理
    #[serde(default)]
    pub proxy_enabled: bool,
    /// 代理类型：http 或 socks5
    #[serde(default = "default_proxy_type")]
    pub proxy_type: String,
    /// 代理主机
    #[serde(default)]
    pub proxy_host: String,
    /// 代理端口
    #[serde(default = "default_proxy_port")]
    pub proxy_port: u16,
    /// 是否启用调试日志
    #[serde(default)]
    pub debug_logging: bool,
    /// 调试日志路径
    #[serde(default)]
    pub debug_log_path: String,
    /// 便携模式
    #[serde(default)]
    pub portable_mode: bool,
}

fn default_proxy_type() -> String {
    "http".to_string()
}

fn default_proxy_port() -> u16 {
    8080
}

impl Default for AdvancedConfig {
    fn default() -> Self {
        Self {
            proxy_enabled: false,
            proxy_type: "http".to_string(),
            proxy_host: String::new(),
            proxy_port: 8080,
            debug_logging: false,
            debug_log_path: String::new(),
            portable_mode: false,
        }
    }
}

impl Default for AppConfig {
    fn default() -> Self {
        Self {
            general: GeneralConfig {
                language: "zh-CN".to_string(),
                theme: "system".to_string(),
                auto_start: false,
                minimize_to_tray: true,
                auto_update_enabled: Some(true),
                update_check_interval_hours: Some(24),
                check_update_on_startup: Some(true),
                auto_download_update: Some(true),
                auto_install_update: Some(false),
            },
            hotkeys: HotkeyConfig::default(),
            screenshot: ScreenshotConfig {
                save_location: "".to_string(), // 默认使用系统图片目录
                default_format: "png".to_string(),
                include_mouse_cursor: false,
                auto_copy: true,  // 默认开启自动复制
                auto_save: false, // 默认关闭自动保存
            },
            annotation: AnnotationConfig {
                default_stroke_color: "#FF0000".to_string(),
                default_stroke_width: 2,
                default_font_size: 16,
                default_font_family: "Microsoft YaHei".to_string(),
            },
            ocr: OcrConfig {
                engine: "local".to_string(),
                default_language: "ch".to_string(),
                auto_translate: false,
                translate_provider: "google".to_string(),
                translate_target_lang: "zh".to_string(),
                baidu_api_key: String::new(),
                baidu_secret_key: String::new(),
                baidu_detect_direction: true,
                baidu_probability: true,
            },
            pin_image: PinImageConfig::default(),
            mouse_highlight: MouseHighlightConfig::default(),
            web_to_markdown: WebToMarkdownConfig::default(),
            file_to_markdown: FileToMarkdownConfig::default(),
            notification: NotificationConfig::default(),
            update: UpdateConfig::default(),
            advanced: AdvancedConfig::default(),
        }
    }
}

/// 加载配置
///
/// 从指定路径加载配置文件。如果文件不存在，返回默认配置。
///
/// # 参数
///
/// - `config_path`: 配置文件路径
///
/// # 返回
///
/// 返回配置对象，如果文件不存在则返回默认配置
///
/// # 错误
///
/// - 文件存在但无法读取时返回错误
/// - JSON 解析失败时返回错误
pub fn load_config<P: AsRef<Path>>(config_path: P) -> HuGeResult<AppConfig> {
    let path = config_path.as_ref();
    debug!("加载配置文件: {:?}", path);

    // 检查文件是否存在
    if !path.exists() {
        info!("配置文件不存在，使用默认配置: {:?}", path);
        let default_config = AppConfig::default();

        // 更新缓存
        if let Ok(mut cache) = CONFIG_CACHE.write() {
            *cache = Some(default_config.clone());
        }

        return Ok(default_config);
    }

    // 读取文件内容
    let content = fs::read_to_string(path).map_err(|e| {
        error!("读取配置文件失败: {:?}, 错误: {}", path, e);
        HuGeError::ConfigError(format!("读取配置文件失败: {}", e))
    })?;

    // 解析 JSON
    let config: AppConfig = serde_json::from_str(&content).map_err(|e| {
        error!("解析配置文件失败: {:?}, 错误: {}", path, e);
        // 配置文件损坏时，返回默认配置并记录警告
        warn!("配置文件格式错误，将使用默认配置");
        HuGeError::ConfigError(format!("解析配置文件失败: {}", e))
    })?;

    info!("配置文件加载成功: {:?}", path);
    debug!("加载的配置: {:?}", config);

    // 更新缓存
    if let Ok(mut cache) = CONFIG_CACHE.write() {
        *cache = Some(config.clone());
    }

    Ok(config)
}

/// 保存配置
///
/// 将配置对象保存到指定路径的 JSON 文件。
/// 如果目录不存在，会自动创建。
///
/// # 参数
///
/// - `config_path`: 配置文件路径
/// - `config`: 配置对象
///
/// # 错误
///
/// - 无法创建目录时返回错误
/// - 无法写入文件时返回错误
pub fn save_config<P: AsRef<Path>>(config_path: P, config: &AppConfig) -> HuGeResult<()> {
    let path = config_path.as_ref();
    debug!("保存配置文件: {:?}", path);

    // 确保目录存在
    if let Some(parent) = path.parent() {
        if !parent.exists() {
            info!("创建配置目录: {:?}", parent);
            fs::create_dir_all(parent).map_err(|e| {
                error!("创建配置目录失败: {:?}, 错误: {}", parent, e);
                HuGeError::ConfigError(format!("创建配置目录失败: {}", e))
            })?;
        }
    }

    // 序列化为 JSON（格式化输出，便于人工编辑）
    let content = serde_json::to_string_pretty(config).map_err(|e| {
        error!("序列化配置失败: {}", e);
        HuGeError::ConfigError(format!("序列化配置失败: {}", e))
    })?;

    // 写入文件
    fs::write(path, &content).map_err(|e| {
        error!("写入配置文件失败: {:?}, 错误: {}", path, e);
        HuGeError::ConfigError(format!("写入配置文件失败: {}", e))
    })?;

    info!("配置文件保存成功: {:?}", path);

    // 更新缓存
    if let Ok(mut cache) = CONFIG_CACHE.write() {
        *cache = Some(config.clone());
    }

    Ok(())
}

/// 获取配置文件路径
///
/// 使用 Tauri 的 app_data_dir 获取配置文件的完整路径。
///
/// # 参数
///
/// - `app`: Tauri 应用句柄
///
/// # 返回
///
/// 返回配置文件的完整路径
pub fn get_config_path<R: Runtime>(app: &AppHandle<R>) -> HuGeResult<PathBuf> {
    let app_data_dir = app.path().app_data_dir().map_err(|e| {
        error!("获取应用数据目录失败: {}", e);
        HuGeError::ConfigError(format!("获取应用数据目录失败: {}", e))
    })?;

    let config_path = app_data_dir.join(CONFIG_FILE_NAME);
    debug!("配置文件路径: {:?}", config_path);

    Ok(config_path)
}

/// 获取缓存的配置
///
/// 从内存缓存中获取配置，如果缓存为空则返回 None。
/// 这是一个快速访问方法，不会读取文件。
///
/// # 返回
///
/// 返回缓存的配置，如果缓存为空则返回 None
pub fn get_cached_config() -> Option<AppConfig> {
    CONFIG_CACHE.read().ok().and_then(|cache| cache.clone())
}

/// 更新缓存的配置
///
/// 直接更新内存缓存中的配置，不会写入文件。
/// 通常在修改配置后调用，然后再调用 save_config 持久化。
///
/// # 参数
///
/// - `config`: 新的配置对象
pub fn update_cached_config(config: AppConfig) {
    if let Ok(mut cache) = CONFIG_CACHE.write() {
        *cache = Some(config);
    }
}

/// 加载热键配置
///
/// 从配置文件加载热键设置。如果配置文件不存在，返回默认热键配置。
///
/// # 参数
///
/// - `app`: Tauri 应用句柄
///
/// # 返回
///
/// 返回热键配置
pub fn load_hotkey_config<R: Runtime>(app: &AppHandle<R>) -> HuGeResult<HotkeyConfig> {
    let config_path = get_config_path(app)?;
    let config = load_config(&config_path)?;
    Ok(config.hotkeys)
}

/// 保存热键配置
///
/// 更新配置文件中的热键设置。
///
/// # 参数
///
/// - `app`: Tauri 应用句柄
/// - `hotkeys`: 新的热键配置
pub fn save_hotkey_config<R: Runtime>(app: &AppHandle<R>, hotkeys: HotkeyConfig) -> HuGeResult<()> {
    let config_path = get_config_path(app)?;

    // 加载现有配置（或默认配置）
    let mut config = load_config(&config_path)?;

    // 更新热键配置
    config.hotkeys = hotkeys;

    // 保存配置
    save_config(&config_path, &config)?;

    Ok(())
}

/// 初始化配置系统
///
/// 在应用启动时调用，确保配置目录存在并加载配置到缓存。
///
/// # 参数
///
/// - `app`: Tauri 应用句柄
///
/// # 返回
///
/// 返回加载的配置
pub fn init_config<R: Runtime>(app: &AppHandle<R>) -> HuGeResult<AppConfig> {
    info!("初始化配置系统...");

    let config_path = get_config_path(app)?;

    // 确保配置目录存在
    if let Some(parent) = config_path.parent() {
        if !parent.exists() {
            info!("创建配置目录: {:?}", parent);
            fs::create_dir_all(parent).map_err(|e| {
                error!("创建配置目录失败: {:?}, 错误: {}", parent, e);
                HuGeError::ConfigError(format!("创建配置目录失败: {}", e))
            })?;
        }
    }

    // 加载配置
    let config = load_config(&config_path)?;

    info!("配置系统初始化完成");
    Ok(config)
}

#[cfg(test)]
mod tests {
    use super::*;
    use serial_test::serial;
    use std::fs;
    use tempfile::tempdir;

    #[test]
    fn test_app_config_default() {
        let config = AppConfig::default();
        assert_eq!(config.general.language, "zh-CN");
        assert_eq!(config.screenshot.default_format, "png");
    }

    #[test]
    fn test_app_config_serialize() {
        let config = AppConfig::default();
        let json = serde_json::to_string_pretty(&config).unwrap();
        assert!(json.contains("zh-CN"));
        assert!(json.contains("Alt+X")); // 默认截图热键
    }

    #[test]
    fn test_load_config_file_not_exists() {
        let temp_dir = tempdir().unwrap();
        let config_path = temp_dir.path().join("nonexistent.json");

        // 文件不存在时应返回默认配置
        let config = load_config(&config_path).unwrap();
        assert_eq!(config.hotkeys.screenshot, "Alt+X");
        assert_eq!(config.hotkeys.ocr, "Ctrl+Shift+O");
    }

    #[test]
    fn test_save_and_load_config() {
        let temp_dir = tempdir().unwrap();
        let config_path = temp_dir.path().join("test_config.json");

        // 创建自定义配置
        let mut config = AppConfig::default();
        config.hotkeys.screenshot = "Ctrl+Alt+S".to_string();
        config.hotkeys.ocr = "Ctrl+Alt+O".to_string();
        config.general.theme = "dark".to_string();

        // 保存配置
        save_config(&config_path, &config).unwrap();

        // 验证文件存在
        assert!(config_path.exists());

        // 重新加载配置
        let loaded_config = load_config(&config_path).unwrap();

        // 验证配置内容
        assert_eq!(loaded_config.hotkeys.screenshot, "Ctrl+Alt+S");
        assert_eq!(loaded_config.hotkeys.ocr, "Ctrl+Alt+O");
        assert_eq!(loaded_config.general.theme, "dark");
    }

    #[test]
    fn test_save_config_creates_directory() {
        let temp_dir = tempdir().unwrap();
        let config_path = temp_dir.path().join("subdir").join("nested").join("config.json");

        // 目录不存在
        assert!(!config_path.parent().unwrap().exists());

        // 保存配置应自动创建目录
        let config = AppConfig::default();
        save_config(&config_path, &config).unwrap();

        // 验证文件和目录都存在
        assert!(config_path.exists());
        assert!(config_path.parent().unwrap().exists());
    }

    #[test]
    #[serial]
    fn test_config_cache() {
        // 清除缓存
        if let Ok(mut cache) = CONFIG_CACHE.write() {
            *cache = None;
        }

        // 初始时缓存为空
        assert!(get_cached_config().is_none());

        // 更新缓存
        let config = AppConfig::default();
        update_cached_config(config.clone());

        // 验证缓存已更新
        let cached = get_cached_config().unwrap();
        assert_eq!(cached.hotkeys.screenshot, config.hotkeys.screenshot);
    }

    #[test]
    #[serial]
    fn test_load_config_updates_cache() {
        let temp_dir = tempdir().unwrap();
        let config_path = temp_dir.path().join("cache_test.json");

        // 清除缓存
        if let Ok(mut cache) = CONFIG_CACHE.write() {
            *cache = None;
        }

        // 创建并保存自定义配置
        let mut config = AppConfig::default();
        config.hotkeys.screenshot = "Ctrl+Shift+X".to_string();

        let content = serde_json::to_string_pretty(&config).unwrap();
        fs::write(&config_path, &content).unwrap();

        // 加载配置
        let loaded = load_config(&config_path).unwrap();
        assert_eq!(loaded.hotkeys.screenshot, "Ctrl+Shift+X");

        // 验证缓存已更新
        let cached = get_cached_config().unwrap();
        assert_eq!(cached.hotkeys.screenshot, "Ctrl+Shift+X");
    }

    #[test]
    fn test_hotkey_config_roundtrip() {
        let temp_dir = tempdir().unwrap();
        let config_path = temp_dir.path().join("hotkey_test.json");

        // 创建自定义热键配置
        let config = AppConfig {
            hotkeys: HotkeyConfig {
                screenshot: "F1".to_string(),
                workbench: "F6".to_string(),
                ocr: "F2".to_string(),
                recording: "F3".to_string(),
                pin: "F4".to_string(),
                mouse_highlight: "F5".to_string(),
                file_search: "Alt+Space".to_string(),
            },
            ..Default::default()
        };

        // 保存
        save_config(&config_path, &config).unwrap();

        // 加载
        let loaded = load_config(&config_path).unwrap();

        // 验证热键配置
        assert_eq!(loaded.hotkeys.screenshot, "F1");
        assert_eq!(loaded.hotkeys.workbench, "F6");
        assert_eq!(loaded.hotkeys.ocr, "F2");
        assert_eq!(loaded.hotkeys.recording, "F3");
        assert_eq!(loaded.hotkeys.pin, "F4");
        assert_eq!(loaded.hotkeys.mouse_highlight, "F5");
        assert_eq!(loaded.hotkeys.file_search, "Alt+Space");
    }

    #[test]
    fn test_config_json_format() {
        let temp_dir = tempdir().unwrap();
        let config_path = temp_dir.path().join("format_test.json");

        let config = AppConfig::default();
        save_config(&config_path, &config).unwrap();

        // 读取文件内容
        let content = fs::read_to_string(&config_path).unwrap();

        // 验证是格式化的 JSON（包含换行和缩进）
        assert!(content.contains('\n'));
        assert!(content.contains("  ")); // 缩进

        // 验证包含所有必要字段
        assert!(content.contains("\"hotkeys\""));
        assert!(content.contains("\"screenshot\""));
        assert!(content.contains("\"general\""));
        assert!(content.contains("\"annotation\""));
    }

    // ========== 新增配置结构体测试 ==========

    #[test]
    fn test_pin_image_config_default() {
        let config = PinImageConfig::default();
        assert!((config.default_opacity - 1.0).abs() < f64::EPSILON);
        assert!(!config.mouse_through);
        assert!(config.remember_position);
    }

    #[test]
    fn test_mouse_highlight_config_default() {
        let config = MouseHighlightConfig::default();
        assert!(!config.enabled);
        assert_eq!(config.color, "#FFFF00");
        assert_eq!(config.radius, 50);
        assert!((config.opacity - 0.3).abs() < f64::EPSILON);
    }

    #[test]
    fn test_web_to_markdown_config_default() {
        let config = WebToMarkdownConfig::default();
        assert!(config.include_images);
        assert!(config.include_links);
        assert_eq!(config.timeout, 30);
        assert!(config.save_dir.is_empty());
    }

    #[test]
    fn test_file_to_markdown_config_default() {
        let config = FileToMarkdownConfig::default();
        assert!(config.api_token.is_empty());
        assert_eq!(config.model_version, "vlm");
        assert!(config.save_dir.is_empty());
    }

    #[test]
    fn test_notification_config_default() {
        let config = NotificationConfig::default();
        assert!(config.startup);
        assert!(config.screenshot_save);
        assert!(config.pin_image);
        assert!(config.recording_complete);
        assert!(config.software_update);
    }

    #[test]
    fn test_update_config_default() {
        let config = UpdateConfig::default();
        assert!(config.auto_check);
        assert!(config.last_check_time.is_empty());
        assert!(config.skip_version.is_empty());
    }

    #[test]
    fn test_advanced_config_default() {
        let config = AdvancedConfig::default();
        assert!(!config.proxy_enabled);
        assert_eq!(config.proxy_type, "http");
        assert!(config.proxy_host.is_empty());
        assert_eq!(config.proxy_port, 8080);
        assert!(!config.debug_logging);
        assert!(config.debug_log_path.is_empty());
        assert!(!config.portable_mode);
    }

    #[test]
    fn test_app_config_includes_new_sections() {
        let config = AppConfig::default();

        // 验证新增的配置节都存在且有正确的默认值
        assert!((config.pin_image.default_opacity - 1.0).abs() < f64::EPSILON);
        assert!(!config.mouse_highlight.enabled);
        assert!(config.web_to_markdown.include_images);
        assert_eq!(config.file_to_markdown.model_version, "vlm");
        assert!(config.notification.startup);
        assert!(config.update.auto_check);
        assert!(!config.advanced.proxy_enabled);
    }

    #[test]
    fn test_new_config_sections_serialize() {
        let config = AppConfig::default();
        let json = serde_json::to_string_pretty(&config).unwrap();

        // 验证新增的配置节都被序列化
        // 注意：使用 camelCase 格式，因为 serde 配置了 rename_all = "camelCase"
        assert!(json.contains("\"pinImage\""));
        assert!(json.contains("\"mouseHighlight\""));
        assert!(json.contains("\"webToMarkdown\""));
        assert!(json.contains("\"fileToMarkdown\""));
        assert!(json.contains("\"notification\""));
        assert!(json.contains("\"update\""));
        assert!(json.contains("\"advanced\""));
    }

    #[test]
    fn test_new_config_sections_roundtrip() {
        let temp_dir = tempdir().unwrap();
        let config_path = temp_dir.path().join("new_sections_test.json");

        // 创建自定义配置
        let mut config = AppConfig::default();
        config.pin_image.default_opacity = 0.8;
        config.pin_image.mouse_through = true;
        config.mouse_highlight.enabled = true;
        config.mouse_highlight.color = "#FF0000".to_string();
        config.mouse_highlight.radius = 100;
        config.web_to_markdown.timeout = 60;
        config.file_to_markdown.api_token = "test_token".to_string();
        config.notification.startup = false;
        config.advanced.proxy_enabled = true;
        config.advanced.proxy_port = 3128;

        // 保存
        save_config(&config_path, &config).unwrap();

        // 加载
        let loaded = load_config(&config_path).unwrap();

        // 验证所有新增配置节的值
        assert!((loaded.pin_image.default_opacity - 0.8).abs() < f64::EPSILON);
        assert!(loaded.pin_image.mouse_through);
        assert!(loaded.mouse_highlight.enabled);
        assert_eq!(loaded.mouse_highlight.color, "#FF0000");
        assert_eq!(loaded.mouse_highlight.radius, 100);
        assert_eq!(loaded.web_to_markdown.timeout, 60);
        assert_eq!(loaded.file_to_markdown.api_token, "test_token");
        assert!(!loaded.notification.startup);
        assert!(loaded.advanced.proxy_enabled);
        assert_eq!(loaded.advanced.proxy_port, 3128);
    }

    #[test]
    fn test_backward_compatibility_missing_new_sections() {
        let temp_dir = tempdir().unwrap();
        let config_path = temp_dir.path().join("old_config.json");

        // 模拟旧版配置文件（不包含新增的配置节）
        // 注意：使用 camelCase 格式，因为 serde 配置了 rename_all = "camelCase"
        let old_config_json = r##"{
            "general": {
                "language": "zh-CN",
                "theme": "dark",
                "autoStart": false,
                "minimizeToTray": true
            },
            "hotkeys": {
                "screenshot": "Alt+X",
                "ocr": "Ctrl+Shift+O",
                "recording": "Ctrl+Shift+R",
                "pin": "Ctrl+Shift+P"
            },
            "screenshot": {
                "saveLocation": "",
                "defaultFormat": "png",
                "includeMouseCursor": false
            },
            "annotation": {
                "defaultStrokeColor": "#FF0000",
                "defaultStrokeWidth": 2,
                "defaultFontSize": 16,
                "defaultFontFamily": "Microsoft YaHei"
            },
            "ocr": {
                "defaultLanguage": "ch",
                "autoTranslate": false,
                "translateProvider": "google",
                "translateTargetLang": "zh"
            }
        }"##;

        fs::write(&config_path, old_config_json).unwrap();

        // 加载旧配置应该成功，新增的配置节使用默认值
        let loaded = load_config(&config_path).unwrap();

        // 验证旧配置被正确加载
        assert_eq!(loaded.general.theme, "dark");
        assert_eq!(loaded.hotkeys.screenshot, "Alt+X");
        assert_eq!(loaded.ocr.engine, "local");
        assert!(loaded.ocr.baidu_api_key.is_empty());
        assert!(loaded.ocr.baidu_secret_key.is_empty());
        assert!(loaded.ocr.baidu_detect_direction);
        assert!(loaded.ocr.baidu_probability);

        // 验证新增的配置节使用默认值
        assert!((loaded.pin_image.default_opacity - 1.0).abs() < f64::EPSILON);
        assert!(!loaded.mouse_highlight.enabled);
        assert!(loaded.web_to_markdown.include_images);
        assert_eq!(loaded.file_to_markdown.model_version, "vlm");
        assert!(loaded.notification.startup);
        assert!(loaded.update.auto_check);
        assert!(!loaded.advanced.proxy_enabled);
    }
}

// ============================================================================
// 属性测试 (Property-Based Testing)
// ============================================================================

#[cfg(test)]
mod property_tests {
    use super::*;
    use proptest::prelude::*;
    use tempfile::tempdir;

    // ========================================================================
    // Feature: rust-performance-optimization
    // Property 6: 配置向后兼容性
    // Validates: Requirements 5.6
    // ========================================================================

    proptest! {
        #![proptest_config(ProptestConfig::with_cases(50))]

        /// Property: 配置序列化/反序列化往返一致性
        ///
        /// 对于任意配置值，序列化后再反序列化应该得到相同的值。
        #[test]
        fn prop_config_serialization_roundtrip(
            language in "(zh-CN|en-US|ja-JP)",
            theme in "(light|dark|system)",
            screenshot_hotkey in "[A-Z]",
            opacity in 0.1f64..=1.0,
            radius in 10u32..=200,
        ) {
            let temp_dir = tempdir().unwrap();
            let config_path = temp_dir.path().join("prop_test.json");

            // 创建配置
            let mut config = AppConfig::default();
            config.general.language = language.clone();
            config.general.theme = theme.clone();
            config.hotkeys.screenshot = format!("Alt+{}", screenshot_hotkey);
            config.pin_image.default_opacity = opacity;
            config.mouse_highlight.radius = radius;

            // 保存
            save_config(&config_path, &config).unwrap();

            // 加载
            let loaded = load_config(&config_path).unwrap();

            // 验证值保持不变
            prop_assert_eq!(loaded.general.language, language,
                "语言设置应该保持不变");
            prop_assert_eq!(loaded.general.theme, theme,
                "主题设置应该保持不变");
            prop_assert_eq!(loaded.hotkeys.screenshot, format!("Alt+{}", screenshot_hotkey),
                "热键设置应该保持不变");
            prop_assert!((loaded.pin_image.default_opacity - opacity).abs() < 0.001,
                "透明度设置应该保持不变");
            prop_assert_eq!(loaded.mouse_highlight.radius, radius,
                "高亮半径设置应该保持不变");
        }

        /// Property: 默认配置总是有效的
        ///
        /// 默认配置应该能够成功序列化和反序列化。
        #[test]
        fn prop_default_config_always_valid(
            _dummy in 0u8..1, // 只是为了让 proptest 运行
        ) {
            let config = AppConfig::default();

            // 序列化应该成功
            let json = serde_json::to_string(&config);
            prop_assert!(json.is_ok(), "默认配置应该能够序列化");

            // 反序列化应该成功
            let parsed: Result<AppConfig, _> = serde_json::from_str(&json.unwrap());
            prop_assert!(parsed.is_ok(), "默认配置应该能够反序列化");
        }

        /// Property: 配置文件缺失字段时使用默认值
        ///
        /// 当配置文件缺少某些字段时，应该使用默认值而不是失败。
        #[test]
        fn prop_missing_fields_use_defaults(
            language in "(zh-CN|en-US)",
            theme in "(light|dark)",
        ) {
            let temp_dir = tempdir().unwrap();
            let config_path = temp_dir.path().join("partial_config.json");

            // 创建只包含部分字段的配置
            let partial_json = format!(r##"{{
                "general": {{
                    "language": "{}",
                    "theme": "{}",
                    "autoStart": false,
                    "minimizeToTray": true
                }},
                "hotkeys": {{
                    "screenshot": "Alt+X",
                    "ocr": "Ctrl+Shift+O",
                    "recording": "Ctrl+Shift+R",
                    "pin": "Ctrl+Shift+P"
                }},
                "screenshot": {{
                    "saveLocation": "",
                    "defaultFormat": "png",
                    "includeMouseCursor": false
                }},
                "annotation": {{
                    "defaultStrokeColor": "#FF0000",
                    "defaultStrokeWidth": 2,
                    "defaultFontSize": 16,
                    "defaultFontFamily": "Microsoft YaHei"
                }},
                "ocr": {{
                    "defaultLanguage": "ch",
                    "autoTranslate": false,
                    "translateProvider": "google",
                    "translateTargetLang": "zh"
                }}
            }}"##, language, theme);

            std::fs::write(&config_path, &partial_json).unwrap();

            // 加载应该成功
            let loaded = load_config(&config_path);
            prop_assert!(loaded.is_ok(), "缺少字段的配置应该能够加载");

            let config = loaded.unwrap();

            // 验证已有字段被正确加载
            prop_assert_eq!(config.general.language, language,
                "已有字段应该被正确加载");
            prop_assert_eq!(config.general.theme, theme,
                "已有字段应该被正确加载");

            // 验证缺失字段使用默认值
            prop_assert!((config.pin_image.default_opacity - 1.0).abs() < 0.001,
                "缺失的 pin_image.default_opacity 应该使用默认值");
            prop_assert!(!config.mouse_highlight.enabled,
                "缺失的 mouse_highlight.enabled 应该使用默认值");
            prop_assert!(config.notification.startup,
                "缺失的 notification.startup 应该使用默认值");
        }

        /// Property: 热键配置往返一致性
        ///
        /// 对于任意热键组合，序列化后再反序列化应该得到相同的值。
        #[test]
        fn prop_hotkey_config_roundtrip(
            modifier in "(Alt|Ctrl|Shift|Ctrl\\+Shift|Alt\\+Shift)",
            key in "[A-Z0-9]",
        ) {
            let temp_dir = tempdir().unwrap();
            let config_path = temp_dir.path().join("hotkey_prop_test.json");

            let hotkey = format!("{}+{}", modifier, key);

            let mut config = AppConfig::default();
            config.hotkeys.screenshot = hotkey.clone();

            save_config(&config_path, &config).unwrap();
            let loaded = load_config(&config_path).unwrap();

            prop_assert_eq!(loaded.hotkeys.screenshot, hotkey,
                "热键配置应该保持不变");
        }
    }
}
