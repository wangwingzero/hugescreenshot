//! 全局鼠标追踪器
//!
//! 使用 rdev 库监听全局鼠标事件，并通过 Tauri 事件系统
//! 将鼠标位置和点击事件发送到前端。

use std::sync::atomic::{AtomicBool, AtomicI32, Ordering};
use std::sync::Arc;
use std::thread::{self, JoinHandle};
use std::time::{Duration, Instant};

use rdev::{listen, Button, Event, EventType};
use serde::{Deserialize, Serialize};
use tauri::{AppHandle, Emitter, Runtime};
use tracing::{debug, error, info, warn};

use super::HighlightConfig;

/// 鼠标位置
#[derive(Debug, Clone, Copy, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct MousePosition {
    pub x: i32,
    pub y: i32,
}

/// 鼠标事件类型
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub enum MouseEventType {
    /// 鼠标移动
    Move,
    /// 左键按下
    LeftDown,
    /// 左键释放
    LeftUp,
    /// 右键按下
    RightDown,
    /// 右键释放
    RightUp,
    /// 中键按下
    MiddleDown,
    /// 中键释放
    MiddleUp,
}

/// 鼠标事件
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct MouseEvent {
    /// 事件类型
    pub event_type: MouseEventType,
    /// 鼠标位置
    pub position: MousePosition,
    /// 时间戳 (毫秒)
    pub timestamp: u64,
}

/// 全局鼠标追踪器
pub struct MouseTracker {
    /// 是否正在运行
    is_running: Arc<AtomicBool>,
    /// 当前鼠标 X 坐标
    current_x: Arc<AtomicI32>,
    /// 当前鼠标 Y 坐标
    current_y: Arc<AtomicI32>,
    /// 监听线程句柄
    listener_handle: Option<JoinHandle<()>>,
    /// 配置
    config: HighlightConfig,
}

impl MouseTracker {
    /// 创建新的鼠标追踪器
    pub fn new(config: HighlightConfig) -> Self {
        Self {
            is_running: Arc::new(AtomicBool::new(false)),
            current_x: Arc::new(AtomicI32::new(0)),
            current_y: Arc::new(AtomicI32::new(0)),
            listener_handle: None,
            config,
        }
    }

    /// 启动鼠标追踪
    pub fn start<R: Runtime>(&mut self, app_handle: AppHandle<R>) -> Result<(), String> {
        if self.is_running.load(Ordering::SeqCst) {
            warn!("鼠标追踪器已在运行中");
            return Ok(());
        }

        info!("启动鼠标追踪器");
        self.is_running.store(true, Ordering::SeqCst);

        let is_running = Arc::clone(&self.is_running);
        let current_x = Arc::clone(&self.current_x);
        let current_y = Arc::clone(&self.current_y);
        let update_interval = Duration::from_millis(1000 / self.config.update_rate as u64);
        let show_left_click = self.config.show_left_click;
        let show_right_click = self.config.show_right_click;

        // 启动事件发送线程
        let app_handle_clone = app_handle.clone();
        let is_running_clone = Arc::clone(&is_running);
        let current_x_clone = Arc::clone(&current_x);
        let current_y_clone = Arc::clone(&current_y);

        thread::spawn(move || {
            let mut last_emit = Instant::now();
            let mut last_x = 0i32;
            let mut last_y = 0i32;

            while is_running_clone.load(Ordering::SeqCst) {
                let now = Instant::now();
                if now.duration_since(last_emit) >= update_interval {
                    let x = current_x_clone.load(Ordering::SeqCst);
                    let y = current_y_clone.load(Ordering::SeqCst);

                    // 只有位置变化时才发送
                    if x != last_x || y != last_y {
                        let event = MouseEvent {
                            event_type: MouseEventType::Move,
                            position: MousePosition { x, y },
                            timestamp: now.elapsed().as_millis() as u64,
                        };

                        if let Err(e) = app_handle_clone.emit("mouse-move", &event) {
                            debug!("发送鼠标移动事件失败: {}", e);
                        }

                        last_x = x;
                        last_y = y;
                    }

                    last_emit = now;
                }

                thread::sleep(Duration::from_millis(1));
            }
        });

        // 启动 rdev 监听线程
        let app_handle_for_listener = app_handle;
        let handle = thread::spawn(move || {
            let callback = move |event: Event| {
                if !is_running.load(Ordering::SeqCst) {
                    return;
                }

                match event.event_type {
                    EventType::MouseMove { x, y } => {
                        current_x.store(x as i32, Ordering::SeqCst);
                        current_y.store(y as i32, Ordering::SeqCst);
                    }
                    EventType::ButtonPress(button) => {
                        let x = current_x.load(Ordering::SeqCst);
                        let y = current_y.load(Ordering::SeqCst);

                        let event_type = match button {
                            Button::Left if show_left_click => Some(MouseEventType::LeftDown),
                            Button::Right if show_right_click => Some(MouseEventType::RightDown),
                            Button::Middle => Some(MouseEventType::MiddleDown),
                            _ => None,
                        };

                        if let Some(event_type) = event_type {
                            let mouse_event = MouseEvent {
                                event_type,
                                position: MousePosition { x, y },
                                timestamp: std::time::SystemTime::now()
                                    .duration_since(std::time::UNIX_EPOCH)
                                    .unwrap_or_default()
                                    .as_millis() as u64,
                            };

                            if let Err(e) =
                                app_handle_for_listener.emit("mouse-click", &mouse_event)
                            {
                                debug!("发送鼠标点击事件失败: {}", e);
                            }
                        }
                    }
                    EventType::ButtonRelease(button) => {
                        let x = current_x.load(Ordering::SeqCst);
                        let y = current_y.load(Ordering::SeqCst);

                        let event_type = match button {
                            Button::Left if show_left_click => Some(MouseEventType::LeftUp),
                            Button::Right if show_right_click => Some(MouseEventType::RightUp),
                            Button::Middle => Some(MouseEventType::MiddleUp),
                            _ => None,
                        };

                        if let Some(event_type) = event_type {
                            let mouse_event = MouseEvent {
                                event_type,
                                position: MousePosition { x, y },
                                timestamp: std::time::SystemTime::now()
                                    .duration_since(std::time::UNIX_EPOCH)
                                    .unwrap_or_default()
                                    .as_millis() as u64,
                            };

                            if let Err(e) =
                                app_handle_for_listener.emit("mouse-click", &mouse_event)
                            {
                                debug!("发送鼠标释放事件失败: {}", e);
                            }
                        }
                    }
                    _ => {}
                }
            };

            if let Err(e) = listen(callback) {
                error!("鼠标事件监听出错: {:?}", e);
            }
        });

        self.listener_handle = Some(handle);
        info!("鼠标追踪器已启动");
        Ok(())
    }

    /// 停止鼠标追踪
    pub fn stop(&mut self) {
        if !self.is_running.load(Ordering::SeqCst) {
            return;
        }

        info!("停止鼠标追踪器");
        self.is_running.store(false, Ordering::SeqCst);

        // 注意：rdev::listen 是阻塞的，无法优雅地停止
        // 这里只是标记停止，实际线程可能会继续运行直到下一个事件
        if let Some(handle) = self.listener_handle.take() {
            // 不等待线程结束，因为 rdev::listen 是阻塞的
            drop(handle);
        }

        info!("鼠标追踪器已停止");
    }

    /// 检查是否正在运行
    pub fn is_running(&self) -> bool {
        self.is_running.load(Ordering::SeqCst)
    }

    /// 获取当前鼠标位置
    pub fn get_position(&self) -> MousePosition {
        MousePosition {
            x: self.current_x.load(Ordering::SeqCst),
            y: self.current_y.load(Ordering::SeqCst),
        }
    }

    /// 更新配置
    pub fn update_config(&mut self, config: HighlightConfig) {
        self.config = config;
    }

    /// 获取当前配置
    pub fn get_config(&self) -> &HighlightConfig {
        &self.config
    }
}

impl Drop for MouseTracker {
    fn drop(&mut self) {
        self.stop();
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_mouse_position() {
        let pos = MousePosition { x: 100, y: 200 };
        assert_eq!(pos.x, 100);
        assert_eq!(pos.y, 200);
    }

    #[test]
    fn test_mouse_event_serialization() {
        let event = MouseEvent {
            event_type: MouseEventType::LeftDown,
            position: MousePosition { x: 100, y: 200 },
            timestamp: 12345,
        };

        let json = serde_json::to_string(&event).unwrap();
        assert!(json.contains("\"eventType\":\"leftDown\""));
        assert!(json.contains("\"x\":100"));
    }

    #[test]
    fn test_tracker_creation() {
        let config = HighlightConfig::default();
        let tracker = MouseTracker::new(config);
        assert!(!tracker.is_running());
    }
}
