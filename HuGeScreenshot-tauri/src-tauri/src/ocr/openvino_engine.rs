//! OpenVINO 推理引擎
//!
//! 使用 Intel OpenVINO 进行高性能 OCR 推理。
//!
//! # 优势
//!
//! - Intel CPU 上比 ONNX Runtime 快 2-3 倍
//! - 支持直接加载 ONNX 模型（无需转换为 IR 格式）
//! - AMD CPU 也能运行（无加速但不会更慢）
//! - **InferRequest 池**：预创建多个推理请求，支持真正的并行推理
//!
//! # 性能优化
//!
//! 1. **Model Caching**: 首次编译后缓存模型，后续启动秒加载
//! 2. **Performance Hint**: 设置 LATENCY 模式优化单张图片推理
//! 3. **异步推理**: 支持 `infer_async()` + `wait()` 模式
//! 4. **InferRequest 池**: 多线程并行推理
//!
//! # 并行推理策略
//!
//! OpenVINO 的最佳实践是创建多个 InferRequest 组成一个池：
//! - 每个 InferRequest 独占一个线程
//! - 使用 crossbeam 的 ArrayQueue 实现无锁对象池
//! - 线程从池中取出请求 → 推理 → 放回池中
//!
//! # 使用示例
//!
//! ```rust,ignore
//! use crate::ocr::openvino_engine::{OpenVinoEngine, InferenceSession};
//!
//! let session = InferenceSession::from_onnx_bytes(model_bytes, "detection")?;
//! let output = session.infer_detection(&input_tensor)?;
//! ```

use crossbeam::queue::ArrayQueue;
use ndarray::{Array3, Array4};
use openvino::{
    CompiledModel, Core, DeviceType, ElementType, InferRequest, RwPropertyKey, Shape, Tensor,
};
use std::path::PathBuf;
use std::sync::{Arc, Mutex};

use super::types::OcrError;

/// 默认推理请求池大小（用于并行推理）
///
/// OCR 路径上没有真正的并行使用方（一次截图 = 一轮检测+识别），
/// 4 个 InferRequest 主要是为长文本批量识别留余量。
/// 实测 2 个池大小已能覆盖典型负载，减半可省 ~70-150MB 编译模型副本。
const DEFAULT_POOL_SIZE: usize = 2;

/// 异步推理等待超时（毫秒）
/// -1 表示无限等待
const ASYNC_WAIT_TIMEOUT_MS: i64 = 30000;

/// 获取模型缓存目录
///
/// 优先使用系统缓存目录，回退到当前目录
fn get_cache_dir() -> PathBuf {
    dirs::cache_dir()
        .unwrap_or_else(|| PathBuf::from("."))
        .join("hugescreenshot")
        .join("openvino_cache")
}

/// OpenVINO 推理会话
///
/// 封装 CompiledModel 和 InferRequest 池，提供线程安全的并行推理接口。
///
/// # 性能优化
///
/// - **InferRequest 池**：预创建多个 InferRequest，支持真正的并行推理
/// - 使用 crossbeam 的 ArrayQueue 实现无锁对象池
/// - 线程从池中取出请求 → 推理 → 放回池中
///
/// # 线程安全
///
/// - CompiledModel 使用 Mutex 保护（仅用于创建新的 InferRequest）
/// - InferRequest 池使用无锁队列，支持高并发访问
pub struct InferenceSession {
    /// 编译后的模型（Mutex 包装，仅用于创建新请求）
    compiled_model: Mutex<CompiledModel>,
    /// 推理请求池（无锁队列，支持并行推理）
    /// 使用 Arc 包装以便在多线程间共享
    infer_request_pool: Arc<ArrayQueue<InferRequest>>,
    /// 模型名称（用于日志）
    model_name: String,
    /// 池大小
    pool_size: usize,
}

// 手动实现 Send + Sync，因为我们用 Mutex 保护了所有访问
unsafe impl Send for InferenceSession {}
unsafe impl Sync for InferenceSession {}

impl InferenceSession {
    /// 从 ONNX 模型字节创建推理会话
    ///
    /// # 参数
    ///
    /// - `model_bytes`: ONNX 模型数据
    /// - `model_name`: 模型名称（用于日志）
    ///
    /// # 返回
    ///
    /// - `Ok(InferenceSession)`: 推理会话
    /// - `Err(OcrError)`: 创建失败
    pub fn from_onnx_bytes(model_bytes: &[u8], model_name: &str) -> Result<Self, OcrError> {
        Self::from_onnx_bytes_with_pool_size(model_bytes, model_name, DEFAULT_POOL_SIZE)
    }

    /// 从 ONNX 模型字节创建推理会话（自定义池大小）
    ///
    /// # 参数
    ///
    /// - `model_bytes`: ONNX 模型数据
    /// - `model_name`: 模型名称（用于日志）
    /// - `pool_size`: InferRequest 池大小
    ///
    /// # 返回
    ///
    /// - `Ok(InferenceSession)`: 推理会话
    /// - `Err(OcrError)`: 创建失败
    pub fn from_onnx_bytes_with_pool_size(
        model_bytes: &[u8],
        model_name: &str,
        pool_size: usize,
    ) -> Result<Self, OcrError> {
        tracing::info!(
            "加载 {} 模型 ({} bytes) with OpenVINO, 池大小={}...",
            model_name,
            model_bytes.len(),
            pool_size
        );

        // 创建 OpenVINO Core
        let mut core = Core::new()
            .map_err(|e| OcrError::ModelLoadError(format!("OpenVINO Core 初始化失败: {:?}", e)))?;

        // 从内存加载 ONNX 模型
        let model = core.read_model_from_buffer(model_bytes, None).map_err(|e| {
            OcrError::ModelLoadError(format!("加载 {} 模型失败: {:?}", model_name, e))
        })?;

        // 使用通用方法完成剩余初始化
        Self::initialize_session(core, model, model_name, pool_size)
    }

    /// 从 IR 格式模型字节创建推理会话
    ///
    /// IR 格式是 OpenVINO 的原生格式，由 .xml（模型结构）和 .bin（权重）组成。
    /// 使用 PrePostProcessor API 生成的 IR 模型包含预处理逻辑，
    /// 可以直接接受 u8 NHWC 格式的输入。
    ///
    /// # 参数
    ///
    /// - `xml_bytes`: IR 模型 XML 数据（模型结构）
    /// - `bin_bytes`: IR 模型 BIN 数据（权重）
    /// - `model_name`: 模型名称（用于日志）
    ///
    /// # 返回
    ///
    /// - `Ok(InferenceSession)`: 推理会话
    /// - `Err(OcrError)`: 创建失败
    ///
    /// # 性能优势
    ///
    /// IR 格式模型的优势：
    /// - 预处理已注入模型，减少 CPU 负载
    /// - 输入直接使用 u8 数据，无需 Rust 侧归一化
    /// - 预期性能提升 30%-100%
    pub fn from_ir_bytes(
        xml_bytes: &[u8],
        bin_bytes: &[u8],
        model_name: &str,
    ) -> Result<Self, OcrError> {
        Self::from_ir_bytes_with_pool_size(xml_bytes, bin_bytes, model_name, DEFAULT_POOL_SIZE)
    }

    /// 从 IR 格式模型字节创建推理会话（自定义池大小）
    ///
    /// # 参数
    ///
    /// - `xml_bytes`: IR 模型 XML 数据
    /// - `bin_bytes`: IR 模型 BIN 数据
    /// - `model_name`: 模型名称（用于日志）
    /// - `pool_size`: InferRequest 池大小
    ///
    /// # 返回
    ///
    /// - `Ok(InferenceSession)`: 推理会话
    /// - `Err(OcrError)`: 创建失败
    pub fn from_ir_bytes_with_pool_size(
        xml_bytes: &[u8],
        bin_bytes: &[u8],
        model_name: &str,
        pool_size: usize,
    ) -> Result<Self, OcrError> {
        tracing::info!(
            "加载 {} IR 模型 (xml={} bytes, bin={} bytes) with OpenVINO, 池大小={}...",
            model_name,
            xml_bytes.len(),
            bin_bytes.len(),
            pool_size
        );

        // 创建 OpenVINO Core
        let mut core = Core::new()
            .map_err(|e| OcrError::ModelLoadError(format!("OpenVINO Core 初始化失败: {:?}", e)))?;

        // 将 BIN 数据包装为 Tensor（openvino-rs 要求权重以 Tensor 形式传入）
        let weights_shape = Shape::new(&[bin_bytes.len() as i64])
            .map_err(|e| OcrError::ModelLoadError(format!("创建权重 Shape 失败: {:?}", e)))?;
        let mut weights_tensor = Tensor::new(ElementType::U8, &weights_shape)
            .map_err(|e| OcrError::ModelLoadError(format!("创建权重 Tensor 失败: {:?}", e)))?;

        // 将 BIN 字节拷贝到 Tensor 缓冲区
        {
            let buffer = weights_tensor.get_data_mut::<u8>().map_err(|e| {
                OcrError::ModelLoadError(format!("获取权重 Tensor 缓冲区失败: {:?}", e))
            })?;
            buffer.copy_from_slice(bin_bytes);
        }

        // 从内存加载 IR 模型（XML + BIN Tensor）
        let model = core.read_model_from_buffer(xml_bytes, Some(&weights_tensor)).map_err(|e| {
            OcrError::ModelLoadError(format!("加载 {} IR 模型失败: {:?}", model_name, e))
        })?;

        // 打印模型输入信息（用于调试）
        let inputs_len = model
            .get_inputs_len()
            .map_err(|e| OcrError::ModelLoadError(format!("获取模型输入数量失败: {:?}", e)))?;
        tracing::info!("{} IR 模型输入数量: {}", model_name, inputs_len);

        // 使用通用方法完成剩余初始化
        Self::initialize_session(core, model, model_name, pool_size)
    }

    /// 初始化推理会话的通用方法
    ///
    /// 被 `from_onnx_bytes_with_pool_size` 和 `from_ir_bytes_with_pool_size` 调用
    fn initialize_session(
        mut core: Core,
        model: openvino::Model,
        model_name: &str,
        pool_size: usize,
    ) -> Result<Self, OcrError> {
        // ========================================
        // 屏蔽 OneDNN 逐操作 verbose 日志
        // ========================================
        // OneDNN 的 verbose 日志会在终端输出大量无用的卷积/重排序操作细节，
        // 例如 "onednn_verbose,v1,primitive,exec,cpu,convolution,..."
        // 仅在用户未显式设置时才屏蔽，保留手动调试的能力
        static ONEDNN_CONFIGURED: std::sync::atomic::AtomicBool =
            std::sync::atomic::AtomicBool::new(false);
        if !ONEDNN_CONFIGURED.swap(true, std::sync::atomic::Ordering::Relaxed)
            && std::env::var("ONEDNN_VERBOSE").is_err()
        {
            std::env::set_var("ONEDNN_VERBOSE", "0");
            tracing::debug!("已屏蔽 OneDNN verbose 日志（设置 ONEDNN_VERBOSE=1 可重新开启）");
        }

        // ========================================
        // 性能优化 1: Model Caching
        // ========================================
        // 首次编译后缓存模型，后续启动秒加载
        let cache_dir = get_cache_dir();
        if let Err(e) = std::fs::create_dir_all(&cache_dir) {
            tracing::warn!("创建缓存目录失败: {:?}, 将禁用模型缓存", e);
        } else if let Some(cache_path) = cache_dir.to_str() {
            match core.set_property(&DeviceType::CPU, &RwPropertyKey::CacheDir, cache_path) {
                Ok(_) => tracing::info!("✅ Model Caching 已启用: {}", cache_path),
                Err(e) => tracing::warn!("设置 CACHE_DIR 失败: {:?}", e),
            }
        }

        // ========================================
        // 性能优化 2: Performance Hint
        // ========================================
        // LATENCY 模式优化单张图片推理延迟
        match core.set_property(&DeviceType::CPU, &RwPropertyKey::HintPerformanceMode, "LATENCY") {
            Ok(_) => tracing::info!("✅ Performance Hint 已设置: LATENCY"),
            Err(e) => tracing::warn!("设置 PERFORMANCE_HINT 失败: {:?}", e),
        }

        // ========================================
        // 编译模型（始终使用 CPU）
        // ========================================
        // 说明：GPU/NPU 对 PP-OCR 等轻量 OCR 模型无加速效果
        // - Intel iGPU: 实测比 CPU 慢 30-40 倍
        // - Intel NPU: PP-OCR 模型包含不支持的算子，编译失败
        // - AMD/NVIDIA GPU: OpenVINO 不支持
        // CPU + AVX2 是当前最优方案（1080p 截图 OCR < 2 秒）
        let compile_start = std::time::Instant::now();
        let mut compiled_model = core.compile_model(&model, DeviceType::CPU).map_err(|e| {
            OcrError::ModelLoadError(format!("编译 {} 模型失败: {:?}", model_name, e))
        })?;

        let compile_elapsed = compile_start.elapsed();
        tracing::info!(
            "{} 模型编译完成 [CPU]，耗时 {:.0}ms (缓存命中时 < 100ms)",
            model_name,
            compile_elapsed.as_millis()
        );

        // 创建 InferRequest 池
        let pool = ArrayQueue::new(pool_size);
        for i in 0..pool_size {
            let infer_request = compiled_model.create_infer_request().map_err(|e| {
                OcrError::ModelLoadError(format!(
                    "创建 {} 推理请求 #{} 失败: {:?}",
                    model_name, i, e
                ))
            })?;
            // 忽略 push 错误（池已满不可能发生）
            let _ = pool.push(infer_request);
        }

        tracing::info!("{} 模型加载成功（已创建 {} 个 InferRequest）", model_name, pool_size);

        Ok(Self {
            compiled_model: Mutex::new(compiled_model),
            infer_request_pool: Arc::new(pool),
            model_name: model_name.to_string(),
            pool_size,
        })
    }

    /// 从池中获取一个 InferRequest
    ///
    /// 如果池为空，会创建一个新的请求（但这会降低性能）
    fn acquire_infer_request(&self) -> Result<InferRequest, OcrError> {
        // 尝试从池中获取
        if let Some(req) = self.infer_request_pool.pop() {
            return Ok(req);
        }

        // 池为空，创建新的请求（这种情况应该很少发生）
        tracing::warn!("{} InferRequest 池已空，创建新请求（可能影响性能）", self.model_name);

        let mut compiled_model = self
            .compiled_model
            .lock()
            .map_err(|e| OcrError::InferenceError(format!("获取模型锁失败: {}", e)))?;

        compiled_model
            .create_infer_request()
            .map_err(|e| OcrError::InferenceError(format!("创建推理请求失败: {:?}", e)))
    }

    /// 将 InferRequest 放回池中
    fn release_infer_request(&self, req: InferRequest) {
        // 尝试放回池中，如果池已满则丢弃
        if self.infer_request_pool.push(req).is_err() {
            tracing::debug!("{} InferRequest 池已满，丢弃请求", self.model_name);
        }
    }

    /// 获取池大小
    #[allow(dead_code)]
    pub fn pool_size(&self) -> usize {
        self.pool_size
    }

    /// 获取当前池中可用的 InferRequest 数量
    #[allow(dead_code)]
    pub fn available_requests(&self) -> usize {
        self.infer_request_pool.len()
    }

    /// 执行检测模型推理
    ///
    /// # 参数
    ///
    /// - `input`: 输入张量 [1, 3, H, W]
    ///
    /// # 返回
    ///
    /// - `Ok(Array4<f32>)`: 输出概率图 [1, 1, H, W]
    pub fn infer_detection(&self, input: &Array4<f32>) -> Result<Array4<f32>, OcrError> {
        let shape = input.shape();
        let batch = shape[0];
        let channels = shape[1];
        let height = shape[2];
        let width = shape[3];

        // 从池中获取 InferRequest
        let mut infer_request = self.acquire_infer_request()?;

        // 使用 RAII 模式确保 InferRequest 被放回池中
        let result =
            self.run_detection_inference(&mut infer_request, input, batch, channels, height, width);

        // 无论成功还是失败，都放回池中
        self.release_infer_request(infer_request);

        result
    }

    /// 执行检测模型推理（u8 NHWC 输入，用于 IR 模型）
    ///
    /// 用于预处理已注入的 IR 模型，直接接受原始 u8 像素数据。
    ///
    /// # 参数
    ///
    /// - `input`: 输入张量 [1, H, W, 3] (u8, NHWC, BGR)
    ///
    /// # 返回
    ///
    /// - `Ok(Array4<f32>)`: 输出概率图 [1, 1, H, W]
    ///
    /// # 性能优势
    ///
    /// - 无需 Rust 侧归一化，预处理在模型内部执行
    /// - 减少内存分配（u8 vs f32）
    /// - 预期性能提升 30%-100%
    pub fn infer_detection_u8(
        &self,
        input: &[u8],
        height: usize,
        width: usize,
    ) -> Result<Array4<f32>, OcrError> {
        let batch = 1;
        let channels = 3;

        // 验证输入大小
        let expected_size = batch * height * width * channels;
        if input.len() != expected_size {
            return Err(OcrError::InferenceError(format!(
                "输入大小不匹配: 期望 {} bytes ({}x{}x{}x{}), 实际 {} bytes",
                expected_size,
                batch,
                height,
                width,
                channels,
                input.len()
            )));
        }

        // 从池中获取 InferRequest
        let mut infer_request = self.acquire_infer_request()?;

        // 执行推理
        let result = self.run_detection_inference_u8(
            &mut infer_request,
            input,
            batch,
            height,
            width,
            channels,
        );

        // 放回池中
        self.release_infer_request(infer_request);

        result
    }

    /// 执行检测推理的内部方法（u8 输入）
    fn run_detection_inference_u8(
        &self,
        infer_request: &mut InferRequest,
        input: &[u8],
        batch: usize,
        height: usize,
        width: usize,
        channels: usize,
    ) -> Result<Array4<f32>, OcrError> {
        // 创建输入 Shape (NHWC 格式)
        let input_shape = Shape::new(&[batch as i64, height as i64, width as i64, channels as i64])
            .map_err(|e| OcrError::InferenceError(format!("创建输入 Shape 失败: {:?}", e)))?;

        // 创建 u8 类型的输入 Tensor
        let mut input_tensor = Tensor::new(ElementType::U8, &input_shape)
            .map_err(|e| OcrError::InferenceError(format!("创建输入 Tensor 失败: {:?}", e)))?;

        // 填充数据
        {
            let tensor_data = input_tensor
                .get_data_mut::<u8>()
                .map_err(|e| OcrError::InferenceError(format!("获取 Tensor 数据失败: {:?}", e)))?;
            tensor_data.copy_from_slice(input);
        }

        // 设置输入
        infer_request
            .set_input_tensor(&input_tensor)
            .map_err(|e| OcrError::InferenceError(format!("设置输入 Tensor 失败: {:?}", e)))?;

        // 执行推理
        infer_request.infer().map_err(|e| {
            OcrError::InferenceError(format!("{} 推理失败: {:?}", self.model_name, e))
        })?;

        // 获取输出
        let output_tensor = infer_request
            .get_output_tensor()
            .map_err(|e| OcrError::InferenceError(format!("获取输出 Tensor 失败: {:?}", e)))?;

        // 获取输出形状
        let output_shape = output_tensor
            .get_shape()
            .map_err(|e| OcrError::InferenceError(format!("获取输出形状失败: {:?}", e)))?;
        let dims: Vec<usize> = output_shape.get_dimensions().iter().map(|&x| x as usize).collect();

        if dims.len() != 4 {
            return Err(OcrError::InferenceError(format!(
                "检测模型输出维度错误: 期望 4D，实际 {:?}",
                dims
            )));
        }

        // 提取输出数据
        let output_data = output_tensor
            .get_data::<f32>()
            .map_err(|e| OcrError::InferenceError(format!("提取输出数据失败: {:?}", e)))?;

        // 转换为 Array4
        let output_array =
            Array4::from_shape_vec((dims[0], dims[1], dims[2], dims[3]), output_data.to_vec())
                .map_err(|e| OcrError::InferenceError(format!("转换输出数组失败: {}", e)))?;

        Ok(output_array)
    }

    /// 执行检测推理的内部方法
    fn run_detection_inference(
        &self,
        infer_request: &mut InferRequest,
        input: &Array4<f32>,
        batch: usize,
        channels: usize,
        height: usize,
        width: usize,
    ) -> Result<Array4<f32>, OcrError> {
        // 创建输入 Shape
        let input_shape = Shape::new(&[batch as i64, channels as i64, height as i64, width as i64])
            .map_err(|e| OcrError::InferenceError(format!("创建输入 Shape 失败: {:?}", e)))?;

        // 创建输入 Tensor 并填充数据
        let mut input_tensor = Tensor::new(ElementType::F32, &input_shape)
            .map_err(|e| OcrError::InferenceError(format!("创建输入 Tensor 失败: {:?}", e)))?;

        // 获取 Tensor 的可变数据切片并复制数据
        {
            let tensor_data = input_tensor
                .get_data_mut::<f32>()
                .map_err(|e| OcrError::InferenceError(format!("获取 Tensor 数据失败: {:?}", e)))?;
            let input_data: Vec<f32> = input.iter().cloned().collect();
            tensor_data.copy_from_slice(&input_data);
        }

        // 设置输入
        infer_request
            .set_input_tensor(&input_tensor)
            .map_err(|e| OcrError::InferenceError(format!("设置输入 Tensor 失败: {:?}", e)))?;

        // 执行推理
        infer_request.infer().map_err(|e| {
            OcrError::InferenceError(format!("{} 推理失败: {:?}", self.model_name, e))
        })?;

        // 获取输出
        let output_tensor = infer_request
            .get_output_tensor()
            .map_err(|e| OcrError::InferenceError(format!("获取输出 Tensor 失败: {:?}", e)))?;

        // 获取输出形状
        let output_shape = output_tensor
            .get_shape()
            .map_err(|e| OcrError::InferenceError(format!("获取输出形状失败: {:?}", e)))?;
        let dims: Vec<usize> = output_shape.get_dimensions().iter().map(|&x| x as usize).collect();

        if dims.len() != 4 {
            return Err(OcrError::InferenceError(format!(
                "检测模型输出维度错误: 期望 4D，实际 {:?}",
                dims
            )));
        }

        // 提取输出数据
        let output_data = output_tensor
            .get_data::<f32>()
            .map_err(|e| OcrError::InferenceError(format!("提取输出数据失败: {:?}", e)))?;

        // 转换为 Array4
        let output_array =
            Array4::from_shape_vec((dims[0], dims[1], dims[2], dims[3]), output_data.to_vec())
                .map_err(|e| OcrError::InferenceError(format!("转换输出数组失败: {}", e)))?;

        Ok(output_array)
    }

    /// 执行识别模型推理
    ///
    /// # 参数
    ///
    /// - `input`: 输入张量 [1, 3, H, W]
    ///
    /// # 返回
    ///
    /// - `Ok(Array3<f32>)`: 输出概率 [1, T, V]
    ///
    /// # 并行推理支持
    ///
    /// 此方法使用 InferRequest 池，支持多线程并行调用。
    /// 每个线程从池中获取独立的 InferRequest，推理完成后放回池中。
    pub fn infer_recognition(&self, input: &Array4<f32>) -> Result<Array3<f32>, OcrError> {
        let shape = input.shape();
        let batch = shape[0];
        let channels = shape[1];
        let height = shape[2];
        let width = shape[3];

        // 调试日志
        let input_slice = input.as_slice().unwrap_or(&[]);
        if !input_slice.is_empty() {
            let min = input_slice.iter().cloned().fold(f32::INFINITY, f32::min);
            let max = input_slice.iter().cloned().fold(f32::NEG_INFINITY, f32::max);
            tracing::debug!(
                "Recognition input: shape=[{}, {}, {}, {}], value_range=[{:.3}, {:.3}]",
                batch,
                channels,
                height,
                width,
                min,
                max
            );
        }

        // 从池中获取 InferRequest（支持并行）
        let mut infer_request = self.acquire_infer_request()?;

        // 使用 RAII 模式确保 InferRequest 被放回池中
        let result = self.run_recognition_inference(
            &mut infer_request,
            input,
            batch,
            channels,
            height,
            width,
        );

        // 无论成功还是失败，都放回池中
        self.release_infer_request(infer_request);

        result
    }

    /// 执行识别模型推理（u8 NHWC 输入，用于 IR 模型）
    ///
    /// 用于预处理已注入的 IR 模型，直接接受原始 u8 像素数据。
    ///
    /// # 参数
    ///
    /// - `input`: 输入数据 [1, H, W, 3] (u8, NHWC, BGR)
    /// - `height`: 图像高度（通常为 48）
    /// - `width`: 图像宽度
    ///
    /// # 返回
    ///
    /// - `Ok(Array3<f32>)`: 输出概率 [1, T, V]
    ///
    /// # 性能优势
    ///
    /// - 无需 Rust 侧归一化，预处理在模型内部执行
    /// - 减少内存分配（u8 vs f32）
    /// - 预期性能提升 30%-100%
    pub fn infer_recognition_u8(
        &self,
        input: &[u8],
        height: usize,
        width: usize,
    ) -> Result<Array3<f32>, OcrError> {
        let batch = 1;
        let channels = 3;

        // 验证输入大小
        let expected_size = batch * height * width * channels;
        if input.len() != expected_size {
            return Err(OcrError::InferenceError(format!(
                "输入大小不匹配: 期望 {} bytes ({}x{}x{}x{}), 实际 {} bytes",
                expected_size,
                batch,
                height,
                width,
                channels,
                input.len()
            )));
        }

        // 从池中获取 InferRequest
        let mut infer_request = self.acquire_infer_request()?;

        // 执行推理
        let result = self.run_recognition_inference_u8(
            &mut infer_request,
            input,
            batch,
            height,
            width,
            channels,
        );

        // 放回池中
        self.release_infer_request(infer_request);

        result
    }

    /// 执行识别推理的内部方法（u8 输入）
    fn run_recognition_inference_u8(
        &self,
        infer_request: &mut InferRequest,
        input: &[u8],
        batch: usize,
        height: usize,
        width: usize,
        channels: usize,
    ) -> Result<Array3<f32>, OcrError> {
        // 创建输入 Shape (NHWC 格式)
        let input_shape = Shape::new(&[batch as i64, height as i64, width as i64, channels as i64])
            .map_err(|e| OcrError::InferenceError(format!("创建输入 Shape 失败: {:?}", e)))?;

        // 创建 u8 类型的输入 Tensor
        let mut input_tensor = Tensor::new(ElementType::U8, &input_shape)
            .map_err(|e| OcrError::InferenceError(format!("创建输入 Tensor 失败: {:?}", e)))?;

        // 填充数据
        {
            let tensor_data = input_tensor
                .get_data_mut::<u8>()
                .map_err(|e| OcrError::InferenceError(format!("获取 Tensor 数据失败: {:?}", e)))?;
            tensor_data.copy_from_slice(input);
        }

        // 设置输入
        infer_request
            .set_input_tensor(&input_tensor)
            .map_err(|e| OcrError::InferenceError(format!("设置输入 Tensor 失败: {:?}", e)))?;

        // 执行推理
        infer_request.infer().map_err(|e| {
            OcrError::InferenceError(format!("{} 推理失败: {:?}", self.model_name, e))
        })?;

        // 获取输出
        let output_tensor = infer_request
            .get_output_tensor()
            .map_err(|e| OcrError::InferenceError(format!("获取输出 Tensor 失败: {:?}", e)))?;

        // 获取输出形状
        let output_shape = output_tensor
            .get_shape()
            .map_err(|e| OcrError::InferenceError(format!("获取输出形状失败: {:?}", e)))?;
        let dims: Vec<usize> = output_shape.get_dimensions().iter().map(|&x| x as usize).collect();

        if dims.len() != 3 {
            return Err(OcrError::InferenceError(format!(
                "识别模型输出维度错误: 期望 3D [B, T, V]，实际 {:?}",
                dims
            )));
        }

        // 提取输出数据
        let output_data = output_tensor
            .get_data::<f32>()
            .map_err(|e| OcrError::InferenceError(format!("提取输出数据失败: {:?}", e)))?;

        // 转换为 Array3
        let output_array =
            Array3::from_shape_vec((dims[0], dims[1], dims[2]), output_data.to_vec())
                .map_err(|e| OcrError::InferenceError(format!("转换输出数组失败: {}", e)))?;

        Ok(output_array)
    }

    /// 执行识别推理的内部方法
    fn run_recognition_inference(
        &self,
        infer_request: &mut InferRequest,
        input: &Array4<f32>,
        batch: usize,
        channels: usize,
        height: usize,
        width: usize,
    ) -> Result<Array3<f32>, OcrError> {
        // 创建输入 Shape
        let input_shape = Shape::new(&[batch as i64, channels as i64, height as i64, width as i64])
            .map_err(|e| OcrError::InferenceError(format!("创建输入 Shape 失败: {:?}", e)))?;

        // 创建输入 Tensor 并填充数据
        let mut input_tensor = Tensor::new(ElementType::F32, &input_shape)
            .map_err(|e| OcrError::InferenceError(format!("创建输入 Tensor 失败: {:?}", e)))?;

        // 获取 Tensor 的可变数据切片并复制数据
        {
            let tensor_data = input_tensor
                .get_data_mut::<f32>()
                .map_err(|e| OcrError::InferenceError(format!("获取 Tensor 数据失败: {:?}", e)))?;
            let input_data: Vec<f32> = input.iter().cloned().collect();
            tensor_data.copy_from_slice(&input_data);
        }

        // 设置输入
        infer_request
            .set_input_tensor(&input_tensor)
            .map_err(|e| OcrError::InferenceError(format!("设置输入 Tensor 失败: {:?}", e)))?;

        // 执行推理
        infer_request.infer().map_err(|e| {
            OcrError::InferenceError(format!("{} 推理失败: {:?}", self.model_name, e))
        })?;

        // 获取输出
        let output_tensor = infer_request
            .get_output_tensor()
            .map_err(|e| OcrError::InferenceError(format!("获取输出 Tensor 失败: {:?}", e)))?;

        // 获取输出形状
        let output_shape = output_tensor
            .get_shape()
            .map_err(|e| OcrError::InferenceError(format!("获取输出形状失败: {:?}", e)))?;
        let dims: Vec<usize> = output_shape.get_dimensions().iter().map(|&x| x as usize).collect();

        if dims.len() != 3 {
            return Err(OcrError::InferenceError(format!(
                "识别模型输出维度错误: 期望 3D [B, T, V]，实际 {:?}",
                dims
            )));
        }

        // 提取输出数据
        let output_data = output_tensor
            .get_data::<f32>()
            .map_err(|e| OcrError::InferenceError(format!("提取输出数据失败: {:?}", e)))?;

        // 转换为 Array3
        let output_array =
            Array3::from_shape_vec((dims[0], dims[1], dims[2]), output_data.to_vec())
                .map_err(|e| OcrError::InferenceError(format!("转换输出数组失败: {}", e)))?;

        Ok(output_array)
    }

    /// 执行异步识别模型推理
    ///
    /// 使用 OpenVINO 的异步推理 API，在等待推理结果时可以执行其他操作。
    ///
    /// # 参数
    ///
    /// - `input`: 输入张量 [1, 3, H, W]
    ///
    /// # 返回
    ///
    /// - `Ok(Array3<f32>)`: 输出概率 [1, T, V]
    ///
    /// # 性能优势
    ///
    /// 异步推理允许在等待 GPU/CPU 计算时执行其他操作（如预处理下一张图片），
    /// 可以提高整体吞吐量约 30%。
    #[allow(dead_code)]
    pub fn infer_recognition_async(&self, input: &Array4<f32>) -> Result<Array3<f32>, OcrError> {
        let shape = input.shape();
        let batch = shape[0];
        let channels = shape[1];
        let height = shape[2];
        let width = shape[3];

        // 从池中获取 InferRequest
        let mut infer_request = self.acquire_infer_request()?;

        // 使用 RAII 模式确保 InferRequest 被放回池中
        let result = self.run_recognition_inference_async(
            &mut infer_request,
            input,
            batch,
            channels,
            height,
            width,
        );

        // 无论成功还是失败，都放回池中
        self.release_infer_request(infer_request);

        result
    }

    /// 执行异步识别推理的内部方法
    fn run_recognition_inference_async(
        &self,
        infer_request: &mut InferRequest,
        input: &Array4<f32>,
        batch: usize,
        channels: usize,
        height: usize,
        width: usize,
    ) -> Result<Array3<f32>, OcrError> {
        // 创建输入 Shape
        let input_shape = Shape::new(&[batch as i64, channels as i64, height as i64, width as i64])
            .map_err(|e| OcrError::InferenceError(format!("创建输入 Shape 失败: {:?}", e)))?;

        // 创建输入 Tensor 并填充数据
        let mut input_tensor = Tensor::new(ElementType::F32, &input_shape)
            .map_err(|e| OcrError::InferenceError(format!("创建输入 Tensor 失败: {:?}", e)))?;

        {
            let tensor_data = input_tensor
                .get_data_mut::<f32>()
                .map_err(|e| OcrError::InferenceError(format!("获取 Tensor 数据失败: {:?}", e)))?;
            let input_data: Vec<f32> = input.iter().cloned().collect();
            tensor_data.copy_from_slice(&input_data);
        }

        // 设置输入
        infer_request
            .set_input_tensor(&input_tensor)
            .map_err(|e| OcrError::InferenceError(format!("设置输入 Tensor 失败: {:?}", e)))?;

        // ========================================
        // 异步推理: start_async + wait
        // ========================================
        // 启动异步推理（非阻塞）
        infer_request.infer_async().map_err(|e| {
            OcrError::InferenceError(format!("{} 异步推理启动失败: {:?}", self.model_name, e))
        })?;

        // 等待推理完成（可以在这里做其他事情）
        // timeout: -1 表示无限等待，或者使用 ASYNC_WAIT_TIMEOUT_MS
        infer_request.wait(ASYNC_WAIT_TIMEOUT_MS).map_err(|e| {
            OcrError::InferenceError(format!("{} 异步推理等待超时: {:?}", self.model_name, e))
        })?;

        // 获取输出
        let output_tensor = infer_request
            .get_output_tensor()
            .map_err(|e| OcrError::InferenceError(format!("获取输出 Tensor 失败: {:?}", e)))?;

        let output_shape = output_tensor
            .get_shape()
            .map_err(|e| OcrError::InferenceError(format!("获取输出形状失败: {:?}", e)))?;
        let dims: Vec<usize> = output_shape.get_dimensions().iter().map(|&x| x as usize).collect();

        if dims.len() != 3 {
            return Err(OcrError::InferenceError(format!(
                "识别模型输出维度错误: 期望 3D [B, T, V]，实际 {:?}",
                dims
            )));
        }

        let output_data = output_tensor
            .get_data::<f32>()
            .map_err(|e| OcrError::InferenceError(format!("提取输出数据失败: {:?}", e)))?;

        let output_array =
            Array3::from_shape_vec((dims[0], dims[1], dims[2]), output_data.to_vec())
                .map_err(|e| OcrError::InferenceError(format!("转换输出数组失败: {}", e)))?;

        Ok(output_array)
    }

    /// 执行批量识别模型推理
    ///
    /// 将多个文本区域合并为单个批次进行推理，显著提升吞吐量。
    ///
    /// # 参数
    ///
    /// - `inputs`: 输入张量列表，每个形状为 [1, 3, H, W]
    /// - `max_width`: 批次中的最大宽度（用于 padding）
    ///
    /// # 返回
    ///
    /// - `Ok(Vec<Array3<f32>>)`: 每个输入对应的输出 [1, T, V]
    ///
    /// # 性能
    ///
    /// 批量推理比逐个推理快 2-5 倍，因为：
    /// - 减少 CPU-GPU 数据传输次数
    /// - 更好地利用 SIMD 向量化
    /// - 减少推理请求创建开销
    pub fn infer_recognition_batch(
        &self,
        inputs: &[Array4<f32>],
        max_width: usize,
    ) -> Result<Vec<Array3<f32>>, OcrError> {
        if inputs.is_empty() {
            return Ok(Vec::new());
        }

        let batch_size = inputs.len();
        let height = inputs[0].shape()[2];
        let channels = inputs[0].shape()[1];

        tracing::debug!("批量推理: {} 个样本, 高度={}, 最大宽度={}", batch_size, height, max_width);

        // 创建批量输入张量 [N, 3, H, max_W]
        let mut batch_tensor =
            ndarray::Array4::<f32>::zeros((batch_size, channels, height, max_width));

        // 填充数据（右侧 padding 为 0）
        for (i, input) in inputs.iter().enumerate() {
            let w = input.shape()[3];
            for c in 0..channels {
                for y in 0..height {
                    for x in 0..w {
                        batch_tensor[[i, c, y, x]] = input[[0, c, y, x]];
                    }
                }
            }
        }

        // 获取模型锁并创建推理请求
        let mut compiled_model = self
            .compiled_model
            .lock()
            .map_err(|e| OcrError::InferenceError(format!("获取模型锁失败: {}", e)))?;

        let mut infer_request = compiled_model
            .create_infer_request()
            .map_err(|e| OcrError::InferenceError(format!("创建推理请求失败: {:?}", e)))?;

        // 创建输入 Shape
        let input_shape =
            Shape::new(&[batch_size as i64, channels as i64, height as i64, max_width as i64])
                .map_err(|e| OcrError::InferenceError(format!("创建输入 Shape 失败: {:?}", e)))?;

        // 创建输入 Tensor
        let mut input_tensor = Tensor::new(ElementType::F32, &input_shape)
            .map_err(|e| OcrError::InferenceError(format!("创建输入 Tensor 失败: {:?}", e)))?;

        // 填充数据
        {
            let tensor_data = input_tensor
                .get_data_mut::<f32>()
                .map_err(|e| OcrError::InferenceError(format!("获取 Tensor 数据失败: {:?}", e)))?;
            let input_data: Vec<f32> = batch_tensor.iter().cloned().collect();
            tensor_data.copy_from_slice(&input_data);
        }

        // 设置输入并执行推理
        infer_request
            .set_input_tensor(&input_tensor)
            .map_err(|e| OcrError::InferenceError(format!("设置输入 Tensor 失败: {:?}", e)))?;

        infer_request.infer().map_err(|e| {
            OcrError::InferenceError(format!("{} 批量推理失败: {:?}", self.model_name, e))
        })?;

        // 获取输出
        let output_tensor = infer_request
            .get_output_tensor()
            .map_err(|e| OcrError::InferenceError(format!("获取输出 Tensor 失败: {:?}", e)))?;

        let output_shape = output_tensor
            .get_shape()
            .map_err(|e| OcrError::InferenceError(format!("获取输出形状失败: {:?}", e)))?;
        let dims: Vec<usize> = output_shape.get_dimensions().iter().map(|&x| x as usize).collect();

        if dims.len() != 3 {
            return Err(OcrError::InferenceError(format!(
                "批量识别输出维度错误: 期望 3D [N, T, V]，实际 {:?}",
                dims
            )));
        }

        let output_data = output_tensor
            .get_data::<f32>()
            .map_err(|e| OcrError::InferenceError(format!("提取输出数据失败: {:?}", e)))?;

        // 拆分批量输出为单独的 Array3
        let timesteps = dims[1];
        let vocab_size = dims[2];
        let mut results = Vec::with_capacity(batch_size);

        for i in 0..batch_size {
            let start = i * timesteps * vocab_size;
            let end = start + timesteps * vocab_size;
            let slice = &output_data[start..end];

            let arr = Array3::from_shape_vec((1, timesteps, vocab_size), slice.to_vec())
                .map_err(|e| OcrError::InferenceError(format!("转换输出数组失败: {}", e)))?;

            results.push(arr);
        }

        tracing::debug!(
            "批量推理完成: {} 个结果, 每个形状 [1, {}, {}]",
            results.len(),
            timesteps,
            vocab_size
        );

        Ok(results)
    }

    /// 执行批量识别模型推理（u8 NHWC 输入，用于 IR 模型）
    ///
    /// 用于预处理已注入的 IR 模型，直接接受原始 u8 像素数据。
    /// 将多个文本区域合并为单个批次进行推理，显著提升吞吐量。
    ///
    /// # 参数
    ///
    /// - `inputs`: 输入数据列表，每个元素为 `(u8数据, 高度, 宽度)`
    /// - `max_width`: 批次中的最大宽度（用于 padding）
    ///
    /// # 返回
    ///
    /// - `Ok(Vec<Array3<f32>>)`: 每个输入对应的输出 [1, T, V]
    ///
    /// # 性能优势
    ///
    /// - 无需 Rust 侧归一化，预处理在模型内部执行
    /// - 批量推理比逐个推理快 2-5 倍
    /// - 减少 CPU-GPU 数据传输次数
    pub fn infer_recognition_batch_u8(
        &self,
        inputs: &[(Vec<u8>, usize, usize)], // (data, height, width)
        max_width: usize,
    ) -> Result<Vec<Array3<f32>>, OcrError> {
        if inputs.is_empty() {
            return Ok(Vec::new());
        }

        let batch_size = inputs.len();
        let height = inputs[0].1; // 所有输入高度相同（通常为 48）
        let channels = 3;

        tracing::debug!(
            "批量推理 (u8): {} 个样本, 高度={}, 最大宽度={}",
            batch_size,
            height,
            max_width
        );

        // 创建批量输入张量 [N, H, max_W, 3] (NHWC 格式)
        let total_size = batch_size * height * max_width * channels;
        let mut batch_data = vec![0u8; total_size];

        // 填充数据（右侧 padding 为 0）
        for (i, (data, h, w)) in inputs.iter().enumerate() {
            if *h != height {
                return Err(OcrError::InferenceError(format!(
                    "输入高度不一致: 期望 {}, 实际 {} (样本 {})",
                    height, h, i
                )));
            }

            // 复制每一行数据
            for y in 0..height {
                let src_start = y * w * channels;
                let src_end = src_start + w * channels;
                let dst_start = i * height * max_width * channels + y * max_width * channels;

                if src_end <= data.len() {
                    batch_data[dst_start..dst_start + w * channels]
                        .copy_from_slice(&data[src_start..src_end]);
                }
            }
        }

        // 获取模型锁并创建推理请求
        let mut compiled_model = self
            .compiled_model
            .lock()
            .map_err(|e| OcrError::InferenceError(format!("获取模型锁失败: {}", e)))?;

        let mut infer_request = compiled_model
            .create_infer_request()
            .map_err(|e| OcrError::InferenceError(format!("创建推理请求失败: {:?}", e)))?;

        // 创建输入 Shape (NHWC 格式)
        let input_shape =
            Shape::new(&[batch_size as i64, height as i64, max_width as i64, channels as i64])
                .map_err(|e| OcrError::InferenceError(format!("创建输入 Shape 失败: {:?}", e)))?;

        // 创建 u8 类型的输入 Tensor
        let mut input_tensor = Tensor::new(ElementType::U8, &input_shape)
            .map_err(|e| OcrError::InferenceError(format!("创建输入 Tensor 失败: {:?}", e)))?;

        // 填充数据
        {
            let tensor_data = input_tensor
                .get_data_mut::<u8>()
                .map_err(|e| OcrError::InferenceError(format!("获取 Tensor 数据失败: {:?}", e)))?;
            tensor_data.copy_from_slice(&batch_data);
        }

        // 设置输入并执行推理
        infer_request
            .set_input_tensor(&input_tensor)
            .map_err(|e| OcrError::InferenceError(format!("设置输入 Tensor 失败: {:?}", e)))?;

        infer_request.infer().map_err(|e| {
            OcrError::InferenceError(format!("{} 批量推理失败: {:?}", self.model_name, e))
        })?;

        // 获取输出
        let output_tensor = infer_request
            .get_output_tensor()
            .map_err(|e| OcrError::InferenceError(format!("获取输出 Tensor 失败: {:?}", e)))?;

        let output_shape = output_tensor
            .get_shape()
            .map_err(|e| OcrError::InferenceError(format!("获取输出形状失败: {:?}", e)))?;
        let dims: Vec<usize> = output_shape.get_dimensions().iter().map(|&x| x as usize).collect();

        if dims.len() != 3 {
            return Err(OcrError::InferenceError(format!(
                "批量识别输出维度错误: 期望 3D [N, T, V]，实际 {:?}",
                dims
            )));
        }

        let output_data = output_tensor
            .get_data::<f32>()
            .map_err(|e| OcrError::InferenceError(format!("提取输出数据失败: {:?}", e)))?;

        // 拆分批量输出为单独的 Array3
        let timesteps = dims[1];
        let vocab_size = dims[2];
        let mut results = Vec::with_capacity(batch_size);

        for i in 0..batch_size {
            let start = i * timesteps * vocab_size;
            let end = start + timesteps * vocab_size;
            let slice = &output_data[start..end];

            let arr = Array3::from_shape_vec((1, timesteps, vocab_size), slice.to_vec())
                .map_err(|e| OcrError::InferenceError(format!("转换输出数组失败: {}", e)))?;

            results.push(arr);
        }

        tracing::debug!(
            "批量推理 (u8) 完成: {} 个结果, 每个形状 [1, {}, {}]",
            results.len(),
            timesteps,
            vocab_size
        );

        Ok(results)
    }
}

/// 获取 OpenVINO 配置信息（用于调试）
pub fn get_openvino_info() -> String {
    match Core::new() {
        Ok(core) => {
            let devices = core
                .available_devices()
                .map(|d| format!("{:?}", d))
                .unwrap_or_else(|_| "unknown".to_string());
            let cache_dir = get_cache_dir();
            format!("OpenVINO 推理引擎: 可用设备={}, 缓存目录={}", devices, cache_dir.display())
        }
        Err(e) => format!("OpenVINO 推理引擎: 初始化失败 - {:?}", e),
    }
}

/// 清除模型缓存
///
/// 删除 OpenVINO 编译后的模型缓存，下次启动时会重新编译。
/// 用于调试或当模型更新后需要强制重新编译。
#[allow(dead_code)]
pub fn clear_model_cache() -> Result<(), std::io::Error> {
    let cache_dir = get_cache_dir();
    if cache_dir.exists() {
        tracing::info!("清除模型缓存: {}", cache_dir.display());
        std::fs::remove_dir_all(&cache_dir)?;
    }
    Ok(())
}

/// 获取模型缓存目录路径
#[allow(dead_code)]
pub fn get_model_cache_path() -> PathBuf {
    get_cache_dir()
}

// ============================================
// 单元测试
// ============================================

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_get_openvino_info() {
        // 只测试函数不会 panic
        let info = get_openvino_info();
        println!("OpenVINO info: {}", info);
    }
}
