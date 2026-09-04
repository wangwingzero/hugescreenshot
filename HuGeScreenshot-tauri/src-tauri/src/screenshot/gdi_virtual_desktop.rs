//! 通过 GDI 捕获整个虚拟桌面，再按显示器/区域裁剪。
//!
//! 旧版 Windows 10 上 per-monitor GDI（screenshots-rs）在副屏负坐标时
//! 常只抓到壁纸层；BitBlt 整屏虚拟桌面可拿到合成后的桌面内容。

use crate::error::{HuGeError, HuGeResult};
use image::RgbaImage;
use tracing::{debug, info};

/// 捕获整个虚拟桌面，返回 RGBA 图像及虚拟桌面原点 (vx, vy)。
pub fn capture_virtual_desktop_rgba() -> HuGeResult<(RgbaImage, i32, i32)> {
    use windows::Win32::Foundation::HWND;
    use windows::Win32::Graphics::Gdi::{
        BitBlt, CreateCompatibleBitmap, CreateCompatibleDC, DeleteDC, DeleteObject, GetDC, GetDIBits,
        ReleaseDC, SelectObject, BITMAPINFO, BITMAPINFOHEADER, BI_RGB, DIB_RGB_COLORS, HGDIOBJ,
        SRCCOPY,
    };
    use windows::Win32::UI::WindowsAndMessaging::{
        GetSystemMetrics, SM_CXVIRTUALSCREEN, SM_CYVIRTUALSCREEN, SM_XVIRTUALSCREEN,
        SM_YVIRTUALSCREEN,
    };

    unsafe {
        let vx = GetSystemMetrics(SM_XVIRTUALSCREEN);
        let vy = GetSystemMetrics(SM_YVIRTUALSCREEN);
        let vw = GetSystemMetrics(SM_CXVIRTUALSCREEN);
        let vh = GetSystemMetrics(SM_CYVIRTUALSCREEN);

        if vw <= 0 || vh <= 0 {
            return Err(HuGeError::CaptureError(format!(
                "虚拟桌面尺寸无效: {}x{}",
                vw, vh
            )));
        }

        let hdc_screen = GetDC(HWND::default());
        if hdc_screen.is_invalid() {
            return Err(HuGeError::CaptureError("GetDC 失败".to_string()));
        }

        let hdc_mem = CreateCompatibleDC(hdc_screen);
        if hdc_mem.is_invalid() {
            ReleaseDC(HWND::default(), hdc_screen);
            return Err(HuGeError::CaptureError("CreateCompatibleDC 失败".to_string()));
        }

        let hbitmap = CreateCompatibleBitmap(hdc_screen, vw, vh);
        if hbitmap.is_invalid() {
            let _ = DeleteDC(hdc_mem);
            ReleaseDC(HWND::default(), hdc_screen);
            return Err(HuGeError::CaptureError("CreateCompatibleBitmap 失败".to_string()));
        }

        let old_obj = SelectObject(hdc_mem, HGDIOBJ::from(hbitmap));
        let blt_ok = BitBlt(hdc_mem, 0, 0, vw, vh, hdc_screen, vx, vy, SRCCOPY).is_ok();
        SelectObject(hdc_mem, old_obj);

        if !blt_ok {
            let _ = DeleteObject(HGDIOBJ::from(hbitmap));
            let _ = DeleteDC(hdc_mem);
            ReleaseDC(HWND::default(), hdc_screen);
            return Err(HuGeError::CaptureError("BitBlt 虚拟桌面失败".to_string()));
        }

        let width = vw as u32;
        let height = vh as u32;
        let row_bytes = (width * 4) as usize;
        let mut pixels = vec![0u8; row_bytes * height as usize];

        let mut bmi = BITMAPINFO {
            bmiHeader: BITMAPINFOHEADER {
                biSize: std::mem::size_of::<BITMAPINFOHEADER>() as u32,
                biWidth: vw,
                biHeight: -(vh as i32),
                biPlanes: 1,
                biBitCount: 32,
                biCompression: BI_RGB.0 as u32,
                ..Default::default()
            },
            ..Default::default()
        };

        let dib_lines = GetDIBits(
            hdc_mem,
            hbitmap,
            0,
            height,
            Some(pixels.as_mut_ptr().cast()),
            &mut bmi,
            DIB_RGB_COLORS,
        );

        let _ = DeleteObject(HGDIOBJ::from(hbitmap));
        let _ = DeleteDC(hdc_mem);
        ReleaseDC(HWND::default(), hdc_screen);

        if dib_lines == 0 {
            return Err(HuGeError::CaptureError("GetDIBits 读取虚拟桌面失败".to_string()));
        }

        for chunk in pixels.chunks_exact_mut(4) {
            chunk.swap(0, 2);
        }

        debug!(
            "GDI 虚拟桌面捕获完成: {}x{} @ ({}, {})",
            width, height, vx, vy
        );

        let image = RgbaImage::from_raw(width, height, pixels).ok_or_else(|| {
            HuGeError::CaptureError("无法创建虚拟桌面 RGBA 图像".to_string())
        })?;

        Ok((image, vx, vy))
    }
}

/// 从虚拟桌面图像中裁剪指定虚拟坐标矩形。
pub fn crop_virtual_desktop(
    image: &RgbaImage,
    origin_x: i32,
    origin_y: i32,
    crop_x: i32,
    crop_y: i32,
    crop_w: u32,
    crop_h: u32,
) -> HuGeResult<RgbaImage> {
    if crop_w == 0 || crop_h == 0 {
        return Err(HuGeError::CaptureError("裁剪区域尺寸为 0".to_string()));
    }

    let local_x = crop_x.saturating_sub(origin_x) as u32;
    let local_y = crop_y.saturating_sub(origin_y) as u32;

    let img_w = image.width();
    let img_h = image.height();

    if local_x + crop_w > img_w || local_y + crop_h > img_h {
        return Err(HuGeError::CaptureError(format!(
            "裁剪区域超出虚拟桌面: local=({}, {}) size={}x{}, desktop={}x{}",
            local_x, local_y, crop_w, crop_h, img_w, img_h
        )));
    }

    use image::GenericImageView;
    Ok(image.view(local_x, local_y, crop_w, crop_h).to_image())
}

/// 捕获单个显示器的虚拟桌面区域。
pub fn capture_monitor_via_virtual_desktop_gdi(
    monitor_x: i32,
    monitor_y: i32,
    monitor_width: u32,
    monitor_height: u32,
) -> HuGeResult<RgbaImage> {
    let start = std::time::Instant::now();
    let (full, vx, vy) = capture_virtual_desktop_rgba()?;
    let cropped =
        crop_virtual_desktop(&full, vx, vy, monitor_x, monitor_y, monitor_width, monitor_height)?;
    info!(
        "GDI 虚拟桌面单屏裁剪完成: {}x{} @ ({}, {}), 耗时: {}ms",
        monitor_width,
        monitor_height,
        monitor_x,
        monitor_y,
        start.elapsed().as_millis()
    );
    Ok(cropped)
}

#[cfg(test)]
mod tests {
    use super::crop_virtual_desktop;
    use image::RgbaImage;

    #[test]
    fn crop_virtual_desktop_maps_negative_origin() {
        let mut data = vec![0u8; 4 * 4 * 4];
        for y in 0..4 {
            for x in 0..4 {
                let idx = ((y * 4 + x) * 4) as usize;
                data[idx] = x as u8 * 40;
                data[idx + 1] = y as u8 * 40;
                data[idx + 2] = 128;
                data[idx + 3] = 255;
            }
        }
        let image = RgbaImage::from_raw(4, 4, data).expect("test image");

        let cropped = crop_virtual_desktop(&image, -2, 0, -1, 1, 2, 2).expect("crop");
        assert_eq!(cropped.dimensions(), (2, 2));
        assert_eq!(cropped.get_pixel(0, 0)[0], 40);
    }
}
