//! 截图帧有效性检测
//!
//! WDA / 显卡驱动 / DXGI 偶发返回尺寸正确但内容全黑的无效帧。
//! WGC 路径已有检测；DXGI 与 GDI 回退路径共用此模块。

/// 检测 RGBA 帧是否近乎全黑（无效截图）
///
/// 仅当接近 100% 像素为纯黑且总亮度极低时才判定无效，
/// 避免误判深色桌面壁纸。
pub(crate) fn is_probably_black_frame_rgba(data: &[u8], width: u32, height: u32) -> bool {
    is_probably_black_frame(data, width, height, 0, 1, 2)
}

/// 检测 BGRA 帧是否近乎全黑（无效截图）
pub(crate) fn is_probably_black_frame_bgra(data: &[u8], width: u32, height: u32) -> bool {
    is_probably_black_frame(data, width, height, 2, 1, 0)
}

fn is_probably_black_frame(
    data: &[u8],
    width: u32,
    height: u32,
    r_idx: usize,
    g_idx: usize,
    b_idx: usize,
) -> bool {
    let expected_len = width as usize * height as usize * 4;
    if expected_len == 0 || data.len() < expected_len {
        return false;
    }

    let total_pixels = width as u64 * height as u64;
    let mut black_pixels = 0u64;
    let mut luma_sum = 0u64;

    for pixel in data[..expected_len].chunks_exact(4) {
        let r = pixel[r_idx] as u64;
        let g = pixel[g_idx] as u64;
        let b = pixel[b_idx] as u64;

        if r <= 2 && g <= 2 && b <= 2 {
            black_pixels += 1;
        }
        luma_sum += r + g + b;
    }

    black_pixels * 10_000 >= total_pixels * 9_995 && luma_sum <= total_pixels * 3
}

#[cfg(test)]
mod tests {
    use super::{is_probably_black_frame_bgra, is_probably_black_frame_rgba};

    #[test]
    fn detects_all_black_rgba_frame() {
        let data = vec![0u8; 32 * 24 * 4];
        assert!(is_probably_black_frame_rgba(&data, 32, 24));
    }

    #[test]
    fn detects_all_black_bgra_frame() {
        let data = vec![0u8; 32 * 24 * 4];
        assert!(is_probably_black_frame_bgra(&data, 32, 24));
    }

    #[test]
    fn allows_normal_rgba_frame() {
        let mut data = vec![0u8; 100 * 100 * 4];
        for (i, pixel) in data.chunks_exact_mut(4).enumerate() {
            pixel[0] = (i % 256) as u8;
            pixel[1] = 128;
            pixel[2] = 64;
            pixel[3] = 255;
        }
        assert!(!is_probably_black_frame_rgba(&data, 100, 100));
    }

    #[test]
    fn rejects_invalid_dimensions() {
        assert!(!is_probably_black_frame_rgba(&[0, 0, 0], 10, 10));
    }
}
