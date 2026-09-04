//! 音频捕获模块
//!
//! 使用 Windows WASAPI API 捕获系统音频和麦克风输入。
//! 音频数据保存为临时 WAV 文件，后由 FFmpeg 与视频合并。
//!
//! # 实现说明
//!
//! 音频捕获将在阶段 6 完整实现。当前提供基础接口和占位实现，
//! 确保录屏引擎可以在没有音频的情况下正常工作。

use std::path::PathBuf;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use tracing::{info, warn};

use crate::error::HuGeResult;

/// 音频捕获配置
#[derive(Debug, Clone)]
pub struct AudioCaptureConfig {
    /// 是否录制系统音频
    pub capture_system_audio: bool,
    /// 是否录制麦克风
    pub capture_microphone: bool,
    /// 采样率
    pub sample_rate: u32,
    /// 声道数
    pub channels: u16,
    /// 临时音频文件路径
    pub output_path: PathBuf,
}

impl Default for AudioCaptureConfig {
    fn default() -> Self {
        Self {
            capture_system_audio: false,
            capture_microphone: false,
            sample_rate: 44100,
            channels: 2,
            output_path: PathBuf::from("temp_audio.wav"),
        }
    }
}

/// 音频捕获工作线程
///
/// 在独立线程中捕获系统音频和/或麦克风输入。
/// 当前为占位实现，完整 WASAPI 实现将在阶段 6 添加。
pub struct AudioCaptureWorker {
    config: AudioCaptureConfig,
    should_stop: Arc<AtomicBool>,
    #[allow(dead_code)]
    is_paused: Arc<AtomicBool>,
}

impl AudioCaptureWorker {
    /// 创建音频捕获工作线程
    pub fn new(
        config: AudioCaptureConfig,
        should_stop: Arc<AtomicBool>,
        is_paused: Arc<AtomicBool>,
    ) -> Self {
        Self { config, should_stop, is_paused }
    }

    /// 检查音频捕获是否可用
    pub fn is_available() -> bool {
        // TODO: 阶段 6 - 检查 WASAPI 设备可用性
        false
    }

    /// 运行音频捕获循环
    ///
    /// 当前为占位实现。完整 WASAPI 实现将在阶段 6 添加。
    pub fn run(&self) -> HuGeResult<()> {
        if !self.config.capture_system_audio && !self.config.capture_microphone {
            info!("音频捕获未启用，跳过");
            return Ok(());
        }

        warn!("音频捕获功能尚未实现（将在阶段 6 添加 WASAPI 支持）");

        // 占位：等待停止信号
        while !self.should_stop.load(Ordering::Relaxed) {
            std::thread::sleep(std::time::Duration::from_millis(100));
        }

        Ok(())
    }

    /// 获取输出文件路径（如果有音频）
    pub fn output_path(&self) -> Option<&PathBuf> {
        if self.config.capture_system_audio || self.config.capture_microphone {
            Some(&self.config.output_path)
        } else {
            None
        }
    }
}
