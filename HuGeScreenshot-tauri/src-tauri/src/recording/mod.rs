//! 录屏引擎模块
//!
//! 本模块提供原生 Rust 录屏功能，使用 DXGI Desktop Duplication API 捕获屏幕帧，
//! 通过 FFmpeg 子进程编码为 H.264/MP4 视频。
//!
//! # 子模块
//!
//! - `engine`: 录屏引擎主逻辑（生命周期管理、状态机）
//! - `frame_capture`: 连续帧捕获（复用 DXGI 引擎）
//! - `encoder`: FFmpeg 编码器（子进程管道）
//! - `audio`: 音频捕获（WASAPI）

pub mod audio;
pub mod encoder;
pub mod engine;
pub mod frame_capture;

// 重新导出常用类型
pub use engine::{
    RecordingConfig as EngineConfig, RecordingEngine, RecordingState, RecordingStats,
};
