//! 后台 OCR 缓存管理器
//!
//! 在系统空闲时自动执行 OCR 并缓存结果，提升用户体验。
//!
//! # 设计原则
//!
//! - **用户无感**: 只在系统空闲且资源充足时执行
//! - **优雅中断**: 用户活动时立即停止
//! - **分片处理**: 每处理一张图片后检查系统状态
//! - **低优先级**: 不影响前台任务
//!
//! # 参考
//!
//! 参考 Python 版本的 `background_ocr_cache_manager.py`

use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::Arc;
use std::time::Duration;

use tokio::sync::{Mutex, Notify};
use tokio::time::sleep;
use tracing::{debug, error, info, warn};

use super::engine::OcrEngine;
use crate::database::HistoryDatabase;
use crate::error::HuGeResult;

/// 默认空闲时间阈值（秒）
const DEFAULT_IDLE_THRESHOLD_SECS: u64 = 5;

/// 默认内存使用阈值（百分比）
const DEFAULT_MEMORY_THRESHOLD_PERCENT: f64 = 70.0;

/// 每批处理的记录数
const BATCH_SIZE: u32 = 5;

/// 处理间隔（毫秒）
const PROCESS_INTERVAL_MS: u64 = 500;

/// 检查间隔（秒）
const CHECK_INTERVAL_SECS: u64 = 10;

/// 后台 OCR 缓存管理器
pub struct BackgroundOcrCache {
    /// 是否正在运行
    is_running: AtomicBool,
    /// 是否暂停
    is_paused: AtomicBool,
    /// 空闲时间阈值（秒）
    idle_threshold_secs: AtomicU64,
    /// 内存使用阈值（百分比）
    memory_threshold_percent: f64,
    /// 停止通知
    stop_notify: Arc<Notify>,
    /// 已处理的记录数
    processed_count: AtomicU64,
}

impl Default for BackgroundOcrCache {
    fn default() -> Self {
        Self::new()
    }
}

impl BackgroundOcrCache {
    /// 创建新的后台 OCR 缓存管理器
    pub fn new() -> Self {
        Self {
            is_running: AtomicBool::new(false),
            is_paused: AtomicBool::new(false),
            idle_threshold_secs: AtomicU64::new(DEFAULT_IDLE_THRESHOLD_SECS),
            memory_threshold_percent: DEFAULT_MEMORY_THRESHOLD_PERCENT,
            stop_notify: Arc::new(Notify::new()),
            processed_count: AtomicU64::new(0),
        }
    }

    /// 启动后台处理
    ///
    /// # 参数
    ///
    /// - `db`: 数据库实例（包装在 Arc<Mutex<Option<...>>> 中，与 HistoryState 兼容）
    pub async fn start(&self, db: Arc<Mutex<Option<HistoryDatabase>>>) -> HuGeResult<()> {
        if self.is_running.swap(true, Ordering::SeqCst) {
            warn!("后台 OCR 缓存已在运行中");
            return Ok(());
        }

        info!("启动后台 OCR 缓存管理器");

        let is_paused = &self.is_paused;
        let stop_notify = Arc::clone(&self.stop_notify);
        let processed_count = &self.processed_count;

        // 主处理循环
        loop {
            // 检查是否应该停止
            tokio::select! {
                _ = stop_notify.notified() => {
                    info!("收到停止信号，退出后台 OCR 缓存处理");
                    break;
                }
                _ = sleep(Duration::from_secs(CHECK_INTERVAL_SECS)) => {
                    // 继续检查
                }
            }

            // 检查是否暂停
            if is_paused.load(Ordering::Relaxed) {
                debug!("后台 OCR 缓存已暂停");
                continue;
            }

            // 检查系统状态
            if !self.should_process() {
                debug!("系统不空闲或资源不足，跳过处理");
                continue;
            }

            // 获取数据库锁并获取未缓存的记录
            let records = {
                let db_guard = db.lock().await;
                match db_guard.as_ref() {
                    Some(database) => match database.get_uncached_ocr_records(BATCH_SIZE) {
                        Ok(r) => r,
                        Err(e) => {
                            error!("获取未缓存记录失败: {}", e);
                            continue;
                        }
                    },
                    None => {
                        debug!("数据库未初始化，跳过处理");
                        continue;
                    }
                }
            };

            if records.is_empty() {
                debug!("没有待处理的 OCR 记录");
                continue;
            }

            info!("开始处理 {} 条未缓存 OCR 记录", records.len());

            for record in records {
                // 再次检查是否应该继续
                if !self.should_process() {
                    info!("用户活动检测到，暂停后台 OCR 处理");
                    break;
                }

                // 检查文件是否存在
                let file_path = std::path::Path::new(&record.file_path);
                if !file_path.exists() {
                    warn!("OCR 跳过: 文件不存在 (id={}, path={})", record.id, record.file_path);
                    // 标记为已处理（空文本），避免重复尝试
                    let db_guard = db.lock().await;
                    if let Some(database) = db_guard.as_ref() {
                        let _ = database.update_ocr_cache(record.id, "[文件不存在]");
                    }
                    continue;
                }

                // 调用原生 OCR 引擎
                match self.process_ocr(&record.file_path).await {
                    Ok(ocr_text) => {
                        // 更新数据库
                        let db_guard = db.lock().await;
                        if let Some(database) = db_guard.as_ref() {
                            // 如果 OCR 结果为空，保存一个占位符避免重复处理
                            let text_to_save = if ocr_text.trim().is_empty() {
                                "[无文字内容]".to_string()
                            } else {
                                ocr_text.clone()
                            };
                            if let Err(e) = database.update_ocr_cache(record.id, &text_to_save) {
                                error!("更新 OCR 缓存失败 (id={}): {}", record.id, e);
                            } else {
                                processed_count.fetch_add(1, Ordering::Relaxed);
                                info!(
                                    "OCR 缓存更新成功: id={}, 文本长度={}",
                                    record.id,
                                    text_to_save.len()
                                );
                            }
                        }
                    }
                    Err(e) => {
                        let error_msg = e.to_string();
                        warn!("OCR 处理失败 (id={}): {}", record.id, error_msg);
                        // 标记为已处理（错误信息），避免重复尝试
                        // 限制错误信息长度，避免数据库字段过长
                        let truncated_error = if error_msg.len() > 100 {
                            format!("{}...", &error_msg[..100])
                        } else {
                            error_msg
                        };
                        let db_guard = db.lock().await;
                        if let Some(database) = db_guard.as_ref() {
                            let _ = database.update_ocr_cache(
                                record.id,
                                &format!("[OCR失败: {}]", truncated_error),
                            );
                        }
                    }
                }

                // 短暂休眠，让出 CPU
                sleep(Duration::from_millis(PROCESS_INTERVAL_MS)).await;
            }
        }

        self.is_running.store(false, Ordering::SeqCst);
        info!("后台 OCR 缓存管理器已停止");

        Ok(())
    }

    /// 停止后台处理
    pub fn stop(&self) {
        info!("请求停止后台 OCR 缓存处理");
        self.is_running.store(false, Ordering::SeqCst);
        self.stop_notify.notify_one();
    }

    /// 暂停后台处理
    pub fn pause(&self) {
        info!("暂停后台 OCR 缓存处理");
        self.is_paused.store(true, Ordering::Relaxed);
    }

    /// 恢复后台处理
    pub fn resume(&self) {
        info!("恢复后台 OCR 缓存处理");
        self.is_paused.store(false, Ordering::Relaxed);
    }

    /// 检查是否应该处理
    ///
    /// 条件：
    /// 1. 系统空闲时间超过阈值
    /// 2. 内存使用低于阈值
    fn should_process(&self) -> bool {
        let idle_time = get_system_idle_time();
        let threshold = self.idle_threshold_secs.load(Ordering::Relaxed);

        if idle_time < threshold {
            debug!("系统空闲时间 {}s < 阈值 {}s", idle_time, threshold);
            return false;
        }

        let memory_percent = get_memory_usage_percent();
        if memory_percent > self.memory_threshold_percent {
            debug!("内存使用 {:.1}% > 阈值 {:.1}%", memory_percent, self.memory_threshold_percent);
            return false;
        }

        true
    }

    /// 处理单个图片的 OCR（使用原生 Rust OCR 引擎，高精度模式）
    ///
    /// 后台处理使用高精度模式：
    /// - 更大的检测输入尺寸（960 vs 480-640）
    /// - 更低的置信度阈值（0.3 vs 0.5）
    /// - 不缩放原始图像，保留全部细节
    /// - 精度优先，不在乎速度
    async fn process_ocr(&self, image_path: &str) -> HuGeResult<String> {
        // 获取 OCR 引擎单例
        let engine = OcrEngine::instance()
            .map_err(|e| crate::error::HuGeError::OcrError(format!("OCR 引擎初始化失败: {}", e)))?;

        // 使用高精度模式执行 OCR（后台不着急，精度第一）
        let result = engine
            .recognize_high_accuracy(image_path)
            .await
            .map_err(|e| crate::error::HuGeError::OcrError(format!("OCR 识别失败: {}", e)))?;

        Ok(result.text)
    }

    /// 获取已处理的记录数
    pub fn get_processed_count(&self) -> u64 {
        self.processed_count.load(Ordering::Relaxed)
    }

    /// 设置空闲时间阈值
    pub fn set_idle_threshold(&self, secs: u64) {
        self.idle_threshold_secs.store(secs, Ordering::Relaxed);
    }

    /// 检查是否正在运行
    pub fn is_running(&self) -> bool {
        self.is_running.load(Ordering::Relaxed)
    }
}

/// 获取系统空闲时间（秒）
///
/// Windows: 使用 GetLastInputInfo API
/// 其他平台: 返回 0（总是处理）
#[cfg(windows)]
fn get_system_idle_time() -> u64 {
    use windows::Win32::UI::Input::KeyboardAndMouse::{GetLastInputInfo, LASTINPUTINFO};

    let mut last_input_info =
        LASTINPUTINFO { cbSize: std::mem::size_of::<LASTINPUTINFO>() as u32, dwTime: 0 };

    unsafe {
        if GetLastInputInfo(&mut last_input_info).as_bool() {
            let tick_count = windows::Win32::System::SystemInformation::GetTickCount();
            let idle_ms = tick_count.saturating_sub(last_input_info.dwTime);
            idle_ms as u64 / 1000
        } else {
            0
        }
    }
}

#[cfg(not(windows))]
fn get_system_idle_time() -> u64 {
    // 非 Windows 平台，假设总是空闲
    u64::MAX
}

/// 获取内存使用百分比
///
/// Windows: 使用 GlobalMemoryStatusEx API
/// 其他平台: 返回 0%（总是处理）
#[cfg(windows)]
fn get_memory_usage_percent() -> f64 {
    use windows::Win32::System::SystemInformation::{GlobalMemoryStatusEx, MEMORYSTATUSEX};

    let mut mem_status = MEMORYSTATUSEX {
        dwLength: std::mem::size_of::<MEMORYSTATUSEX>() as u32,
        ..Default::default()
    };

    unsafe {
        if GlobalMemoryStatusEx(&mut mem_status).is_ok() {
            mem_status.dwMemoryLoad as f64
        } else {
            0.0
        }
    }
}

#[cfg(not(windows))]
fn get_memory_usage_percent() -> f64 {
    0.0
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_background_ocr_cache_new() {
        let cache = BackgroundOcrCache::new();
        assert!(!cache.is_running());
        assert_eq!(cache.get_processed_count(), 0);
    }

    #[test]
    fn test_pause_resume() {
        let cache = BackgroundOcrCache::new();

        cache.pause();
        assert!(cache.is_paused.load(Ordering::Relaxed));

        cache.resume();
        assert!(!cache.is_paused.load(Ordering::Relaxed));
    }

    #[test]
    fn test_set_idle_threshold() {
        let cache = BackgroundOcrCache::new();
        cache.set_idle_threshold(10);
        assert_eq!(cache.idle_threshold_secs.load(Ordering::Relaxed), 10);
    }

    #[cfg(windows)]
    #[test]
    fn test_get_system_idle_time() {
        let idle_time = get_system_idle_time();
        // 应返回一个合理值（避免对测试机当前空闲时长做脆弱假设）
        assert!(idle_time < 10 * 365 * 24 * 3600); // 小于 10 年
    }

    #[cfg(windows)]
    #[test]
    fn test_get_memory_usage_percent() {
        let percent = get_memory_usage_percent();
        // 内存使用应该在 0-100% 之间
        assert!((0.0..=100.0).contains(&percent));
    }
}
