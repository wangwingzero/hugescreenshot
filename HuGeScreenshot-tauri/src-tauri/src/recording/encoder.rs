//! FFmpeg 编码器模块
//!
//! 通过 FFmpeg 子进程将原始帧数据编码为 H.264/MP4 视频。
//! 使用 stdin 管道传输 BGRA 帧数据。

use std::io::{BufWriter, Write};
use std::path::{Path, PathBuf};
use std::process::{Child, ChildStdin, Command, Stdio};
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::{Arc, OnceLock};
use std::time::Instant;
use tracing::{debug, error, info, warn};

use super::frame_capture::CapturedFrame;
use crate::error::{HuGeError, HuGeResult};

/// FFmpeg 编码器配置
#[derive(Debug, Clone)]
pub struct EncoderConfig {
    /// 输出文件路径
    pub output_path: PathBuf,
    /// 视频宽度（物理像素，必须为偶数）
    pub width: u32,
    /// 视频高度（物理像素，必须为偶数）
    pub height: u32,
    /// 帧率
    pub fps: u32,
    /// 恒定质量因子 (CRF)，越低质量越好，范围 0-51，默认 23
    pub crf: u32,
    /// 编码预设：ultrafast, superfast, veryfast, faster, fast, medium, slow
    pub preset: String,
    /// 像素格式输入 (bgra, 录屏使用原始 BGRA 不做转换以提升性能)
    pub input_pixel_format: String,
    /// 是否包含音频输入文件
    pub audio_input: Option<PathBuf>,
}

impl Default for EncoderConfig {
    fn default() -> Self {
        Self {
            output_path: PathBuf::from("output.mp4"),
            width: 1920,
            height: 1080,
            fps: 30,
            crf: 23,
            preset: "fast".to_string(),
            input_pixel_format: "bgra".to_string(),
            audio_input: None,
        }
    }
}

/// 硬件编码器类型
#[derive(Debug, Clone, PartialEq)]
enum HwEncoder {
    /// NVIDIA NVENC
    Nvenc,
    /// AMD AMF
    Amf,
    /// Intel QuickSync
    Qsv,
    /// 软件编码 (libx264)
    Software,
}

impl std::fmt::Display for HwEncoder {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            HwEncoder::Nvenc => write!(f, "h264_nvenc (NVIDIA)"),
            HwEncoder::Amf => write!(f, "h264_amf (AMD)"),
            HwEncoder::Qsv => write!(f, "h264_qsv (Intel)"),
            HwEncoder::Software => write!(f, "libx264 (CPU)"),
        }
    }
}

/// FFmpeg 编码器
///
/// 管理 FFmpeg 子进程的生命周期，接收原始帧数据并编码为视频。
/// 自动检测并优先使用硬件编码器（NVENC/AMF/QSV）以降低 CPU 占用。
pub struct FfmpegEncoder {
    config: EncoderConfig,
    process: Option<Child>,
    /// 带缓冲的 stdin 写入器，减少管道阻塞
    buffered_stdin: Option<BufWriter<ChildStdin>>,
    frame_count: Arc<AtomicU64>,
    is_running: Arc<AtomicBool>,
}

impl FfmpegEncoder {
    /// 创建 FFmpeg 编码器
    pub fn new(config: EncoderConfig) -> Self {
        Self {
            config,
            process: None,
            buffered_stdin: None,
            frame_count: Arc::new(AtomicU64::new(0)),
            is_running: Arc::new(AtomicBool::new(false)),
        }
    }

    /// 获取帧计数器（可共享）
    pub fn frame_count(&self) -> Arc<AtomicU64> {
        self.frame_count.clone()
    }

    /// 获取运行状态标志
    pub fn is_running(&self) -> Arc<AtomicBool> {
        self.is_running.clone()
    }

    /// 查找 FFmpeg 可执行文件路径
    fn find_ffmpeg() -> HuGeResult<PathBuf> {
        // 1. 检查应用资源目录（打包时捆绑的 ffmpeg）
        if let Ok(exe_path) = std::env::current_exe() {
            let app_dir = exe_path.parent().unwrap_or(Path::new("."));
            let bundled_ffmpeg = app_dir.join("ffmpeg.exe");
            if bundled_ffmpeg.exists() {
                info!("使用捆绑的 FFmpeg: {:?}", bundled_ffmpeg);
                return Ok(bundled_ffmpeg);
            }
            // 也检查 resources 子目录
            let resources_ffmpeg = app_dir.join("resources").join("ffmpeg.exe");
            if resources_ffmpeg.exists() {
                info!("使用资源目录的 FFmpeg: {:?}", resources_ffmpeg);
                return Ok(resources_ffmpeg);
            }
        }

        // 2. 检查 PATH 中的 ffmpeg
        if let Ok(output) = Command::new("where").arg("ffmpeg").output() {
            if output.status.success() {
                let path_str = String::from_utf8_lossy(&output.stdout);
                if let Some(first_line) = path_str.lines().next() {
                    let path = PathBuf::from(first_line.trim());
                    if path.exists() {
                        info!("使用系统 PATH 中的 FFmpeg: {:?}", path);
                        return Ok(path);
                    }
                }
            }
        }

        // 3. 直接尝试 "ffmpeg" 命令（依赖 PATH）
        info!("尝试使用 PATH 中的 ffmpeg 命令");
        Ok(PathBuf::from("ffmpeg"))
    }

    /// 检测可用的硬件编码器（结果会被缓存）
    ///
    /// 按优先级依次检测 NVENC → AMF → QSV，如果都不可用则回退到 libx264。
    /// 通过实际运行试编码来检测（而非仅检查 -encoders 列表），
    /// 确保编码器在当前硬件/驱动环境下真正可用。
    /// 首次检测后结果会缓存到进程级 OnceLock 中，避免重复试编码。
    fn detect_hardware_encoder(ffmpeg_path: &Path) -> HwEncoder {
        static CACHED_ENCODER: OnceLock<HwEncoder> = OnceLock::new();

        if let Some(cached) = CACHED_ENCODER.get() {
            info!("使用缓存的编码器检测结果: {}", cached);
            return cached.clone();
        }

        let result = Self::do_detect_hardware_encoder(ffmpeg_path);
        // 忽略 set 的返回值——如果另一线程先 set 了，用先到的结果即可
        let _ = CACHED_ENCODER.set(result.clone());
        result
    }

    /// 实际执行硬件编码器检测
    fn do_detect_hardware_encoder(ffmpeg_path: &Path) -> HwEncoder {
        // 通过试编码验证硬件编码器是否真正可用。
        // 仅检查 `-encoders` 列表不够——FFmpeg 可能编译时包含 NVENC 支持，
        // 但运行时缺少 nvcuda.dll 或驱动版本过低，导致编码器初始化失败。
        let validate_encoder = |ffmpeg: &Path, encoder_name: &str| -> bool {
            let mut cmd = Command::new(ffmpeg);
            // 使用 nullsrc 生成极小的虚拟输入，试运行编码器初始化
            // 只编码 1 帧即可验证编码器是否能成功打开
            cmd.args([
                "-v",
                "quiet",
                "-f",
                "lavfi",
                "-i",
                "nullsrc=s=64x64:d=0.1",
                "-frames:v",
                "1",
                "-c:v",
                encoder_name,
                "-f",
                "null",
                "-",
            ])
            .stdout(Stdio::null())
            .stderr(Stdio::piped());

            #[cfg(windows)]
            {
                use std::os::windows::process::CommandExt;
                cmd.creation_flags(0x08000000); // CREATE_NO_WINDOW
            }

            match cmd.output() {
                Ok(output) => {
                    if output.status.success() {
                        true
                    } else {
                        let stderr = String::from_utf8_lossy(&output.stderr);
                        debug!(
                            "硬件编码器 {} 试编码失败 (exit={:?}): {}",
                            encoder_name,
                            output.status.code(),
                            stderr.trim()
                        );
                        false
                    }
                }
                Err(e) => {
                    debug!("运行 FFmpeg 试编码失败: {}", e);
                    false
                }
            }
        };

        // 按优先级检测硬件编码器（通过实际试编码验证）
        let candidates = [
            ("h264_nvenc", HwEncoder::Nvenc),
            ("h264_amf", HwEncoder::Amf),
            ("h264_qsv", HwEncoder::Qsv),
        ];

        for (name, hw) in &candidates {
            debug!("正在验证硬件编码器: {} ...", name);
            if validate_encoder(ffmpeg_path, name) {
                info!("硬件编码器验证通过: {} ({})", name, hw);
                return hw.clone();
            }
        }

        info!("所有硬件编码器均不可用，使用 libx264 软件编码");
        HwEncoder::Software
    }

    /// 启动 FFmpeg 子进程
    pub fn start(&mut self) -> HuGeResult<()> {
        let ffmpeg_path = Self::find_ffmpeg()?;

        // 确保输出目录存在
        if let Some(parent) = self.config.output_path.parent() {
            std::fs::create_dir_all(parent)?;
        }

        // 构建 FFmpeg 命令
        let mut cmd = Command::new(&ffmpeg_path);

        // 全局选项
        cmd.arg("-y") // 覆盖输出文件
            .arg("-hide_banner")
            .arg("-loglevel").arg("warning");

        // 视频输入（从 stdin 读取原始帧）
        cmd.arg("-f")
            .arg("rawvideo")
            .arg("-pix_fmt")
            .arg(&self.config.input_pixel_format)
            .arg("-s")
            .arg(format!("{}x{}", self.config.width, self.config.height))
            .arg("-r")
            .arg(self.config.fps.to_string())
            .arg("-i")
            .arg("pipe:0");

        // 音频输入（如果有）
        if let Some(ref audio_path) = self.config.audio_input {
            cmd.arg("-i").arg(audio_path);
        }

        // 自动检测最佳编码器
        let hw_encoder = Self::detect_hardware_encoder(&ffmpeg_path);
        info!("选择编码器: {}", hw_encoder);

        match hw_encoder {
            HwEncoder::Nvenc => {
                cmd.arg("-c:v").arg("h264_nvenc")
                    .arg("-preset").arg("p4")        // p1(fastest)..p7(slowest), p4=medium
                    .arg("-rc").arg("vbr")            // 可变码率
                    .arg("-cq").arg(self.config.crf.to_string()) // 恒定质量
                    .arg("-pix_fmt").arg("yuv420p")
                    .arg("-tune").arg("ll")           // 低延迟
                    .arg("-b:v").arg("0"); // 无码率上限（CQ 模式）
            }
            HwEncoder::Amf => {
                cmd.arg("-c:v")
                    .arg("h264_amf")
                    .arg("-quality")
                    .arg("speed")
                    .arg("-rc")
                    .arg("cqp")
                    .arg("-qp_i")
                    .arg(self.config.crf.to_string())
                    .arg("-qp_p")
                    .arg(self.config.crf.to_string())
                    .arg("-pix_fmt")
                    .arg("yuv420p");
            }
            HwEncoder::Qsv => {
                cmd.arg("-c:v")
                    .arg("h264_qsv")
                    .arg("-preset")
                    .arg("fast")
                    .arg("-global_quality")
                    .arg(self.config.crf.to_string())
                    .arg("-pix_fmt")
                    .arg("yuv420p");
            }
            HwEncoder::Software => {
                // 软件编码强制使用 ultrafast 预设，确保实时录屏时 CPU 编码跟得上帧捕获速度
                // （fast/medium 等预设在较高分辨率下无法实时编码 30fps，导致大量丢帧）
                warn!("使用 CPU 软件编码 (libx264 ultrafast)，CPU 占用会较高。建议安装 NVIDIA/AMD/Intel 显卡驱动以启用硬件加速");
                cmd.arg("-c:v")
                    .arg("libx264")
                    .arg("-preset")
                    .arg("ultrafast")
                    .arg("-crf")
                    .arg(self.config.crf.to_string())
                    .arg("-pix_fmt")
                    .arg("yuv420p")
                    .arg("-tune")
                    .arg("zerolatency");
            }
        }

        // 音频编码选项（如果有音频输入）
        if self.config.audio_input.is_some() {
            cmd.arg("-c:a").arg("aac").arg("-b:a").arg("128k");
        }

        // 输出文件
        cmd.arg(&self.config.output_path);

        // 设置 stdin 为管道，stdout/stderr 管道用于错误检测
        cmd.stdin(Stdio::piped()).stdout(Stdio::null()).stderr(Stdio::piped());

        // Windows: 隐藏控制台窗口
        #[cfg(windows)]
        {
            use std::os::windows::process::CommandExt;
            cmd.creation_flags(0x08000000); // CREATE_NO_WINDOW
        }

        info!(
            "启动 FFmpeg 编码器: {:?}, {}x{} @ {}fps, CRF={}, preset={}",
            self.config.output_path,
            self.config.width,
            self.config.height,
            self.config.fps,
            self.config.crf,
            self.config.preset,
        );

        let mut process = cmd.spawn().map_err(|e| {
            error!("启动 FFmpeg 失败: {}", e);
            if e.kind() == std::io::ErrorKind::NotFound {
                HuGeError::CaptureError(
                    "FFmpeg 未找到。请安装 FFmpeg 或将 ffmpeg.exe 放入应用目录。".to_string(),
                )
            } else {
                HuGeError::CaptureError(format!("启动 FFmpeg 失败: {}", e))
            }
        })?;

        // 提取 stdin 并用 BufWriter 包装（缓冲区大小 = 2 帧，减少管道阻塞）
        let stdin = process
            .stdin
            .take()
            .ok_or_else(|| HuGeError::CaptureError("无法获取 FFmpeg stdin".to_string()))?;
        let buf_size = (self.config.width * self.config.height * 4 * 2) as usize;
        self.buffered_stdin = Some(BufWriter::with_capacity(buf_size, stdin));

        self.process = Some(process);
        self.is_running.store(true, Ordering::SeqCst);
        self.frame_count.store(0, Ordering::SeqCst);

        info!("FFmpeg 编码器已启动");
        Ok(())
    }

    /// 写入一帧数据
    ///
    /// 通过 BufWriter 写入以减少系统调用次数和管道阻塞概率。
    pub fn write_frame(&mut self, frame: &CapturedFrame) -> HuGeResult<()> {
        if let Some(ref mut writer) = self.buffered_stdin {
            // 写入 BGRA 帧数据（通过 BufWriter 缓冲）
            writer.write_all(&frame.data).map_err(|e| {
                error!("写入帧数据到 FFmpeg 失败: {}", e);
                HuGeError::CaptureError(format!("写入帧失败: {}", e))
            })?;

            self.frame_count.fetch_add(1, Ordering::Relaxed);
            Ok(())
        } else {
            Err(HuGeError::CaptureError("FFmpeg 未启动或 stdin 不可用".to_string()))
        }
    }

    /// 停止编码器并等待 FFmpeg 完成
    ///
    /// 关闭 stdin 管道触发 FFmpeg 刷新并完成编码。
    /// 返回最终帧计数。
    pub fn stop(&mut self) -> HuGeResult<u64> {
        let final_count = self.frame_count.load(Ordering::SeqCst);
        info!("停止 FFmpeg 编码器，共 {} 帧", final_count);

        if let Some(mut process) = self.process.take() {
            // 先刷新 BufWriter 确保所有数据写入，然后 drop 关闭 stdin 管道
            if let Some(writer) = self.buffered_stdin.take() {
                // into_inner 会先 flush，然后返回 ChildStdin
                match writer.into_inner() {
                    Ok(_stdin) => { /* drop stdin 关闭管道 */ }
                    Err(e) => warn!("刷新 BufWriter 失败: {}", e),
                }
            }
            drop(process.stdin.take());

            // 等待 FFmpeg 完成（最多 30 秒）
            let start = Instant::now();
            let timeout = std::time::Duration::from_secs(30);

            loop {
                match process.try_wait() {
                    Ok(Some(status)) => {
                        if status.success() {
                            info!("FFmpeg 编码完成");
                        } else {
                            // 读取 stderr 获取错误信息
                            let stderr_output = if let Some(mut stderr) = process.stderr.take() {
                                use std::io::Read;
                                let mut buf = String::new();
                                stderr.read_to_string(&mut buf).unwrap_or(0);
                                buf
                            } else {
                                String::new()
                            };
                            warn!(
                                "FFmpeg 退出码异常: {:?}, stderr: {}",
                                status.code(),
                                stderr_output
                            );
                        }
                        break;
                    }
                    Ok(None) => {
                        if start.elapsed() > timeout {
                            warn!("FFmpeg 超时未完成，强制终止");
                            let _ = process.kill();
                            break;
                        }
                        std::thread::sleep(std::time::Duration::from_millis(100));
                    }
                    Err(e) => {
                        error!("等待 FFmpeg 完成失败: {}", e);
                        break;
                    }
                }
            }
        }

        self.is_running.store(false, Ordering::SeqCst);
        Ok(final_count)
    }

    /// 获取已编码帧数
    pub fn get_frame_count(&self) -> u64 {
        self.frame_count.load(Ordering::SeqCst)
    }

    /// 获取输出文件路径
    pub fn output_path(&self) -> &Path {
        &self.config.output_path
    }
}

impl Drop for FfmpegEncoder {
    fn drop(&mut self) {
        if self.process.is_some() {
            let _ = self.stop();
        }
    }
}
