//! 图片哈希计算
//!
//! 使用 MD5 计算图片哈希，用于去重检测。
//!
//! # 设计原则
//!
//! - 使用 MD5 而非更安全的哈希算法（SHA-256），因为这里只需要去重，不需要密码学安全
//! - MD5 速度快，对于图片去重场景足够可靠
//! - 支持从文件和内存数据计算哈希

use std::fs::File;
use std::io::{BufReader, Read};
use std::path::Path;
use tracing::{debug, error};

use crate::error::{HuGeError, HuGeResult};

/// 计算文件的 MD5 哈希
///
/// # 参数
///
/// - `path`: 文件路径
///
/// # 返回
///
/// 返回 32 位小写十六进制字符串
///
/// # 示例
///
/// ```ignore
/// let hash = compute_file_hash("/tmp/screenshot.png")?;
/// println!("文件哈希: {}", hash);  // e.g., "d41d8cd98f00b204e9800998ecf8427e"
/// ```
pub fn compute_file_hash<P: AsRef<Path>>(path: P) -> HuGeResult<String> {
    let path = path.as_ref();

    let file = File::open(path).map_err(|e| {
        error!("打开文件失败 {:?}: {}", path, e);
        HuGeError::FileError(e)
    })?;

    let mut reader = BufReader::new(file);
    let mut buffer = Vec::new();

    reader.read_to_end(&mut buffer).map_err(|e| {
        error!("读取文件失败 {:?}: {}", path, e);
        HuGeError::FileError(e)
    })?;

    let hash = compute_bytes_hash(&buffer);

    debug!("计算文件哈希 {:?}: {}", path, hash);

    Ok(hash)
}

/// 计算字节数据的 MD5 哈希
///
/// # 参数
///
/// - `data`: 字节数据
///
/// # 返回
///
/// 返回 32 位小写十六进制字符串
pub fn compute_bytes_hash(data: &[u8]) -> String {
    let digest = md5::compute(data);
    format!("{:x}", digest)
}

/// 快速哈希检查（仅计算前 N 字节）
///
/// 用于大文件的初步去重筛选，减少 I/O 开销。
/// 如果快速哈希相同，再计算完整哈希确认。
///
/// # 参数
///
/// - `path`: 文件路径
/// - `bytes_to_read`: 读取的字节数（默认 64KB）
///
/// # 返回
///
/// 返回快速哈希和文件大小的元组
pub fn compute_quick_hash<P: AsRef<Path>>(
    path: P,
    bytes_to_read: usize,
) -> HuGeResult<(String, u64)> {
    let path = path.as_ref();

    let file = File::open(path).map_err(|e| {
        error!("打开文件失败 {:?}: {}", path, e);
        HuGeError::FileError(e)
    })?;

    let file_size = file.metadata().map(|m| m.len()).unwrap_or(0);

    let mut reader = BufReader::new(file);
    let mut buffer = vec![0u8; bytes_to_read.min(file_size as usize)];

    let bytes_read = reader.read(&mut buffer).map_err(|e| {
        error!("读取文件失败 {:?}: {}", path, e);
        HuGeError::FileError(e)
    })?;

    buffer.truncate(bytes_read);

    // 组合文件大小和内容哈希，增加唯一性
    let size_bytes = file_size.to_le_bytes();
    let mut combined = Vec::with_capacity(size_bytes.len() + buffer.len());
    combined.extend_from_slice(&size_bytes);
    combined.extend_from_slice(&buffer);

    let hash = compute_bytes_hash(&combined);

    debug!("计算快速哈希 {:?}: {} (前 {} 字节 + 文件大小 {})", path, hash, bytes_read, file_size);

    Ok((hash, file_size))
}

/// 默认快速哈希读取字节数（64KB）
pub const DEFAULT_QUICK_HASH_BYTES: usize = 65536;

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;
    use tempfile::NamedTempFile;

    #[test]
    fn test_compute_bytes_hash() {
        let data = b"Hello, World!";
        let hash = compute_bytes_hash(data);
        // MD5("Hello, World!") = 65a8e27d8879283831b664bd8b7f0ad4
        assert_eq!(hash, "65a8e27d8879283831b664bd8b7f0ad4");
    }

    #[test]
    fn test_compute_bytes_hash_empty() {
        let data = b"";
        let hash = compute_bytes_hash(data);
        // MD5("") = d41d8cd98f00b204e9800998ecf8427e
        assert_eq!(hash, "d41d8cd98f00b204e9800998ecf8427e");
    }

    #[test]
    fn test_compute_file_hash() {
        let mut temp_file = NamedTempFile::new().unwrap();
        temp_file.write_all(b"Hello, World!").unwrap();
        temp_file.flush().unwrap();

        let hash = compute_file_hash(temp_file.path()).unwrap();
        assert_eq!(hash, "65a8e27d8879283831b664bd8b7f0ad4");
    }

    #[test]
    fn test_same_content_same_hash() {
        let data1 = b"Test content for hash";
        let data2 = b"Test content for hash";

        let hash1 = compute_bytes_hash(data1);
        let hash2 = compute_bytes_hash(data2);

        assert_eq!(hash1, hash2);
    }

    #[test]
    fn test_different_content_different_hash() {
        let data1 = b"Content A";
        let data2 = b"Content B";

        let hash1 = compute_bytes_hash(data1);
        let hash2 = compute_bytes_hash(data2);

        assert_ne!(hash1, hash2);
    }

    #[test]
    fn test_quick_hash() {
        let mut temp_file = NamedTempFile::new().unwrap();
        let content = b"A".repeat(100000); // 100KB
        temp_file.write_all(&content).unwrap();
        temp_file.flush().unwrap();

        let (quick_hash, size) = compute_quick_hash(temp_file.path(), 1024).unwrap();

        assert!(!quick_hash.is_empty());
        assert_eq!(quick_hash.len(), 32);
        assert_eq!(size, 100000);
    }

    #[test]
    fn test_quick_hash_small_file() {
        let mut temp_file = NamedTempFile::new().unwrap();
        temp_file.write_all(b"Small").unwrap();
        temp_file.flush().unwrap();

        // 请求的字节数大于文件大小
        let (hash, size) = compute_quick_hash(temp_file.path(), 10000).unwrap();

        assert!(!hash.is_empty());
        assert_eq!(size, 5);
    }

    #[test]
    fn test_hash_length() {
        let hash = compute_bytes_hash(b"Any content");
        // MD5 哈希是 128 位 = 32 个十六进制字符
        assert_eq!(hash.len(), 32);
    }
}
