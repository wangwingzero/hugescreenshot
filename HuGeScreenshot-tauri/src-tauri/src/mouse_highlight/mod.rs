//! 鼠标高亮效果模块
//!
//! 提供全局鼠标追踪和高亮效果功能，支持：
//! - 聚光灯效果 (Spotlight)
//! - 放大镜效果 (Magnifier)
//! - 点击涟漪效果 (Click Ripple)
//! - 光圈效果 (Circle)

mod effects;
mod tracker;

pub use effects::{ClickEffect, HighlightConfig, HighlightEffect};
pub use tracker::{MouseEvent, MousePosition, MouseTracker};
