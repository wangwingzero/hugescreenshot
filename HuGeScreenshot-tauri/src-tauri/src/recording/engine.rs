//! 录屏引擎
//!
//! 管理录制的完整生命周期：初始化 → 录制 → 暂停/恢复 → 停止 → 编码完成。
//! 协调帧捕获线程和 FFmpeg 编码器之间的数据流。

use std::path::PathBuf;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use std::time::{Duration, Instant};
use tracing::{debug, error, info, warn};

use super::encoder::{EncoderConfig, FfmpegEncoder};
use super::frame_capture::{CaptureRegion, CapturedFrame, FrameCaptureConfig, FrameCaptureWorker};
use crate::error::{HuGeError, HuGeResult};

/// 录制状态
#[derive(Debug, Clone, Copy, PartialEq, Eq, serde::Serialize, serde::Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum RecordingState {
    /// 空闲（未在录制）
    Idle,
    /// 倒计时中
    Countdown,
    /// 录制中
    Recording,
    /// 已暂停
    Paused,
    /// 正在编码（停止后 FFmpeg 完成编码）
    Encoding,
    /// 已完成
    Finished,
    /// 出错
    Error,
}

impl std::fmt::Display for RecordingState {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            RecordingState::Idle => write!(f, "idle"),
            RecordingState::Countdown => write!(f, "countdown"),
            RecordingState::Recording => write!(f, "recording"),
            RecordingState::Paused => write!(f, "paused"),
            RecordingState::Encoding => write!(f, "encoding"),
            RecordingState::Finished => write!(f, "finished"),
            RecordingState::Error => write!(f, "error"),
        }
    }
}

/// 录屏配置
#[derive(Debug, Clone)]
pub struct RecordingConfig {
    /// 录制区域（物理像素坐标），None 表示全屏
    pub region: Option<CaptureRegion>,
    /// 帧率
    pub fps: u32,
    /// 编码质量 (CRF 值)
    pub crf: u32,
    /// 编码预设
    pub preset: String,
    /// 输出文件路径
    pub output_path: PathBuf,
    /// 显示器索引
    pub monitor_index: u32,
    /// 是否录制系统音频
    pub system_audio: bool,
    /// 是否录制麦克风
    pub mic_audio: bool,
}

impl Default for RecordingConfig {
    fn default() -> Self {
        Self {
            region: None,
            fps: 30,
            crf: 23,
            preset: "fast".to_string(),
            output_path: Self::default_output_path(),
            monitor_index: 0,
            system_audio: false,
            mic_audio: false,
        }
    }
}

impl RecordingConfig {
    /// 生成默认输出路径
    pub fn default_output_path() -> PathBuf {
        let videos_dir = dirs::video_dir()
            .unwrap_or_else(|| dirs::home_dir().unwrap_or_else(|| PathBuf::from(".")));

        let recording_dir = videos_dir.join("HuGeScreenshot").join("Recordings");
        let _ = std::fs::create_dir_all(&recording_dir);

        let now = chrono::Local::now();
        let filename = format!("recording_{}.mp4", now.format("%Y%m%d_%H%M%S"));
        recording_dir.join(filename)
    }

    /// 根据质量等级获取 CRF 值
    pub fn crf_from_quality(quality: &str) -> u32 {
        match quality {
            "low" => 28,
            "medium" => 23,
            "high" => 18,
            _ => 23,
        }
    }
}

/// 录制统计信息
#[derive(Debug, Clone, serde::Serialize)]
pub struct RecordingStats {
    /// 当前状态
    pub state: RecordingState,
    /// 已录制时长（秒，不含暂停时间）
    pub elapsed_time: f64,
    /// 已编码帧数
    pub frame_count: u64,
    /// 丢弃帧数（编码速度不足时丢弃的帧）
    pub dropped_frames: u64,
    /// 输出文件路径
    pub output_path: String,
    /// 文件大小（字节）
    pub file_size: i64,
}

/// 录屏引擎
///
/// 管理录制的完整生命周期，协调帧捕获和编码。
pub struct RecordingEngine {
    /// 当前状态
    state: RecordingState,
    /// 录制配置
    config: Option<RecordingConfig>,
    /// 录制开始时间
    start_time: Option<Instant>,
    /// 累计暂停时长
    pause_duration: Duration,
    /// 上次暂停开始时间
    pause_start: Option<Instant>,
    /// 停止信号
    should_stop: Arc<AtomicBool>,
    /// 暂停信号
    is_paused: Arc<AtomicBool>,
    /// 帧捕获线程句柄
    capture_thread: Option<std::thread::JoinHandle<HuGeResult<()>>>,
    /// 编码线程句柄
    encode_thread: Option<std::thread::JoinHandle<HuGeResult<u64>>>,
    /// 帧计数器（共享）
    frame_count: Option<Arc<std::sync::atomic::AtomicU64>>,
    /// 丢帧计数器（共享）
    dropped_frames: Option<Arc<std::sync::atomic::AtomicU64>>,
    /// 输出文件路径
    output_path: Option<PathBuf>,
    /// 错误信息
    last_error: Option<String>,
}

impl RecordingEngine {
    /// 创建录屏引擎
    pub fn new() -> Self {
        Self {
            state: RecordingState::Idle,
            config: None,
            start_time: None,
            pause_duration: Duration::ZERO,
            pause_start: None,
            should_stop: Arc::new(AtomicBool::new(false)),
            is_paused: Arc::new(AtomicBool::new(false)),
            capture_thread: None,
            encode_thread: None,
            frame_count: None,
            dropped_frames: None,
            output_path: None,
            last_error: None,
        }
    }

    /// 获取当前状态
    pub fn state(&self) -> RecordingState {
        self.state
    }

    /// 获取录制统计信息
    pub fn stats(&self) -> RecordingStats {
        let elapsed_time = self.elapsed_time().as_secs_f64();
        let frame_count = self.frame_count.as_ref().map(|c| c.load(Ordering::Relaxed)).unwrap_or(0);
        let dropped_frames =
            self.dropped_frames.as_ref().map(|c| c.load(Ordering::Relaxed)).unwrap_or(0);
        let output_path =
            self.output_path.as_ref().map(|p| p.to_string_lossy().to_string()).unwrap_or_default();
        let file_size = self
            .output_path
            .as_ref()
            .and_then(|p| std::fs::metadata(p).ok())
            .map(|m| m.len() as i64)
            .unwrap_or(0);

        RecordingStats {
            state: self.state,
            elapsed_time,
            frame_count,
            dropped_frames,
            output_path,
            file_size,
        }
    }

    /// 计算已录制时长（不含暂停时间）
    fn elapsed_time(&self) -> Duration {
        match self.start_time {
            Some(start) => {
                let total = start.elapsed();
                let pause = self.pause_duration
                    + match self.pause_start {
                        Some(ps) => ps.elapsed(),
                        None => Duration::ZERO,
                    };
                total.saturating_sub(pause)
            }
            None => Duration::ZERO,
        }
    }

    /// 开始录制
    pub fn start(&mut self, config: RecordingConfig) -> HuGeResult<()> {
        if self.state != RecordingState::Idle {
            return Err(HuGeError::CaptureError(format!(
                "无法开始录制：当前状态为 {}",
                self.state
            )));
        }

        info!("开始录屏: {:?}", config.output_path);
        info!(
            "录制参数: {}fps, CRF={}, preset={}, 区域={:?}",
            config.fps, config.crf, config.preset, config.region
        );

        // 重置状态
        self.should_stop = Arc::new(AtomicBool::new(false));
        self.is_paused = Arc::new(AtomicBool::new(false));
        self.pause_duration = Duration::ZERO;
        self.pause_start = None;
        self.last_error = None;

        // 设置 Windows 计时器精度为 1ms（提高 thread::sleep 精度，对 60fps 录制关键）
        #[cfg(windows)]
        unsafe {
            windows::Win32::Media::timeBeginPeriod(1);
        }
        info!("已设置 Windows 计时器精度为 1ms");

        let output_path = config.output_path.clone();
        self.output_path = Some(output_path.clone());

        // 需要先做一次试捕获来获取实际的帧尺寸
        let (actual_width, actual_height) = self.probe_frame_size(&config)?;
        info!("实际捕获尺寸: {}x{}", actual_width, actual_height);

        // 创建帧通道（有界队列，防止内存爆炸）
        // 使用 16 帧缓冲，为软件编码提供足够余量应对 CPU 瞄时负载
        let (frame_tx, frame_rx) = std::sync::mpsc::sync_channel::<CapturedFrame>(16);

        // 配置并启动 FFmpeg 编码器
        let encoder_config = EncoderConfig {
            output_path: output_path.clone(),
            width: actual_width,
            height: actual_height,
            fps: config.fps,
            crf: config.crf,
            preset: config.preset.clone(),
            input_pixel_format: "bgra".to_string(),
            audio_input: None, // FUTURE: 阶段 6 添加音频支持
        };

        let mut encoder = FfmpegEncoder::new(encoder_config);
        let frame_count_ref = encoder.frame_count();
        self.frame_count = Some(frame_count_ref);

        encoder.start()?;

        // 启动编码线程（从 channel 读取帧并写入 FFmpeg）
        let should_stop_enc = self.should_stop.clone();
        let encode_thread = std::thread::Builder::new()
            .name("recording-encoder".to_string())
            .spawn(move || {
                info!("编码线程启动");
                let mut total_frames: u64 = 0;

                loop {
                    match frame_rx.recv_timeout(Duration::from_millis(500)) {
                        Ok(frame) => {
                            if let Err(e) = encoder.write_frame(&frame) {
                                error!("编码帧失败: {}", e);
                                break;
                            }
                            total_frames += 1;
                        }
                        Err(std::sync::mpsc::RecvTimeoutError::Timeout) => {
                            if should_stop_enc.load(Ordering::Relaxed) {
                                debug!("编码线程收到停止信号");
                                break;
                            }
                        }
                        Err(std::sync::mpsc::RecvTimeoutError::Disconnected) => {
                            debug!("帧通道已断开");
                            break;
                        }
                    }
                }

                // 停止编码器，等待 FFmpeg 完成
                info!("编码线程正在完成，共处理 {} 帧", total_frames);
                let final_count = encoder.stop()?;
                info!("编码线程退出，最终帧数: {}", final_count);
                Ok(final_count)
            })
            .map_err(|e| HuGeError::CaptureError(format!("创建编码线程失败: {}", e)))?;

        // 配置帧捕获
        let capture_config = FrameCaptureConfig {
            fps: config.fps,
            region: config.region,
            monitor_index: config.monitor_index,
            capture_timeout_ms: 50,
        };

        // 创建丢帧计数器（共享给帧捕获线程）
        let dropped_frames_counter = Arc::new(std::sync::atomic::AtomicU64::new(0));
        self.dropped_frames = Some(dropped_frames_counter.clone());

        // 启动帧捕获线程
        let should_stop_cap = self.should_stop.clone();
        let is_paused_cap = self.is_paused.clone();
        let capture_thread = std::thread::Builder::new()
            .name("recording-capture".to_string())
            .spawn(move || {
                let worker = FrameCaptureWorker::with_dropped_counter(
                    capture_config,
                    should_stop_cap,
                    is_paused_cap,
                    dropped_frames_counter,
                );
                worker.run(frame_tx)
            })
            .map_err(|e| HuGeError::CaptureError(format!("创建帧捕获线程失败: {}", e)))?;

        self.capture_thread = Some(capture_thread);
        self.encode_thread = Some(encode_thread);
        self.start_time = Some(Instant::now());
        self.config = Some(config);
        self.state = RecordingState::Recording;

        info!("录屏已启动");
        Ok(())
    }

    /// 试捕获获取实际帧尺寸
    fn probe_frame_size(&self, config: &RecordingConfig) -> HuGeResult<(u32, u32)> {
        #[cfg(windows)]
        {
            use crate::screenshot::capture::{
                get_all_screens, DxgiCaptureConfig, DxgiCaptureEngine,
            };

            let dxgi_config =
                DxgiCaptureConfig { timeout_ms: 1000, include_cursor: true, ..Default::default() };

            // 获取屏幕信息用于 DXGI 坐标匹配
            let screens = get_all_screens()?;
            let screen = screens.get(config.monitor_index as usize).ok_or_else(|| {
                crate::error::HuGeError::CaptureError(format!(
                    "显示器索引 {} 超出范围",
                    config.monitor_index
                ))
            })?;
            let di = &screen.display_info;

            let mut engine =
                DxgiCaptureEngine::new(di.id, di.x, di.y, di.width, di.height, dxgi_config)?;

            // 使用高性能 BGRA 区域捕获进行试捕获
            let dxgi_region =
                config.region.map(|r| (r.x.max(0) as u32, r.y.max(0) as u32, r.width, r.height));

            let mut buffer = Vec::new();
            let (width, height, _) =
                engine.capture_region_bgra(dxgi_region, &mut buffer).or_else(|_| {
                    // 第一次可能超时（屏幕无变化），重试
                    std::thread::sleep(std::time::Duration::from_millis(50));
                    engine.capture_region_bgra(dxgi_region, &mut buffer)
                })?;

            // 已经是偶数（capture_region_bgra 内部保证）
            Ok((width, height))
        }

        #[cfg(not(windows))]
        {
            Err(HuGeError::CaptureError("录屏功能仅支持 Windows".to_string()))
        }
    }

    /// 暂停录制
    pub fn pause(&mut self) -> HuGeResult<()> {
        if self.state != RecordingState::Recording {
            return Err(HuGeError::CaptureError(format!("无法暂停：当前状态为 {}", self.state)));
        }

        info!("暂停录屏");
        self.is_paused.store(true, Ordering::SeqCst);
        self.pause_start = Some(Instant::now());
        self.state = RecordingState::Paused;
        Ok(())
    }

    /// 恢复录制
    pub fn resume(&mut self) -> HuGeResult<()> {
        if self.state != RecordingState::Paused {
            return Err(HuGeError::CaptureError(format!("无法恢复：当前状态为 {}", self.state)));
        }

        info!("恢复录屏");
        if let Some(pause_start) = self.pause_start.take() {
            self.pause_duration += pause_start.elapsed();
        }
        self.is_paused.store(false, Ordering::SeqCst);
        self.state = RecordingState::Recording;
        Ok(())
    }

    /// 停止录制
    ///
    /// 发送停止信号，等待捕获和编码线程完成。
    pub fn stop(&mut self) -> HuGeResult<RecordingStats> {
        if self.state != RecordingState::Recording && self.state != RecordingState::Paused {
            return Err(HuGeError::CaptureError(format!("无法停止：当前状态为 {}", self.state)));
        }

        info!("停止录屏");
        self.state = RecordingState::Encoding;

        // 如果处于暂停状态，先累计暂停时长
        if let Some(pause_start) = self.pause_start.take() {
            self.pause_duration += pause_start.elapsed();
        }

        // 发送停止信号
        self.should_stop.store(true, Ordering::SeqCst);
        self.is_paused.store(false, Ordering::SeqCst);

        // 等待帧捕获线程结束
        if let Some(thread) = self.capture_thread.take() {
            match thread.join() {
                Ok(Ok(())) => info!("帧捕获线程正常退出"),
                Ok(Err(e)) => warn!("帧捕获线程出错: {}", e),
                Err(_) => error!("帧捕获线程崩溃"),
            }
        }

        // 等待编码线程结束（编码器会刷新并完成）
        if let Some(thread) = self.encode_thread.take() {
            match thread.join() {
                Ok(Ok(count)) => info!("编码线程正常退出，最终帧数: {}", count),
                Ok(Err(e)) => {
                    warn!("编码线程出错: {}", e);
                    self.last_error = Some(e.to_string());
                }
                Err(_) => error!("编码线程崩溃"),
            }
        }

        // 先设为 Finished 以便 stats() 返回正确状态
        self.state = RecordingState::Finished;
        let stats = self.stats();
        info!(
            "录屏完成: {:.1}s, {} 帧 (丢弃 {} 帧), 文件: {}",
            stats.elapsed_time, stats.frame_count, stats.dropped_frames, stats.output_path
        );

        // 重置为 Idle，允许下次录制
        self.state = RecordingState::Idle;

        // 恢复 Windows 计时器精度
        #[cfg(windows)]
        unsafe {
            windows::Win32::Media::timeEndPeriod(1);
        }
        info!("已恢复 Windows 计时器精度");

        Ok(stats)
    }

    /// 重置引擎到空闲状态
    pub fn reset(&mut self) {
        // 如果还在录制，先强制停止
        if self.state == RecordingState::Recording || self.state == RecordingState::Paused {
            let _ = self.stop();
        }

        self.state = RecordingState::Idle;
        self.config = None;
        self.start_time = None;
        self.pause_duration = Duration::ZERO;
        self.pause_start = None;
        self.frame_count = None;
        self.dropped_frames = None;
        self.output_path = None;
        self.last_error = None;
    }
}

impl Default for RecordingEngine {
    fn default() -> Self {
        Self::new()
    }
}

impl Drop for RecordingEngine {
    fn drop(&mut self) {
        // 确保录制线程在引擎销毁时被正确停止，防止线程泄漏
        if self.state == RecordingState::Recording || self.state == RecordingState::Paused {
            warn!("RecordingEngine 在录制状态中被销毁，强制停止录制");
            self.should_stop.store(true, Ordering::SeqCst);
            self.is_paused.store(false, Ordering::SeqCst);

            if let Some(thread) = self.capture_thread.take() {
                let _ = thread.join();
            }
            if let Some(thread) = self.encode_thread.take() {
                let _ = thread.join();
            }
        }
    }
}
