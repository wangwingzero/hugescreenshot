/**
 * 标注相关类型定义
 * 用于 screenshot store 和 overlay-main.ts
 */

import type { Rect } from './screenshot'

/** 标注工具类型 */
export type AnnotationTool =
  | 'select'
  | 'rectangle'
  | 'ellipse'
  | 'arrow'
  | 'line'
  | 'text'
  | 'mosaic'
  | 'blur'
  | 'pen'
  | 'marker'

/** 坐标点 */
export interface Point {
  x: number
  y: number
}

/** 标注样式 */
export interface AnnotationStyle {
  /** 描边颜色 */
  strokeColor: string
  /** 填充颜色 */
  fillColor: string
  /** 描边宽度 */
  strokeWidth: number
  /** 字体大小 (文字工具) */
  fontSize?: number
  /** 字体 (文字工具) */
  fontFamily?: string
  /** 马赛克块大小 */
  mosaicSize?: number
  /** 模糊半径 */
  blurRadius?: number
}

/** 标注对象基础接口 */
export interface AnnotationObject {
  /** 唯一 ID */
  id: string
  /** 工具类型 */
  type: AnnotationTool
  /** 关键点列表 */
  points: Point[]
  /** 样式 */
  style: AnnotationStyle
  /** 文字内容 (文字工具) */
  text?: string
  /** 边界框 (计算属性) */
  bounds?: Rect
  /** 是否选中 */
  selected?: boolean
  /** 是否锁定 */
  locked?: boolean
}

/** 默认标注样式 */
export const DEFAULT_ANNOTATION_STYLE: AnnotationStyle = {
  strokeColor: '#FF0000',
  fillColor: 'transparent',
  strokeWidth: 2,
  fontSize: 16,
  fontFamily: 'Microsoft YaHei',
  mosaicSize: 10,
  blurRadius: 8,
}
