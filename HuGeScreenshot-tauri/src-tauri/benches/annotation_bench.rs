/// 标注系统性能基准测试
///
/// 测试项目:
/// - 标注对象序列化
/// - Undo/Redo 栈操作
/// - 边界框计算
use criterion::{criterion_group, criterion_main, BenchmarkId, Criterion};
use serde::{Deserialize, Serialize};
use std::collections::VecDeque;
use std::hint::black_box as bb;

/// 坐标点
#[derive(Debug, Clone, Copy, Serialize, Deserialize)]
struct Point {
    x: f64,
    y: f64,
}

/// 标注样式
#[derive(Debug, Clone, Serialize, Deserialize)]
struct AnnotationStyle {
    stroke_color: String,
    stroke_width: f64,
    fill_color: String,
}

/// 标注对象
#[derive(Debug, Clone, Serialize, Deserialize)]
struct AnnotationObject {
    id: String,
    annotation_type: String,
    points: Vec<Point>,
    style: AnnotationStyle,
    text: Option<String>,
}

/// 标注命令
#[derive(Debug, Clone)]
struct AnnotationCommand {
    command_type: String,
    target_id: String,
    before: Option<AnnotationObject>,
    after: Option<AnnotationObject>,
}

/// 历史记录管理器
#[derive(Clone)]
struct AnnotationHistory {
    undo_stack: VecDeque<AnnotationCommand>,
    redo_stack: VecDeque<AnnotationCommand>,
    max_size: usize,
}

impl AnnotationHistory {
    fn new(max_size: usize) -> Self {
        Self {
            undo_stack: VecDeque::with_capacity(max_size),
            redo_stack: VecDeque::with_capacity(max_size),
            max_size,
        }
    }

    fn push(&mut self, command: AnnotationCommand) {
        if self.undo_stack.len() >= self.max_size {
            self.undo_stack.pop_front();
        }
        self.undo_stack.push_back(command);
        self.redo_stack.clear();
    }

    fn undo(&mut self) -> Option<AnnotationCommand> {
        if let Some(cmd) = self.undo_stack.pop_back() {
            self.redo_stack.push_back(cmd.clone());
            Some(cmd)
        } else {
            None
        }
    }

    fn redo(&mut self) -> Option<AnnotationCommand> {
        if let Some(cmd) = self.redo_stack.pop_back() {
            self.undo_stack.push_back(cmd.clone());
            Some(cmd)
        } else {
            None
        }
    }
}

/// 生成测试标注对象
fn create_test_annotation(id: &str, point_count: usize) -> AnnotationObject {
    AnnotationObject {
        id: id.to_string(),
        annotation_type: "rectangle".to_string(),
        points: (0..point_count)
            .map(|i| Point { x: i as f64 * 10.0, y: i as f64 * 10.0 })
            .collect(),
        style: AnnotationStyle {
            stroke_color: "#FF0000".to_string(),
            stroke_width: 2.0,
            fill_color: "transparent".to_string(),
        },
        text: None,
    }
}

/// 计算边界框
fn calculate_bounds(points: &[Point]) -> (Point, Point) {
    if points.is_empty() {
        return (Point { x: 0.0, y: 0.0 }, Point { x: 0.0, y: 0.0 });
    }

    let mut min_x = f64::MAX;
    let mut min_y = f64::MAX;
    let mut max_x = f64::MIN;
    let mut max_y = f64::MIN;

    for p in points {
        min_x = min_x.min(p.x);
        min_y = min_y.min(p.y);
        max_x = max_x.max(p.x);
        max_y = max_y.max(p.y);
    }

    (Point { x: min_x, y: min_y }, Point { x: max_x, y: max_y })
}

/// 标注对象序列化基准测试
fn bench_annotation_serialize(c: &mut Criterion) {
    let mut group = c.benchmark_group("annotation_serialize");

    let point_counts = [4, 20, 100];

    for count in point_counts {
        let annotation = create_test_annotation("test", count);

        group.bench_with_input(BenchmarkId::new("serialize", count), &annotation, |b, ann| {
            b.iter(|| serde_json::to_string(bb(ann)))
        });
    }

    group.finish();
}

/// Undo/Redo 栈操作基准测试
fn bench_history_operations(c: &mut Criterion) {
    let mut group = c.benchmark_group("history_operations");

    fn touch_command(cmd: &AnnotationCommand) -> usize {
        cmd.command_type.len()
            + cmd.target_id.len()
            + cmd.before.as_ref().map_or(0, |ann| ann.points.len())
            + cmd.after.as_ref().map_or(0, |ann| ann.points.len())
    }

    // Push 操作
    group.bench_function("push_50", |b| {
        b.iter(|| {
            let mut history = AnnotationHistory::new(50);
            for i in 0..50 {
                let cmd = AnnotationCommand {
                    command_type: "add".to_string(),
                    target_id: format!("ann-{}", i),
                    before: None,
                    after: Some(create_test_annotation(&format!("ann-{}", i), 4)),
                };
                history.push(cmd);
            }
            history
        })
    });

    // Undo 操作
    group.bench_function("undo_50", |b| {
        let mut history = AnnotationHistory::new(50);
        for i in 0..50 {
            let cmd = AnnotationCommand {
                command_type: "add".to_string(),
                target_id: format!("ann-{}", i),
                before: None,
                after: Some(create_test_annotation(&format!("ann-{}", i), 4)),
            };
            history.push(cmd);
        }

        b.iter(|| {
            let mut h = history.clone();
            for _ in 0..50 {
                if let Some(cmd) = h.undo() {
                    bb(touch_command(&cmd));
                }
            }
        })
    });

    // Redo 操作
    group.bench_function("redo_50", |b| {
        let mut history = AnnotationHistory::new(50);
        for i in 0..50 {
            let cmd = AnnotationCommand {
                command_type: "add".to_string(),
                target_id: format!("ann-{}", i),
                before: None,
                after: Some(create_test_annotation(&format!("ann-{}", i), 4)),
            };
            history.push(cmd);
        }
        for _ in 0..50 {
            let _ = history.undo();
        }

        b.iter(|| {
            let mut h = history.clone();
            for _ in 0..50 {
                if let Some(cmd) = h.redo() {
                    bb(touch_command(&cmd));
                }
            }
        })
    });

    group.finish();
}

/// 边界框计算基准测试
fn bench_bounds_calculation(c: &mut Criterion) {
    let mut group = c.benchmark_group("bounds_calculation");

    let point_counts = [4, 50, 200];

    for count in point_counts {
        let points: Vec<Point> = (0..count)
            .map(|i| Point { x: (i as f64).sin() * 100.0, y: (i as f64).cos() * 100.0 })
            .collect();

        group.bench_with_input(BenchmarkId::new("calculate", count), &points, |b, pts| {
            b.iter(|| calculate_bounds(bb(pts)))
        });
    }

    group.finish();
}

criterion_group!(
    benches,
    bench_annotation_serialize,
    bench_history_operations,
    bench_bounds_calculation,
);

criterion_main!(benches);
