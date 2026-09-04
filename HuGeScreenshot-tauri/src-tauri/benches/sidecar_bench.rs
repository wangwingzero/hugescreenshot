/// Sidecar 通信性能基准测试
///
/// 测试项目:
/// - JSON 序列化/反序列化
/// - 请求/响应往返时间模拟
/// - 批量请求处理
use criterion::{criterion_group, criterion_main, BenchmarkId, Criterion};
use serde::{Deserialize, Serialize};
use std::hint::black_box as bb;

/// Sidecar 请求结构
#[derive(Debug, Clone, Serialize, Deserialize)]
struct SidecarRequest {
    id: String,
    service: String,
    method: String,
    params: serde_json::Value,
}

/// Sidecar 响应结构
#[derive(Debug, Clone, Serialize, Deserialize)]
struct SidecarResponse {
    id: String,
    success: bool,
    result: Option<serde_json::Value>,
    error: Option<String>,
}

/// 生成测试请求
fn create_test_request(id: &str) -> SidecarRequest {
    SidecarRequest {
        id: id.to_string(),
        service: "ocr".to_string(),
        method: "recognize".to_string(),
        params: serde_json::json!({
            "image_path": "C:/Users/test/AppData/Local/Temp/test.png"
        }),
    }
}

/// 生成测试响应
fn create_test_response(id: &str) -> SidecarResponse {
    SidecarResponse {
        id: id.to_string(),
        success: true,
        result: Some(serde_json::json!({
            "text": "Hello, World!\n你好，世界！",
            "boxes": [
                {"text": "Hello", "confidence": 0.98, "box": [[0,0], [50,0], [50,20], [0,20]]},
                {"text": "World", "confidence": 0.95, "box": [[55,0], [100,0], [100,20], [55,20]]}
            ],
            "elapse": 0.234
        })),
        error: None,
    }
}

/// JSON 序列化基准测试
fn bench_json_serialize(c: &mut Criterion) {
    let mut group = c.benchmark_group("json_serialize");

    let request = create_test_request("test-001");
    let response = create_test_response("test-001");

    group.bench_function("request", |b| b.iter(|| serde_json::to_string(bb(&request))));

    group.bench_function("response", |b| b.iter(|| serde_json::to_string(bb(&response))));

    group.finish();
}

/// JSON 反序列化基准测试
fn bench_json_deserialize(c: &mut Criterion) {
    let mut group = c.benchmark_group("json_deserialize");

    let request_json = serde_json::to_string(&create_test_request("test-001")).unwrap();
    let response_json = serde_json::to_string(&create_test_response("test-001")).unwrap();

    group.bench_function("request", |b| {
        b.iter(|| serde_json::from_str::<SidecarRequest>(bb(&request_json)))
    });

    group.bench_function("response", |b| {
        b.iter(|| serde_json::from_str::<SidecarResponse>(bb(&response_json)))
    });

    group.finish();
}

/// 批量请求处理基准测试
fn bench_batch_requests(c: &mut Criterion) {
    let mut group = c.benchmark_group("batch_requests");

    let batch_sizes = [10, 50, 100];

    for size in batch_sizes {
        let requests: Vec<SidecarRequest> =
            (0..size).map(|i| create_test_request(&format!("req-{}", i))).collect();

        group.bench_with_input(BenchmarkId::new("serialize_batch", size), &requests, |b, reqs| {
            b.iter(|| reqs.iter().map(|r| serde_json::to_string(r).unwrap()).collect::<Vec<_>>())
        });
    }

    group.finish();
}

criterion_group!(benches, bench_json_serialize, bench_json_deserialize, bench_batch_requests,);

criterion_main!(benches);
