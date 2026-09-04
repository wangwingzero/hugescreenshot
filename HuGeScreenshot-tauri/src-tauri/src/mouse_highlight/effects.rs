//! 鼠标高亮效果定义
//!
//! 定义各种高亮效果的配置和参数

use serde::{Deserialize, Serialize};

/// 高亮效果类型
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
#[derive(Default)]
pub enum HighlightEffect {
    /// 无效果
    None,
    /// 聚光灯效果 - 高亮鼠标周围区域，其余区域变暗
    Spotlight,
    /// 光圈效果 - 在鼠标周围显示彩色光圈
    #[default]
    Circle,
    /// 放大镜效果 - 放大鼠标周围区域
    Magnifier,
}

/// 点击效果类型
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
#[derive(Default)]
pub enum ClickEffect {
    /// 无效果
    None,
    /// 涟漪效果 - 点击时显示扩散的涟漪
    #[default]
    Ripple,
    /// 闪烁效果 - 点击时短暂闪烁
    Flash,
    /// 圆环效果 - 点击时显示收缩的圆环
    Ring,
}

/// 高亮效果配置
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct HighlightConfig {
    /// 是否启用高亮效果
    pub enabled: bool,

    /// 高亮效果类型
    pub effect: HighlightEffect,

    /// 点击效果类型
    pub click_effect: ClickEffect,

    /// 高亮颜色 (CSS 颜色格式)
    pub color: String,

    /// 高亮半径 (像素)
    pub radius: u32,

    /// 高亮不透明度 (0.0 - 1.0)
    pub opacity: f32,

    /// 聚光灯效果的背景暗度 (0.0 - 1.0)
    pub spotlight_darkness: f32,

    /// 放大镜放大倍数
    pub magnifier_zoom: f32,

    /// 是否显示左键点击效果
    pub show_left_click: bool,

    /// 是否显示右键点击效果
    pub show_right_click: bool,

    /// 左键点击颜色
    pub left_click_color: String,

    /// 右键点击颜色
    pub right_click_color: String,

    /// 点击效果持续时间 (毫秒)
    pub click_duration: u32,

    /// 更新频率 (Hz，每秒更新次数)
    pub update_rate: u32,
}

impl Default for HighlightConfig {
    fn default() -> Self {
        Self {
            enabled: false,
            effect: HighlightEffect::Circle,
            click_effect: ClickEffect::Ripple,
            color: "#FFD700".to_string(), // 金色
            radius: 30,
            opacity: 0.6,
            spotlight_darkness: 0.5,
            magnifier_zoom: 2.0,
            show_left_click: true,
            show_right_click: true,
            left_click_color: "#00FF00".to_string(),  // 绿色
            right_click_color: "#FF6600".to_string(), // 橙色
            click_duration: 300,
            update_rate: 60,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_default_config() {
        let config = HighlightConfig::default();
        assert!(!config.enabled);
        assert_eq!(config.effect, HighlightEffect::Circle);
        assert_eq!(config.radius, 30);
        assert_eq!(config.update_rate, 60);
    }

    #[test]
    fn test_config_serialization() {
        let config = HighlightConfig::default();
        let json = serde_json::to_string(&config).unwrap();
        assert!(json.contains("\"enabled\":false"));
        assert!(json.contains("\"effect\":\"circle\""));

        let parsed: HighlightConfig = serde_json::from_str(&json).unwrap();
        assert_eq!(parsed.effect, config.effect);
    }
}
