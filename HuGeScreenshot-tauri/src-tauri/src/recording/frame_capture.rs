//! 连续帧捕获模块
//!
//! 复用 DXGI Desktop Duplication API 进行连续屏幕帧捕获。
//! 在独立线程中运行，通过 channel 将帧数据发送给编码器。

use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::Arc;
use std::time::{Duration, Instant};
use tracing::{error, info, warn};

use crate::error::{HuGeError, HuGeResult};

/// 捕获的帧数据
#[derive(Debug)]
pub struct CapturedFrame {
    /// BGRA 像素数据（原始格式，不做颜色转换以提升性能）
    pub data: Vec<u8>,
    /// 宽度（物理像素）
    pub width: u32,
    /// 高度（物理像素）
    pub height: u32,
    /// 帧时间戳（相对于录制开始）
    pub timestamp: Duration,
    /// 帧序号
    pub frame_index: u64,
}

/// 帧捕获配置
#[derive(Debug, Clone)]
pub struct FrameCaptureConfig {
    /// 目标帧率
    pub fps: u32,
    /// 录制区域（物理像素坐标），None 表示全屏
    pub region: Option<CaptureRegion>,
    /// 显示器索引
    pub monitor_index: u32,
    /// DXGI 捕获超时（毫秒）
    pub capture_timeout_ms: u32,
}

/// 录制区域（物理像素坐标）
#[derive(Debug, Clone, Copy)]
pub struct CaptureRegion {
    pub x: i32,
    pub y: i32,
    pub width: u32,
    pub height: u32,
}

impl Default for FrameCaptureConfig {
    fn default() -> Self {
        Self { fps: 30, region: None, monitor_index: 0, capture_timeout_ms: 50 }
    }
}

/// 帧捕获工作线程
///
/// 在独立线程中持续捕获屏幕帧，通过 crossbeam channel 发送给编码器。
pub struct FrameCaptureWorker {
    config: FrameCaptureConfig,
    should_stop: Arc<AtomicBool>,
    is_paused: Arc<AtomicBool>,
    /// 丢帧计数器（共享，可从引擎读取）
    dropped_frames: Arc<AtomicU64>,
}

impl FrameCaptureWorker {
    /// 创建帧捕获工作线程
    pub fn new(
        config: FrameCaptureConfig,
        should_stop: Arc<AtomicBool>,
        is_paused: Arc<AtomicBool>,
    ) -> Self {
        Self { config, should_stop, is_paused, dropped_frames: Arc::new(AtomicU64::new(0)) }
    }

    /// 创建帧捕获工作线程（使用外部丢帧计数器）
    pub fn with_dropped_counter(
        config: FrameCaptureConfig,
        should_stop: Arc<AtomicBool>,
        is_paused: Arc<AtomicBool>,
        dropped_frames: Arc<AtomicU64>,
    ) -> Self {
        Self { config, should_stop, is_paused, dropped_frames }
    }

    /// 获取丢帧计数器（可共享）
    pub fn dropped_frames(&self) -> Arc<AtomicU64> {
        self.dropped_frames.clone()
    }

    /// 运行帧捕获循环（在独立线程中调用）
    ///
    /// 使用 `capture_region_bgra` 高性能方法：
    /// - 直接输出 BGRA（不做颜色转换，FFmpeg 直接接受）
    /// - 只读取指定区域像素（不读全屏再裁剪）
    /// - 复用缓冲区（避免每帧分配内存）
    pub fn run(&self, sender: std::sync::mpsc::SyncSender<CapturedFrame>) -> HuGeResult<()> {
        info!(
            "帧捕获线程启动: {}fps, 显示器 {}, 区域 {:?}",
            self.config.fps, self.config.monitor_index, self.config.region
        );

        // 初始化 DXGI 捕获引擎
        let mut engine = self.create_capture_engine()?;

        let frame_interval = Duration::from_secs_f64(1.0 / self.config.fps as f64);
        let start_time = Instant::now();
        let mut frame_index: u64 = 0;
        let mut consecutive_errors: u32 = 0;
        let max_consecutive_errors: u32 = 30;

        // 预分配缓冲区（复用，避免每帧分配）
        let mut bgra_buffer: Vec<u8> = Vec::new();

        // 转换区域参数
        let dxgi_region =
            self.config.region.map(|r| (r.x.max(0) as u32, r.y.max(0) as u32, r.width, r.height));

        while !self.should_stop.load(Ordering::Relaxed) {
            let frame_start = Instant::now();

            // 暂停状态下跳过捕获
            if self.is_paused.load(Ordering::Relaxed) {
                std::thread::sleep(Duration::from_millis(50));
                continue;
            }

            // 使用高性能 BGRA 区域捕获
            match engine.capture_region_bgra(dxgi_region, &mut bgra_buffer) {
                Ok((width, height, _capture_us)) => {
                    consecutive_errors = 0;
                    let timestamp = start_time.elapsed();

                    let captured_frame = CapturedFrame {
                        // 零拷贝：move buffer 到帧中而不是 clone
                        // 下次循环 capture_region_bgra 会重新分配 bgra_buffer
                        data: std::mem::take(&mut bgra_buffer),
                        width,
                        height,
                        timestamp,
                        frame_index,
                    };

                    // 发送帧给编码器
                    match sender.try_send(captured_frame) {
                        Ok(()) => {}
                        Err(std::sync::mpsc::TrySendError::Full(_)) => {
                            self.dropped_frames.fetch_add(1, Ordering::Relaxed);
                            warn!("编码器队列满，丢弃帧 {} (编码速度不足)", frame_index);
                        }
                        Err(std::sync::mpsc::TrySendError::Disconnected(_)) => {
                            error!("编码器通道已断开（编码器可能已崩溃），停止帧捕获");
                            break;
                        }
                    }

                    frame_index += 1;
                }
                Err(e) => {
                    consecutive_errors += 1;
                    let err_msg = e.to_string();

                    if err_msg.contains("ACCESS_LOST") || err_msg.contains("DEVICE_REMOVED") {
                        warn!("DXGI 访问丢失，尝试重新初始化 (连续错误: {})", consecutive_errors);
                        if let Err(reinit_err) = engine.reinitialize() {
                            error!("DXGI 重新初始化失败: {}", reinit_err);
                            if consecutive_errors >= max_consecutive_errors {
                                return Err(HuGeError::CaptureError(format!(
                                    "连续捕获失败超过阈值: {}",
                                    reinit_err
                                )));
                            }
                        } else {
                            consecutive_errors = 0;
                        }
                    } else if err_msg.contains("超时") || err_msg.contains("TIMEOUT") {
                        // 屏幕无变化，跳过
                    } else {
                        warn!("帧捕获错误 (连续 {}): {}", consecutive_errors, err_msg);
                    }
                }
            }

            // 帧率控制（精确计时：sleep 粗调 + spin-wait 精调）
            // Windows 默认 thread::sleep 精度约 15ms，spin-wait 最后 2ms 可保证帧间隔精确
            let elapsed = frame_start.elapsed();
            if elapsed < frame_interval {
                let remaining = frame_interval - elapsed;
                if remaining > Duration::from_millis(2) {
                    std::thread::sleep(remaining - Duration::from_millis(2));
                }
                // spin-wait 精确等待最后几毫秒
                while frame_start.elapsed() < frame_interval {
                    std::hint::spin_loop();
                }
            }
        }

        let dropped = self.dropped_frames.load(Ordering::Relaxed);
        info!("帧捕获线程退出，共捕获 {} 帧，丢弃 {} 帧", frame_index, dropped);
        Ok(())
    }

    /// 创建 DXGI 捕获引擎
    #[cfg(windows)]
    fn create_capture_engine(&self) -> HuGeResult<crate::screenshot::capture::DxgiCaptureEngine> {
        use crate::screenshot::capture::{get_all_screens, DxgiCaptureConfig, DxgiCaptureEngine};

        let config = DxgiCaptureConfig {
            timeout_ms: self.config.capture_timeout_ms,
            include_cursor: true,
            ..Default::default()
        };

        // 获取屏幕信息用于 DXGI 坐标匹配
        let screens = get_all_screens()?;
        let screen = screens.get(self.config.monitor_index as usize).ok_or_else(|| {
            crate::error::HuGeError::CaptureError(format!(
                "显示器索引 {} 超出范围",
                self.config.monitor_index
            ))
        })?;
        let di = &screen.display_info;

        DxgiCaptureEngine::new(di.id, di.x, di.y, di.width, di.height, config)
    }
}
