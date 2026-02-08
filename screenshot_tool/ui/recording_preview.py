# -*- coding: utf-8 -*-
"""
录制预览对话框模块

录制完成后显示预览，支持播放、保存、复制等操作。

Feature: screen-recording
"""

import os
import shutil
import subprocess
from typing import Optional

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFileDialog, QMessageBox, QSizePolicy, QWidget, QApplication,
    QSlider
)
from PySide6.QtCore import Qt, Signal, QUrl, QSize

# 尝试导入多媒体模块
try:
    from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
    from PySide6.QtMultimediaWidgets import QVideoWidget
    MULTIMEDIA_AVAILABLE = True
except ImportError:
    MULTIMEDIA_AVAILABLE = False


class RecordingPreviewDialog(QDialog):
    """录制完成预览对话框

    显示录制的视频预览，支持播放、另存为、复制路径、删除等操作。
    """

    # 信号
    save_requested = Signal(str)      # 另存为路径
    delete_requested = Signal()        # 删除录制
    open_folder_requested = Signal()   # 打开所在文件夹

    def __init__(self, file_path: str, duration: float, file_size: int, parent=None):
        super().__init__(parent)
        self._file_path = file_path
        self._duration = duration
        self._file_size = file_size
        self._player: Optional[QMediaPlayer] = None
        self._slider_being_dragged = False  # 标记是否正在拖动滑块
        self._setup_ui()

    def _setup_ui(self):
        """设置 UI"""
        self.setWindowTitle("录屏完成")
        self.setMinimumSize(640, 520)
        self.resize(720, 560)
        self.setWindowFlags(
            Qt.WindowType.Dialog |
            Qt.WindowType.WindowCloseButtonHint |
            Qt.WindowType.WindowTitleHint
        )

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # 视频预览区域
        if MULTIMEDIA_AVAILABLE:
            self._video_widget = QVideoWidget()
            self._video_widget.setMinimumSize(640, 360)
            self._video_widget.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Expanding
            )
            layout.addWidget(self._video_widget)

            # 创建播放器
            self._audio_output = QAudioOutput()
            self._player = QMediaPlayer()
            self._player.setAudioOutput(self._audio_output)
            self._player.setVideoOutput(self._video_widget)
            self._player.setSource(QUrl.fromLocalFile(self._file_path))
        else:
            # 多媒体不可用时显示占位符
            placeholder = QLabel("视频预览不可用\n（缺少 Qt 多媒体模块）")
            placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
            placeholder.setMinimumSize(640, 360)
            placeholder.setStyleSheet("""
                QLabel {
                    background-color: #2a2a2a;
                    color: #888;
                    font-size: 14px;
                    border-radius: 8px;
                }
            """)
            layout.addWidget(placeholder)

        # 播放控制
        if MULTIMEDIA_AVAILABLE:
            control_layout = QHBoxLayout()
            control_layout.setSpacing(8)

            self._play_btn = QPushButton("▶ 播放")
            self._play_btn.setFixedWidth(80)
            self._play_btn.clicked.connect(self._toggle_play)
            control_layout.addWidget(self._play_btn)

            self._progress_label = QLabel("00:00 / 00:00")
            self._progress_label.setStyleSheet("color: #888;")
            self._progress_label.setFixedWidth(100)
            control_layout.addWidget(self._progress_label)

            control_layout.addStretch()
            layout.addLayout(control_layout)

            # 时间轴滑块
            slider_layout = QHBoxLayout()
            slider_layout.setSpacing(8)
            
            self._time_slider = QSlider(Qt.Orientation.Horizontal)
            self._time_slider.setRange(0, int(self._duration * 1000))  # 毫秒
            self._time_slider.setValue(0)
            self._time_slider.setStyleSheet("""
                QSlider::groove:horizontal {
                    border: 1px solid #444;
                    height: 6px;
                    background: #333;
                    border-radius: 3px;
                }
                QSlider::handle:horizontal {
                    background: #4A90D9;
                    border: none;
                    width: 14px;
                    height: 14px;
                    margin: -4px 0;
                    border-radius: 7px;
                }
                QSlider::handle:horizontal:hover {
                    background: #5AA0E9;
                }
                QSlider::sub-page:horizontal {
                    background: #4A90D9;
                    border-radius: 3px;
                }
            """)
            self._time_slider.sliderPressed.connect(self._on_slider_pressed)
            self._time_slider.sliderReleased.connect(self._on_slider_released)
            self._time_slider.sliderMoved.connect(self._on_slider_moved)
            slider_layout.addWidget(self._time_slider)
            
            layout.addLayout(slider_layout)

            # 播放器信号连接
            self._player.playbackStateChanged.connect(self._on_playback_state_changed)
            self._player.positionChanged.connect(self._on_position_changed)
            self._player.durationChanged.connect(self._on_duration_changed)

        # 信息显示
        info_layout = QHBoxLayout()

        # 文件路径
        path_label = QLabel(f"📁 {self._file_path}")
        path_label.setStyleSheet("color: #888; font-size: 11px;")
        path_label.setWordWrap(True)
        info_layout.addWidget(path_label, 1)

        # 时长和大小
        duration_str = self._format_duration(self._duration)
        size_str = self._format_size(self._file_size)
        stats_label = QLabel(f"⏱ {duration_str}  |  📦 {size_str}")
        stats_label.setStyleSheet("color: #888; font-size: 11px;")
        info_layout.addWidget(stats_label)

        layout.addLayout(info_layout)

        # 分隔线
        sep = QWidget()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background-color: #444;")
        layout.addWidget(sep)

        # 操作按钮
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        # 打开文件夹
        open_folder_btn = QPushButton("📂 打开文件夹")
        open_folder_btn.clicked.connect(self._on_open_folder)
        btn_layout.addWidget(open_folder_btn)

        # 复制视频（复制文件到剪贴板）
        copy_video_btn = QPushButton("📋 复制视频")
        copy_video_btn.setToolTip("复制视频文件到剪贴板，可直接粘贴到其他应用")
        copy_video_btn.clicked.connect(self._on_copy_video)
        btn_layout.addWidget(copy_video_btn)

        # 另存为
        save_as_btn = QPushButton("💾 另存为")
        save_as_btn.clicked.connect(self._on_save_as)
        btn_layout.addWidget(save_as_btn)

        # 删除
        delete_btn = QPushButton("🗑 删除")
        delete_btn.setStyleSheet("""
            QPushButton {
                color: #ff6666;
            }
            QPushButton:hover {
                color: #ff4444;
            }
        """)
        delete_btn.clicked.connect(self._on_delete)
        btn_layout.addWidget(delete_btn)

        btn_layout.addStretch()

        # 关闭按钮
        close_btn = QPushButton("关闭")
        close_btn.setDefault(True)
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)

        layout.addLayout(btn_layout)

    def _format_duration(self, seconds: float) -> str:
        """格式化时长"""
        minutes = int(seconds) // 60
        secs = int(seconds) % 60
        return f"{minutes:02d}:{secs:02d}"

    def _format_size(self, size_bytes: int) -> str:
        """格式化文件大小"""
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / 1024 / 1024:.1f} MB"
        else:
            return f"{size_bytes / 1024 / 1024 / 1024:.2f} GB"

    def _toggle_play(self):
        """切换播放/暂停"""
        if not self._player:
            return

        if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._player.pause()
        else:
            self._player.play()

    def _on_playback_state_changed(self, state):
        """播放状态变化"""
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self._play_btn.setText("⏸ 暂停")
        else:
            self._play_btn.setText("▶ 播放")

    def _on_position_changed(self, position):
        """播放位置变化"""
        current = self._format_duration(position / 1000)
        total = self._format_duration(self._duration)
        self._progress_label.setText(f"{current} / {total}")
        
        # 更新滑块位置（如果不是正在拖动）
        if not self._slider_being_dragged:
            self._time_slider.setValue(position)

    def _on_duration_changed(self, duration):
        """视频时长变化（从媒体文件读取）"""
        if duration > 0:
            self._time_slider.setRange(0, duration)
            self._duration = duration / 1000  # 更新时长（秒）

    def _on_slider_pressed(self):
        """滑块按下"""
        self._slider_being_dragged = True

    def _on_slider_released(self):
        """滑块释放"""
        self._slider_being_dragged = False
        if self._player:
            self._player.setPosition(self._time_slider.value())

    def _on_slider_moved(self, position):
        """滑块拖动"""
        # 更新时间显示
        current = self._format_duration(position / 1000)
        total = self._format_duration(self._duration)
        self._progress_label.setText(f"{current} / {total}")

    def _on_open_folder(self):
        """打开所在文件夹"""
        folder = os.path.dirname(self._file_path)
        if os.path.exists(folder):
            # Windows: 选中文件
            if os.name == 'nt':
                subprocess.run(['explorer', '/select,', self._file_path], check=False)
            else:
                subprocess.run(['xdg-open', folder], check=False)
        self.open_folder_requested.emit()

    def _on_copy_video(self):
        """复制视频文件到剪贴板"""
        if not os.path.exists(self._file_path):
            QMessageBox.warning(self, "哎呀 😅", "视频文件跑丢了 🏃")
            return

        try:
            # Windows: 使用 QMimeData 复制文件到剪贴板
            from PySide6.QtCore import QMimeData, QUrl
            
            clipboard = QApplication.clipboard()
            mime_data = QMimeData()
            
            # 设置文件 URL 列表
            file_url = QUrl.fromLocalFile(self._file_path)
            mime_data.setUrls([file_url])
            
            clipboard.setMimeData(mime_data)
            
            QMessageBox.information(self, "搞定！📋", "视频已偷偷塞进剪贴板，随时粘贴！")
            
        except Exception as e:
            QMessageBox.warning(self, "哎呀 😅", f"复制失败了：{str(e)}")

    def _on_save_as(self):
        """另存为"""
        # 获取原文件名
        original_name = os.path.basename(self._file_path)
        default_name = original_name

        # 打开保存对话框
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "另存为",
            default_name,
            "MP4 视频 (*.mp4);;所有文件 (*.*)"
        )

        if file_path:
            try:
                # 如果目标路径与源路径相同，跳过
                if os.path.abspath(file_path) == os.path.abspath(self._file_path):
                    return

                # 复制文件
                shutil.copy2(self._file_path, file_path)
                QMessageBox.information(self, "保存成功！💾", f"宝贝已存好：\n{file_path}")
                self.save_requested.emit(file_path)

            except Exception as e:
                QMessageBox.warning(self, "哎呀 😅", f"保存失败了：{str(e)}")

    def _on_delete(self):
        """删除录制"""
        reply = QMessageBox.question(
            self,
            "确定要删除吗？🗑️",
            f"真的要删掉这个录屏吗？\n\n{self._file_path}\n\n删了就找不回来了哦～",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            try:
                # 停止播放
                if self._player:
                    self._player.stop()
                    self._player.setSource(QUrl())

                # 删除文件
                if os.path.exists(self._file_path):
                    os.remove(self._file_path)

                self.delete_requested.emit()
                self.accept()

            except Exception as e:
                QMessageBox.warning(self, "哎呀 😅", f"删除失败了：{str(e)}")

    def closeEvent(self, event):
        """关闭事件"""
        # 停止播放
        if self._player:
            self._player.stop()
        super().closeEvent(event)


def show_recording_preview(file_path: str, duration: float, file_size: int, parent=None) -> bool:
    """显示录制预览对话框

    Args:
        file_path: 视频文件路径
        duration: 时长（秒）
        file_size: 文件大小（字节）
        parent: 父窗口

    Returns:
        用户是否点击了关闭（而非删除）
    """
    dialog = RecordingPreviewDialog(file_path, duration, file_size, parent)
    result = dialog.exec()
    return result == QDialog.DialogCode.Accepted


def test_preview():
    """测试预览对话框"""
    import sys
    app = QApplication(sys.argv)

    # 使用一个测试文件路径
    test_path = os.path.join(os.path.expanduser("~"), "Videos", "test.mp4")

    dialog = RecordingPreviewDialog(
        file_path=test_path,
        duration=125.5,
        file_size=15 * 1024 * 1024,
    )
    dialog.exec()


if __name__ == "__main__":
    test_preview()
