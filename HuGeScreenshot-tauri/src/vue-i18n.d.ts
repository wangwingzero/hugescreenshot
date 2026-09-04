/**
 * Vue I18n 类型声明
 *
 * 为 Vue 3 组件添加 $t, $tc, $n, $d 全局属性的类型支持
 *
 * @validates Requirements 17.6
 */

import { DefineLocaleMessage } from 'vue-i18n'

declare module '@vue/runtime-core' {
  interface ComponentCustomProperties {
    $t: (key: string, ...args: any[]) => string
    $tc: (key: string, choice?: number, ...args: any[]) => string
    $n: (value: number, ...args: any[]) => string
    $d: (value: Date, ...args: any[]) => string
  }
}

export {}
