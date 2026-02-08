# =====================================================
# QSS 缓存管理器 - QSS Cache Manager
# =====================================================

"""
QSS 缓存管理器 - 极致性能优化

Feature: extreme-performance-optimization
Requirements: 5.1, 5.2, 5.4

优化策略：
1. 预编译所有样式表为单一样式表
2. 使用哈希键缓存解析结果
3. 避免运行时动态生成 QSS
4. 使用简单选择器（类名）而非复杂选择器链
"""

from typing import Dict, Optional, Callable


class QSSCacheManager:
    """QSS 缓存管理器
    
    单例模式，管理全局 QSS 样式缓存。
    
    Feature: extreme-performance-optimization
    Requirements: 5.1, 5.2, 5.4
    
    使用方法：
    ```python
    # 获取预编译的全局样式表
    stylesheet = QSSCacheManager.instance().get_compiled_stylesheet()
    app.setStyleSheet(stylesheet)
    
    # 获取缓存的组件样式
    button_style = QSSCacheManager.instance().get_cached_style(
        "primary_button",
        lambda: generate_button_style()
    )
    ```
    """
    
    _instance: Optional['QSSCacheManager'] = None
    _cache: Dict[str, str] = {}
    _compiled_stylesheet: Optional[str] = None
    
    def __new__(cls) -> 'QSSCacheManager':
        """确保单例模式"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._cache = {}
            cls._instance._compiled_stylesheet = None
        return cls._instance
    
    @classmethod
    def instance(cls) -> 'QSSCacheManager':
        """获取单例实例
        
        Returns:
            QSSCacheManager 单例实例
        """
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def get_compiled_stylesheet(self) -> str:
        """获取预编译的全局样式表
        
        Requirements: 5.1 - 使用单一预编译样式表
        
        Returns:
            预编译的全局 QSS 样式表字符串
        """
        if self._compiled_stylesheet is None:
            self._compiled_stylesheet = self._compile_all_styles()
        return self._compiled_stylesheet
    
    def _compile_all_styles(self) -> str:
        """编译所有样式为单一样式表
        
        Requirements: 5.1, 5.5 - 使用简单选择器
        
        Returns:
            编译后的完整 QSS 样式表
        """
        # 延迟导入避免循环依赖
        from screenshot_tool.ui.styles import (
            COLORS, FONT_FAMILY, SCROLLBAR_STYLE, MENU_STYLE
        )
        
        # 预编译的全局样式表
        # 使用简单选择器（类名）而非复杂选择器链
        return f"""
            /* 全局基础样式 */
            QMainWindow {{
                background-color: {COLORS['bg']};
            }}
            QWidget {{
                font-family: {FONT_FAMILY};
            }}
            
            /* 滚动条样式 */
            {SCROLLBAR_STYLE}
            
            /* 菜单样式 */
            {MENU_STYLE}
        """
    
    def get_cached_style(self, key: str, generator: Callable[[], str]) -> str:
        """获取缓存的样式，不存在则生成并缓存
        
        Requirements: 5.2, 5.4 - 避免运行时动态生成，缓存解析结果
        
        Args:
            key: 样式缓存键
            generator: 样式生成函数，仅在缓存未命中时调用
            
        Returns:
            缓存的或新生成的 QSS 样式字符串
        """
        if key not in self._cache:
            self._cache[key] = generator()
        return self._cache[key]
    
    def has_cached_style(self, key: str) -> bool:
        """检查样式是否已缓存
        
        Args:
            key: 样式缓存键
            
        Returns:
            True 如果样式已缓存，否则 False
        """
        return key in self._cache
    
    def set_cached_style(self, key: str, style: str) -> None:
        """直接设置缓存的样式
        
        用于预热缓存或批量设置样式。
        
        Args:
            key: 样式缓存键
            style: QSS 样式字符串
        """
        self._cache[key] = style
    
    def clear_cache(self) -> None:
        """清除所有缓存（主题切换时使用）
        
        清除样式缓存和预编译的样式表，
        下次访问时会重新生成。
        """
        self._cache.clear()
        self._compiled_stylesheet = None
    
    def get_cache_stats(self) -> Dict[str, int]:
        """获取缓存统计信息
        
        Returns:
            包含缓存条目数和预编译状态的字典
        """
        return {
            "cached_styles_count": len(self._cache),
            "has_compiled_stylesheet": self._compiled_stylesheet is not None,
        }
    
    def preload_common_styles(self) -> None:
        """预加载常用样式到缓存
        
        在应用启动时调用，预热缓存以提高首次访问性能。
        """
        from screenshot_tool.ui.styles import (
            BUTTON_PRIMARY_STYLE,
            BUTTON_SECONDARY_STYLE,
            INPUT_STYLE,
            CHECKBOX_STYLE,
            TEXT_AREA_STYLE,
        )
        
        # 预加载常用样式
        common_styles = {
            "button_primary": BUTTON_PRIMARY_STYLE,
            "button_secondary": BUTTON_SECONDARY_STYLE,
            "input": INPUT_STYLE,
            "checkbox": CHECKBOX_STYLE,
            "text_area": TEXT_AREA_STYLE,
        }
        
        for key, style in common_styles.items():
            self._cache[key] = style
