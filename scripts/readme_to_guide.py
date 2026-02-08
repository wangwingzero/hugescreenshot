#!/usr/bin/env python3
"""
README.md 转换为 guide.html 的脚本

功能：
- 解析 README.md 内容
- 生成美观的 guide.html 页面
- 自动提取版本号、功能特性、快捷键等

使用方法：
    python scripts/readme_to_guide.py
"""

import re
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Feature:
    """功能特性"""
    icon: str
    title: str
    description: str


@dataclass
class Shortcut:
    """快捷键"""
    key: str
    action: str


@dataclass
class ReadmeContent:
    """README 解析结果"""
    version: str = ""
    features: list[Feature] = field(default_factory=list)
    shortcuts: list[Shortcut] = field(default_factory=list)
    quick_start: list[str] = field(default_factory=list)
    config_path: str = ""
    portable_mode: str = ""
    subscription_free: str = ""
    subscription_vip: str = ""


# 功能图标到 SVG 的映射
FEATURE_ICONS = {
    "📸": "screenshot",
    "🎨": "palette",
    "🔤": "text",
    "🌐": "globe",
    "📌": "pin",
    "📚": "book",
    "🖼️": "image",
    "🎬": "video",
    "📜": "document",
    "📝": "markdown",
    "📄": "word",
    "🖱️": "mouse",
    "🔧": "tool",
    "⏰": "clock",
    "🔄": "update",
    "👤": "user",
}

# SVG 图标定义
SVG_ICONS = {
    "screenshot": '''<path d="M14.5 4h-5L7 7H4a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2h-3l-2.5-3z"/><circle cx="12" cy="13" r="3"/>''',
    "palette": '''<circle cx="13.5" cy="6.5" r=".5"/><circle cx="17.5" cy="10.5" r=".5"/><circle cx="8.5" cy="7.5" r=".5"/><circle cx="6.5" cy="12.5" r=".5"/><path d="M12 2C6.5 2 2 6.5 2 12s4.5 10 10 10c.926 0 1.648-.746 1.648-1.688 0-.437-.18-.835-.437-1.125-.29-.289-.438-.652-.438-1.125a1.64 1.64 0 0 1 1.668-1.668h1.996c3.051 0 5.555-2.503 5.555-5.555C21.965 6.012 17.461 2 12 2z"/>''',
    "text": '''<polyline points="4 7 4 4 20 4 20 7"/><line x1="9" y1="20" x2="15" y2="20"/><line x1="12" y1="4" x2="12" y2="20"/>''',
    "globe": '''<circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>''',
    "pin": '''<path d="M12 17v5"/><path d="M9 10.76a2 2 0 0 1-1.11 1.79l-1.78.9A2 2 0 0 0 5 15.24V16a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-.76a2 2 0 0 0-1.11-1.79l-1.78-.9A2 2 0 0 1 15 10.76V7a1 1 0 0 1 1-1 2 2 0 0 0 0-4H8a2 2 0 0 0 0 4 1 1 0 0 1 1 1z"/>''',
    "book": '''<path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H20v20H6.5a2.5 2.5 0 0 1 0-5H20"/>''',
    "image": '''<rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><line x1="12" y1="8" x2="12" y2="16"/><line x1="8" y1="12" x2="16" y2="12"/>''',
    "video": '''<path d="m22 8-6 4 6 4V8Z"/><rect x="2" y="6" width="14" height="12" rx="2" ry="2"/>''',
    "document": '''<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/>''',
    "markdown": '''<path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>''',
    "word": '''<path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"/><polyline points="14 2 14 8 20 8"/>''',
    "mouse": '''<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>''',
    "tool": '''<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/>''',
    "clock": '''<circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>''',
    "update": '''<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>''',
    "user": '''<path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>''',
}


def parse_readme(readme_path: Path) -> ReadmeContent:
    """解析 README.md 文件"""
    content = readme_path.read_text(encoding='utf-8')
    result = ReadmeContent()
    
    # 提取版本号
    version_match = re.search(r'badge/version-(\d+\.\d+\.\d+)-', content)
    if version_match:
        result.version = version_match.group(1)
    
    # 提取功能特性
    features_section = re.search(r'## ✨ 功能特性\s*(.*?)(?=\n---|\n## )', content, re.DOTALL)
    if features_section:
        features_text = features_section.group(1)
        # 匹配每个功能块：### 图标 标题 + 列表项
        feature_blocks = re.findall(
            r'### ([^\n]+)\n((?:- [^\n]+\n?)+)',
            features_text
        )
        for title_line, items in feature_blocks:
            # 提取图标和标题
            icon_match = re.match(r'([^\s]+)\s+(.+)', title_line.strip())
            if icon_match:
                icon = icon_match.group(1)
                title = icon_match.group(2)
                # 合并列表项为描述
                items_list = [item.strip('- \n') for item in items.strip().split('\n') if item.strip()]
                description = '、'.join(items_list)
                result.features.append(Feature(icon=icon, title=title, description=description))
    
    # 提取快捷键
    shortcuts_section = re.search(r'## ⌨️ 快捷键\s*(.*?)(?=\n---|\n## )', content, re.DOTALL)
    if shortcuts_section:
        shortcuts_text = shortcuts_section.group(1)
        # 匹配表格行
        shortcut_rows = re.findall(r'\|\s*`([^`]+)`\s*\|\s*([^|]+)\s*\|', shortcuts_text)
        for key, action in shortcut_rows:
            if key and action.strip():
                result.shortcuts.append(Shortcut(key=key, action=action.strip()))
    
    # 提取快速开始
    quick_start_section = re.search(r'## 🚀 快速开始\s*(.*?)(?=\n---|\n## )', content, re.DOTALL)
    if quick_start_section:
        quick_start_text = quick_start_section.group(1)
        steps = re.findall(r'\d+\.\s+(.+)', quick_start_text)
        result.quick_start = steps
    
    # 如果没有用户友好的步骤，使用默认步骤
    if not result.quick_start:
        result.quick_start = [
            "下载安装包（Windows: `.exe` / macOS: `.dmg`）",
            "按照向导完成安装（macOS 拖入 Applications 即可）",
            "默认热键 `Alt+X`（macOS: `Option+X`）开始截图",
            "系统托盘会显示虎哥截图图标",
        ]
    
    # 提取配置信息
    config_section = re.search(r'## 🔧 配置\s*(.*?)(?=\n---|\n## )', content, re.DOTALL)
    if config_section:
        config_text = config_section.group(1)
        config_path_match = re.search(r'配置文件位置：`([^`]+)`', config_text)
        if config_path_match:
            result.config_path = config_path_match.group(1)
        portable_match = re.search(r'支持便携模式：(.+?)(?:\n|$)', config_text)
        if portable_match:
            result.portable_mode = portable_match.group(1).strip()
    
    # 提取订阅信息
    subscription_section = re.search(r'### 👤 账户与订阅\s*(.*?)(?=\n---|\n## |\n###|$)', content, re.DOTALL)
    if not subscription_section:
        subscription_section = re.search(r'账户与订阅\s*(.*?)(?=\n---|\n## |$)', content, re.DOTALL)
    if subscription_section:
        sub_text = subscription_section.group(1)
        free_match = re.search(r'免费版[：:]\s*(.+?)(?:\n|$)', sub_text)
        if free_match:
            result.subscription_free = free_match.group(1).strip()
        vip_match = re.search(r'终身 VIP[：:]\s*(.+?)(?:\n|$)', sub_text)
        if vip_match:
            result.subscription_vip = vip_match.group(1).strip()
    
    return result


def get_svg_icon(emoji: str) -> str:
    """根据 emoji 获取对应的 SVG 图标"""
    icon_name = FEATURE_ICONS.get(emoji, "screenshot")
    svg_content = SVG_ICONS.get(icon_name, SVG_ICONS["screenshot"])
    return f'''<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">{svg_content}</svg>'''


def convert_markdown_inline(text: str) -> str:
    """将 Markdown 行内格式转换为 HTML
    
    支持: **粗体** → <strong>, `代码` → <code>
    """
    # 先处理 **粗体**（必须在 `code` 之前，避免 code 内的 ** 被误转）
    text = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', text)
    # 处理 `code` 标记
    text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)
    return text


def generate_feature_html(feature: Feature) -> str:
    """生成单个功能特性的 HTML"""
    svg = get_svg_icon(feature.icon)
    # 处理描述中的 Markdown 行内格式
    description = convert_markdown_inline(feature.description)
    return f'''                <div class="feature-item">
                    <strong>
                        {svg}
                        {feature.title}
                    </strong>
                    <span>{description}</span>
                </div>'''


def generate_shortcut_row(shortcut: Shortcut) -> str:
    """生成快捷键表格行"""
    return f'                <tr><td><code>{shortcut.key}</code></td><td>{shortcut.action}</td></tr>'


def generate_step_html(index: int, step: str) -> str:
    """生成快速开始步骤 HTML"""
    step = convert_markdown_inline(step)
    return f'''                <div class="step">
                    <div class="step-num">{index}</div>
                    <div class="step-content">{step}</div>
                </div>'''


def generate_guide_html(content: ReadmeContent) -> str:
    """生成完整的 guide.html"""
    # 生成功能特性 HTML
    features_html = '\n'.join(generate_feature_html(f) for f in content.features)
    
    # 生成快捷键表格行
    shortcuts_html = '\n'.join(generate_shortcut_row(s) for s in content.shortcuts)
    
    # 生成快速开始步骤
    steps_html = '\n'.join(generate_step_html(i+1, s) for i, s in enumerate(content.quick_start))
    
    return f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="description" content="虎哥截图使用说明 - 功能介绍、快捷键、配置指南">
    <meta name="theme-color" content="#f8fafc">
    <title>虎哥截图 - 使用说明</title>
    <link rel="preconnect" href="https://fonts.loli.net" crossorigin>
    <link href="https://fonts.loli.net/css2?family=Noto+Sans+SC:wght@400;500;600;700;800&display=swap" rel="stylesheet">
    <style>
        :root {{
            --bg-body: #f8fafc;
            --card-bg: rgba(255, 255, 255, 0.85);
            --card-border: #e2e8f0;
            --primary: #f59e0b;
            --primary-dark: #d97706;
            --text-main: #1e293b;
            --text-muted: #64748b;
        }}

        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
            -webkit-font-smoothing: antialiased;
        }}

        body {{
            font-family: "Noto Sans SC", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
            background-color: var(--bg-body);
            color: var(--text-main);
            line-height: 1.7;
        }}

        .container {{
            max-width: 800px;
            margin: 0 auto;
            padding: 40px 24px;
        }}

        @media (max-width: 640px) {{
            .container {{ padding: 24px 16px; }}
        }}

        .back-link {{
            display: inline-flex;
            align-items: center;
            gap: 6px;
            color: var(--text-muted);
            text-decoration: none;
            font-size: 14px;
            font-weight: 500;
            margin-bottom: 32px;
            transition: color 0.2s ease;
            cursor: pointer;
        }}

        .back-link:hover {{ color: var(--text-main); }}

        .back-link svg {{
            width: 16px;
            height: 16px;
        }}

        header {{
            text-align: center;
            margin-bottom: 48px;
            animation: fadeIn 0.5s ease-out;
        }}

        .logo {{
            width: 72px;
            height: 72px;
            background: linear-gradient(135deg, #fbbf24 0%, #f59e0b 100%);
            border-radius: 18px;
            display: flex;
            align-items: center;
            justify-content: center;
            margin: 0 auto 20px;
            box-shadow: 0 8px 24px -4px rgba(245, 158, 11, 0.3);
        }}

        .logo svg {{
            width: 36px;
            height: 36px;
            color: #fff;
        }}

        h1 {{
            font-size: 32px;
            font-weight: 800;
            margin-bottom: 12px;
            background: linear-gradient(135deg, #f59e0b, #d97706);
            -webkit-background-clip: text;
            background-clip: text;
            -webkit-text-fill-color: transparent;
        }}

        .version {{
            display: inline-block;
            padding: 5px 14px;
            background: rgba(245, 158, 11, 0.1);
            color: var(--primary-dark);
            border-radius: 20px;
            font-size: 13px;
            font-weight: 600;
        }}

        .section {{
            background: var(--card-bg);
            border: 1px solid var(--card-border);
            border-radius: 16px;
            padding: 24px;
            margin-bottom: 20px;
            animation: fadeInUp 0.5s ease-out backwards;
        }}

        .section:nth-child(2) {{ animation-delay: 0.05s; }}
        .section:nth-child(3) {{ animation-delay: 0.1s; }}
        .section:nth-child(4) {{ animation-delay: 0.15s; }}
        .section:nth-child(5) {{ animation-delay: 0.2s; }}

        h2 {{
            font-size: 17px;
            font-weight: 700;
            margin-bottom: 18px;
            display: flex;
            align-items: center;
            gap: 10px;
            color: var(--text-main);
        }}

        h2 svg {{
            width: 20px;
            height: 20px;
            color: var(--primary);
        }}

        p, li {{
            font-size: 14px;
            color: var(--text-muted);
        }}

        ul {{
            padding-left: 20px;
            margin: 10px 0;
        }}

        li {{ margin: 8px 0; }}

        .feature-grid {{
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 12px;
        }}

        @media (max-width: 600px) {{
            .feature-grid {{ grid-template-columns: 1fr; }}
        }}

        .feature-item {{
            padding: 14px;
            background: rgba(0, 0, 0, 0.02);
            border-radius: 12px;
            transition: background 0.2s ease;
        }}

        .feature-item:hover {{
            background: rgba(0, 0, 0, 0.04);
        }}

        .feature-item strong {{
            display: flex;
            align-items: center;
            gap: 8px;
            font-size: 14px;
            margin-bottom: 6px;
            color: var(--text-main);
        }}

        .feature-item strong svg {{
            width: 18px;
            height: 18px;
            color: var(--primary);
            flex-shrink: 0;
        }}

        .feature-item span {{
            font-size: 13px;
            color: var(--text-muted);
            display: block;
            padding-left: 26px;
        }}

        table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 14px;
        }}

        th, td {{
            padding: 12px 14px;
            text-align: left;
            border-bottom: 1px solid var(--card-border);
        }}

        th {{
            font-weight: 600;
            color: var(--text-main);
            background: rgba(0, 0, 0, 0.02);
        }}

        td {{ color: var(--text-muted); }}

        code {{
            background: rgba(0, 0, 0, 0.05);
            padding: 3px 8px;
            border-radius: 6px;
            font-family: "SF Mono", "Cascadia Code", Consolas, monospace;
            font-size: 13px;
        }}

        .tip {{
            background: rgba(245, 158, 11, 0.08);
            border-left: 3px solid var(--primary);
            padding: 14px 18px;
            border-radius: 0 10px 10px 0;
            margin: 18px 0;
        }}

        .tip strong {{
            color: var(--primary-dark);
            display: flex;
            align-items: center;
            gap: 6px;
            margin-bottom: 6px;
            font-size: 14px;
        }}

        .tip strong svg {{
            width: 16px;
            height: 16px;
        }}

        .tip p {{
            margin: 0;
        }}

        .steps {{
            counter-reset: step;
        }}

        .step {{
            display: flex;
            gap: 14px;
            margin: 14px 0;
        }}

        .step-num {{
            width: 28px;
            height: 28px;
            background: linear-gradient(135deg, #f59e0b, #d97706);
            color: white;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 13px;
            font-weight: 600;
            flex-shrink: 0;
            box-shadow: 0 2px 8px rgba(245, 158, 11, 0.3);
        }}

        .step-content {{
            flex: 1;
            padding-top: 4px;
            font-size: 14px;
            color: var(--text-muted);
        }}

        footer {{
            text-align: center;
            padding: 32px 0;
            font-size: 13px;
            color: var(--text-muted);
        }}

        footer a {{
            color: var(--primary);
            text-decoration: none;
            transition: color 0.2s ease;
            cursor: pointer;
        }}

        footer a:hover {{
            color: var(--primary-dark);
        }}

        @keyframes fadeIn {{
            from {{ opacity: 0; }}
            to {{ opacity: 1; }}
        }}

        @keyframes fadeInUp {{
            from {{ opacity: 0; transform: translateY(12px); }}
            to {{ opacity: 1; transform: translateY(0); }}
        }}

        @media (prefers-reduced-motion: reduce) {{
            *, *::before, *::after {{
                animation-duration: 0.01ms !important;
                transition-duration: 0.01ms !important;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <a href="index.html" class="back-link">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="m15 18-6-6 6-6"/>
            </svg>
            返回首页
        </a>

        <header>
            <div class="logo">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M14.5 4h-5L7 7H4a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2h-3l-2.5-3z"/>
                    <circle cx="12" cy="13" r="3"/>
                </svg>
            </div>
            <h1>虎哥截图</h1>
            <span class="version">v{content.version}</span>
        </header>

        <!-- 快速开始 -->
        <div class="section">
            <h2>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M4.5 16.5c-1.5 1.26-2 5-2 5s3.74-.5 5-2c.71-.84.7-2.13-.09-2.91a2.18 2.18 0 0 0-2.91-.09z"/>
                    <path d="m12 15-3-3a22 22 0 0 1 2-3.95A12.88 12.88 0 0 1 22 2c0 2.72-.78 7.5-6 11a22.35 22.35 0 0 1-4 2z"/>
                    <path d="M9 12H4s.55-3.03 2-4c1.62-1.08 5 0 5 0"/>
                    <path d="M12 15v5s3.03-.55 4-2c1.08-1.62 0-5 0-5"/>
                </svg>
                快速开始
            </h2>
            <div class="steps">
{steps_html}
            </div>
            <div class="tip">
                <strong>
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/>
                        <line x1="12" y1="9" x2="12" y2="13"/>
                        <line x1="12" y1="17" x2="12.01" y2="17"/>
                    </svg>
                    重要提示
                </strong>
                <p>安装版会自动处理更新，无需手动操作。</p>
            </div>
        </div>

        <!-- 功能特性 -->
        <div class="section">
            <h2>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>
                </svg>
                功能特性
            </h2>
            <div class="feature-grid">
{features_html}
            </div>
        </div>

        <!-- 快捷键 -->
        <div class="section">
            <h2>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <rect x="2" y="4" width="20" height="16" rx="2" ry="2"/>
                    <path d="M6 8h.001"/>
                    <path d="M10 8h.001"/>
                    <path d="M14 8h.001"/>
                    <path d="M18 8h.001"/>
                    <path d="M8 12h.001"/>
                    <path d="M12 12h.001"/>
                    <path d="M16 12h.001"/>
                    <path d="M7 16h10"/>
                </svg>
                快捷键
            </h2>
            <table>
                <tr><th>快捷键</th><th>功能</th></tr>
{shortcuts_html}
            </table>
        </div>

        <!-- 配置 -->
        <div class="section">
            <h2>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <circle cx="12" cy="12" r="3"/>
                    <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/>
                </svg>
                配置
            </h2>
            <p>配置文件位置：<code>{content.config_path}</code></p>
            <p style="margin-top: 10px;">支持便携模式：将 <code>config.json</code> 放在程序同目录下即可。</p>
        </div>

        <!-- 订阅说明 -->
        <div class="section">
            <h2>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
                    <circle cx="12" cy="7" r="4"/>
                </svg>
                账户与订阅
            </h2>
            <ul>
                <li><strong>免费版</strong>：{content.subscription_free}</li>
                <li><strong>终身 VIP</strong>：{content.subscription_vip}</li>
            </ul>
        </div>

        <footer>
            <p>© 2024-2026 虎哥飞行空间 · <a href="index.html">返回首页</a></p>
        </footer>
    </div>
</body>
</html>
'''


def main():
    import argparse
    parser = argparse.ArgumentParser(description='将 README.md 转换为 guide.html')
    parser.add_argument('--readme', default='README.md', help='README.md 路径')
    parser.add_argument('--guide', default='website/guide.html', help='guide.html 输出路径')
    args = parser.parse_args()
    
    # 确定脚本所在目录
    script_dir = Path(__file__).parent
    repo_root = script_dir.parent
    
    readme_path = repo_root / args.readme
    guide_path = repo_root / args.guide
    
    if not readme_path.exists():
        print(f"❌ 找不到 README: {readme_path}")
        return 1
    
    try:
        # 解析 README
        print(f"📖 解析 {readme_path.name}...")
        content = parse_readme(readme_path)
        print(f"   版本号: v{content.version}")
        print(f"   功能特性: {len(content.features)} 个")
        print(f"   快捷键: {len(content.shortcuts)} 个")
        print(f"   快速开始: {len(content.quick_start)} 步")
        
        # 生成 HTML
        print(f"🔨 生成 {guide_path.name}...")
        html = generate_guide_html(content)
        
        # 写入文件
        guide_path.parent.mkdir(parents=True, exist_ok=True)
        guide_path.write_text(html, encoding='utf-8')
        
        print(f"✅ 转换完成: {guide_path}")
        return 0
        
    except Exception as e:
        print(f"❌ 错误: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    exit(main())
