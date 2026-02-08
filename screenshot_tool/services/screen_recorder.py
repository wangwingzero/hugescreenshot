# -*- coding: utf-8 -*-
"""
录屏服务模块

使用 DXcam 进行高性能屏幕捕获，PyAV 进行 H.264 编码。

Feature: screen-recording
"""

import os
import time
import threading
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional, Tuple, Callable

from PySide6.QtCore import QObject, Signal, QThread

# 尝试导入录屏相关库
try:
    import dxcam
    DXCAM_AVAILABLE = True
except ImportError:
    DXCAM_AVAILABLE = False
    dxcam = None

try:
    import av
    AV_AVAILABLE = True
except ImportError:
    AV_AVAILABLE = False
    av = None

try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False
    np = None


class RecordingState(Enum):
    """录制状态"""
    IDLE = "idle"           # 空闲
    RECORDING = "recording" # 录制中
    PAUSED = "paused"       # 暂停
    STOPPING = "stopping"   # 正在停止


@dataclass
class RecordingResult:
    """录制结果"""
    success: bool
    file_path: str = ""
    duration_seconds: float = 0.0
    file_size_bytes: int = 0
    error: str = ""

    @classmethod
    def success_result(cls, file_path: str, duration: float, size: int) -> "RecordingResult":
        """创建成功结果"""
        return cls(
            success=True,
            file_path=file_path,
            duration_seconds=duration,
            file_size_bytes=size,
        )

    @classmethod
    def error_result(cls, error_msg: str) -> "RecordingResult":
        """创建错误结果"""
        return cls(success=False, error=error_msg)


class ScreenRecorderWorker(QThread):
    """录屏后台工作线程

    使用 DXcam 捕获屏幕，PyAV 编码为 H.264 视频。
    """

    # 信号
    frame_captured = Signal(int)           # 已捕获帧数
    recording_stopped = Signal(object)     # RecordingResult
    error_occurred = Signal(str)           # 错误信息

    def __init__(
        self,
        output_path: str,
        region: Optional[Tuple[int, int, int, int]] = None,  # (left, top, right, bottom)
        fps: int = 30,
        bitrate: int = 5_000_000,
        show_cursor: bool = True,
        monitor_index: int = 0,
    ):
        super().__init__()
        self._output_path = output_path
        self._region = region  # None 表示全屏
        self._fps = fps
        self._bitrate = bitrate
        self._show_cursor = show_cursor
        self._monitor_index = monitor_index

        self._should_stop = False
        self._is_paused = False
        self._frame_count = 0
        self._start_time = 0.0
        self._pause_duration = 0.0
        self._pause_start = 0.0

        self._lock = threading.Lock()

    def run(self):
        """录制主循环"""
        if not DXCAM_AVAILABLE:
            self.error_occurred.emit("dxcam 库未安装，请运行: pip install dxcam")
            self.recording_stopped.emit(RecordingResult.error_result("dxcam 库未安装"))
            return

        if not AV_AVAILABLE:
            self.error_occurred.emit("av 库未安装，请运行: pip install av")
            self.recording_stopped.emit(RecordingResult.error_result("av 库未安装"))
            return

        camera = None
        container = None

        try:
            # 初始化 DXcam
            camera = dxcam.create(output_idx=self._monitor_index, output_color="BGR")
            if camera is None:
                raise RuntimeError("无法创建 DXcam 捕获器，可能不支持当前显示器")

            # 获取屏幕尺寸
            if self._region:
                left, top, right, bottom = self._region
                width = right - left
                height = bottom - top
            else:
                # 全屏
                width = camera.width
                height = camera.height

            # 确保宽高是偶数（H.264 要求）
            width = width - (width % 2)
            height = height - (height % 2)

            # 开始捕获
            if self._region:
                camera.start(target_fps=self._fps, region=self._region)
            else:
                camera.start(target_fps=self._fps)

            # 初始化 PyAV 输出
            container = av.open(self._output_path, mode='w')
            stream = container.add_stream('libx264', rate=self._fps)
            stream.width = width
            stream.height = height
            stream.pix_fmt = 'yuv420p'
            stream.options = {
                'crf': '23',
                'preset': 'fast',
                'tune': 'zerolatency',
            }

            self._start_time = time.time()
            frame_interval = 1.0 / self._fps

            while not self._should_stop:
                loop_start = time.time()

                # 暂停处理
                with self._lock:
                    if self._is_paused:
                        if self._pause_start == 0:
                            self._pause_start = time.time()
                        time.sleep(0.01)
                        continue
                    elif self._pause_start > 0:
                        self._pause_duration += time.time() - self._pause_start
                        self._pause_start = 0

                # 获取帧
                frame = camera.get_latest_frame()
                if frame is not None:
                    # 裁剪到目标尺寸（确保偶数）
                    frame = frame[:height, :width]

                    # 编码并写入
                    video_frame = av.VideoFrame.from_ndarray(frame, format='bgr24')
                    video_frame.pts = self._frame_count

                    for packet in stream.encode(video_frame):
                        container.mux(packet)

                    self._frame_count += 1

                    # 每秒发送一次进度信号
                    if self._frame_count % self._fps == 0:
                        self.frame_captured.emit(self._frame_count)

                # 控制帧率
                elapsed = time.time() - loop_start
                if elapsed < frame_interval:
                    time.sleep(frame_interval - elapsed)

            # 刷新编码器
            for packet in stream.encode():
                container.mux(packet)

            container.close()
            container = None
            camera.stop()
            camera = None

            # 计算实际时长
            actual_duration = (time.time() - self._start_time - self._pause_duration)

            # 获取文件大小
            file_size = os.path.getsize(self._output_path) if os.path.exists(self._output_path) else 0

            # 返回结果
            result = RecordingResult.success_result(
                file_path=self._output_path,
                duration=actual_duration,
                size=file_size,
            )
            self.recording_stopped.emit(result)

        except Exception as e:
            error_msg = f"录屏失败: {str(e)}"
            self.error_occurred.emit(error_msg)
            self.recording_stopped.emit(RecordingResult.error_result(error_msg))

        finally:
            # 清理资源
            if container is not None:
                try:
                    container.close()
                except Exception:
                    pass
            if camera is not None:
                try:
                    camera.stop()
                    del camera  # 完全释放 DirectX 资源
                except Exception:
                    pass

    def pause(self):
        """暂停录制"""
        with self._lock:
            self._is_paused = True

    def resume(self):
        """继续录制"""
        with self._lock:
            self._is_paused = False

    def stop(self):
        """停止录制"""
        self._should_stop = True

    @property
    def is_paused(self) -> bool:
        """是否暂停"""
        with self._lock:
            return self._is_paused


class ScreenRecorder(QObject):
    """录屏服务主类

    提供高层 API 用于控制录屏。
    """

    # 信号
    state_changed = Signal(object)         # RecordingState
    progress_updated = Signal(int, float)  # 帧数, 时长秒数
    recording_finished = Signal(object)    # RecordingResult

    def __init__(self, config: "RecordingConfig" = None):
        super().__init__()
        self._config = config
        self._state = RecordingState.IDLE
        self._worker: Optional[ScreenRecorderWorker] = None
        self._current_region: Optional[Tuple[int, int, int, int]] = None
        self._current_output_path: str = ""

    @property
    def state(self) -> RecordingState:
        """获取当前状态"""
        return self._state

    @property
    def is_recording(self) -> bool:
        """是否正在录制"""
        return self._state in (RecordingState.RECORDING, RecordingState.PAUSED)

    @property
    def current_output_path(self) -> str:
        """当前输出文件路径"""
        return self._current_output_path

    @staticmethod
    def check_dependencies() -> Tuple[bool, str]:
        """检查依赖是否可用

        Returns:
            (是否可用, 错误信息)
        """
        missing = []
        if not DXCAM_AVAILABLE:
            missing.append("dxcam")
        if not AV_AVAILABLE:
            missing.append("av")
        if not NUMPY_AVAILABLE:
            missing.append("numpy")

        if missing:
            return False, f"缺少依赖: {', '.join(missing)}，请运行: pip install {' '.join(missing)}"
        return True, ""

    def start_recording(
        self,
        region: Optional[Tuple[int, int, int, int]] = None,
        output_path: Optional[str] = None,
        monitor_index: int = 0,
    ) -> bool:
        """开始录制

        Args:
            region: 录制区域 (left, top, right, bottom)，None 表示全屏
            output_path: 输出文件路径，None 则自动生成
            monitor_index: 显示器索引

        Returns:
            是否成功启动
        """
        if self._state != RecordingState.IDLE:
            return False

        # 检查依赖
        available, error = self.check_dependencies()
        if not available:
            self.recording_finished.emit(RecordingResult.error_result(error))
            return False

        # 生成输出路径
        if output_path is None:
            if self._config:
                save_dir = self._config.get_save_path()
            else:
                save_dir = os.path.join(os.path.expanduser("~"), "Videos", "Recordings")
            os.makedirs(save_dir, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = os.path.join(save_dir, f"录屏_{timestamp}.mp4")

        self._current_output_path = output_path
        self._current_region = region

        # 获取配置参数
        fps = self._config.fps if self._config else 30
        bitrate = self._config.get_bitrate() if self._config else 5_000_000
        show_cursor = self._config.show_cursor if self._config else True

        # 创建工作线程
        self._worker = ScreenRecorderWorker(
            output_path=output_path,
            region=region,
            fps=fps,
            bitrate=bitrate,
            show_cursor=show_cursor,
            monitor_index=monitor_index,
        )

        self._worker.frame_captured.connect(self._on_frame_captured)
        self._worker.recording_stopped.connect(self._on_recording_stopped)
        self._worker.error_occurred.connect(self._on_error)

        self._worker.start()
        self._state = RecordingState.RECORDING
        self.state_changed.emit(self._state)

        return True

    def pause_recording(self):
        """暂停录制"""
        if self._state == RecordingState.RECORDING and self._worker:
            self._worker.pause()
            self._state = RecordingState.PAUSED
            self.state_changed.emit(self._state)

    def resume_recording(self):
        """继续录制"""
        if self._state == RecordingState.PAUSED and self._worker:
            self._worker.resume()
            self._state = RecordingState.RECORDING
            self.state_changed.emit(self._state)

    def toggle_pause(self):
        """切换暂停状态"""
        if self._state == RecordingState.RECORDING:
            self.pause_recording()
        elif self._state == RecordingState.PAUSED:
            self.resume_recording()

    def stop_recording(self):
        """停止录制"""
        if self._worker and self._state in (RecordingState.RECORDING, RecordingState.PAUSED):
            self._state = RecordingState.STOPPING
            self.state_changed.emit(self._state)
            self._worker.stop()

    def cancel_recording(self):
        """取消录制并删除文件"""
        output_path = self._current_output_path
        self.stop_recording()

        # 等待线程结束
        if self._worker:
            self._worker.wait(5000)  # 最多等待 5 秒

        # 删除文件
        if output_path and os.path.exists(output_path):
            try:
                os.remove(output_path)
            except Exception:
                pass

    def _on_frame_captured(self, frame_count: int):
        """帧捕获回调"""
        fps = self._config.fps if self._config else 30
        duration = frame_count / fps
        self.progress_updated.emit(frame_count, duration)

    def _on_recording_stopped(self, result: RecordingResult):
        """录制停止回调"""
        self._state = RecordingState.IDLE
        self.state_changed.emit(self._state)
        self.recording_finished.emit(result)
        self._worker = None

    def _on_error(self, error: str):
        """错误回调"""
        print(f"[ScreenRecorder] 错误: {error}")


def test_recording():
    """测试录屏功能"""
    from PySide6.QtWidgets import QApplication
    import sys

    app = QApplication(sys.argv)

    # 检查依赖
    available, error = ScreenRecorder.check_dependencies()
    if not available:
        print(f"错误: {error}")
        return

    recorder = ScreenRecorder()

    def on_progress(frames, duration):
        print(f"录制中: {frames} 帧, {duration:.1f} 秒")

    def on_finished(result):
        if result.success:
            print(f"录制完成: {result.file_path}")
            print(f"时长: {result.duration_seconds:.1f} 秒")
            print(f"大小: {result.file_size_bytes / 1024 / 1024:.2f} MB")
        else:
            print(f"录制失败: {result.error}")
        app.quit()

    recorder.progress_updated.connect(on_progress)
    recorder.recording_finished.connect(on_finished)

    # 开始录制（5秒后停止）
    recorder.start_recording()
    print("开始录制...")

    from PySide6.QtCore import QTimer
    QTimer.singleShot(5000, recorder.stop_recording)

    app.exec()


if __name__ == "__main__":
    test_recording()
