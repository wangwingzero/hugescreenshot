//! 统一错误类型定义
//!
//! 本模块定义了 HuGeError 统一错误类型，用于整个应用的错误处理。
//! 所有 Tauri 命令返回的错误都应该使用此类型。

use serde::Serialize;
use thiserror::Error;

/// 虎哥截图统一错误类型
///
/// 所有模块的错误都应该转换为此类型，以便统一处理和序列化到前端。
#[derive(Debug, Error)]
pub enum HuGeError {
    /// 截图捕获失败
    #[error("截图捕获失败: {0}")]
    CaptureError(String),

    /// 热键注册失败
    #[error("热键注册失败: {0}")]
    HotkeyError(String),

    /// 窗口操作失败
    #[error("窗口操作失败: {0}")]
    WindowError(String),

    /// Sidecar 通信失败
    #[error("Sidecar 通信失败: {0}")]
    SidecarError(String),

    /// OCR 识别错误
    #[error("OCR 识别错误: {0}")]
    OcrError(String),

    /// 文件系统错误
    #[error("文件系统错误: {0}")]
    FileError(#[from] std::io::Error),

    /// 数据库错误（来自 rusqlite）
    #[error("数据库错误: {0}")]
    DatabaseError(#[from] rusqlite::Error),

    /// 数据库错误（自定义消息）
    #[error("数据库错误: {0}")]
    Database(String),

    /// 序列化错误
    #[error("序列化错误: {0}")]
    SerializationError(#[from] serde_json::Error),

    /// 配置错误
    #[error("配置错误: {0}")]
    ConfigError(String),

    /// 超时错误
    #[error("操作超时: {0}")]
    TimeoutError(String),

    /// 未知错误
    #[error("未知错误: {0}")]
    Unknown(String),

    /// 内部错误（用于规章索引等内部模块）
    #[error("内部错误: {0}")]
    Internal(String),
}

/// 为 HuGeError 实现 Serialize，以便可以传递给前端
///
/// Tauri 命令返回的错误必须实现 Serialize。
/// 这里我们将错误序列化为字符串形式。
impl Serialize for HuGeError {
    fn serialize<S>(&self, serializer: S) -> Result<S::Ok, S::Error>
    where
        S: serde::ser::Serializer,
    {
        serializer.serialize_str(self.to_string().as_ref())
    }
}

/// 便捷类型别名
pub type HuGeResult<T> = Result<T, HuGeError>;

/// 从字符串创建 HuGeError 的便捷方法
impl From<String> for HuGeError {
    fn from(s: String) -> Self {
        HuGeError::Unknown(s)
    }
}

impl From<&str> for HuGeError {
    fn from(s: &str) -> Self {
        HuGeError::Unknown(s.to_string())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_error_display() {
        let err = HuGeError::CaptureError("屏幕捕获超时".to_string());
        assert_eq!(err.to_string(), "截图捕获失败: 屏幕捕获超时");
    }

    #[test]
    fn test_error_serialize() {
        let err = HuGeError::HotkeyError("Ctrl+Shift+A 已被占用".to_string());
        let json = serde_json::to_string(&err).unwrap();
        assert_eq!(json, "\"热键注册失败: Ctrl+Shift+A 已被占用\"");
    }

    #[test]
    fn test_error_from_io() {
        let io_err = std::io::Error::new(std::io::ErrorKind::NotFound, "文件不存在");
        let err: HuGeError = io_err.into();
        assert!(err.to_string().contains("文件系统错误"));
    }

    #[test]
    fn test_error_from_string() {
        let err: HuGeError = "测试错误".into();
        assert!(matches!(err, HuGeError::Unknown(_)));
    }
}
