# macOS Style UI Design System (Vue 3 Edition)

本文档定义了项目的前端 UI 设计规范，基于 Apple Human Interface Guidelines，适配 Vue 3 技术栈。

---

## 技术栈

- **框架**: Vue 3 (Composition API)
- **样式**: Tailwind CSS v3.x
- **动画**: @vueuse/motion 或 Vue `<Transition>`
- **图标**: Lucide Vue Next (`lucide-vue-next`)

---

## 1. 视觉物理引擎 (核心设计 DNA)

### A. 高级毛玻璃效果 (Glassmorphism)

禁止使用简单的透明度，材质必须有物理光学玻璃的质感。

**公式**: `backdrop-filter: blur(VAR) saturate(VAR)` + `bg-opacity`

**材质类型**:
- **侧边栏/底层**: 薄材质
  ```
  bg-gray-100/60 dark:bg-[#1e1e1e]/60 backdrop-blur-2xl saturate-150
  ```
- **主窗口**: 厚材质
  ```
  bg-white/80 dark:bg-[#282828]/70 backdrop-blur-3xl
  ```
- **弹出层/菜单**: 超亮材质
  ```
  bg-white/90 dark:bg-[#323232]/90 backdrop-blur-xl shadow-2xl
  ```

**噪点纹理**: 大面积表面必须添加微妙的噪点叠加层 (opacity 0.015)，防止色带并模拟铝/玻璃质感。

### B. 光照与「视网膜边框」

原生 macOS 元素由光线定义，而非边框。

**0.5px 规则**: 标准 CSS 边框 (1px) 太粗。使用 `box-shadow` 或 `border-[0.5px]` 模拟发丝边框。
- 亮色模式: `border-black/5` 或 `shadow-[0_0_0_1px_rgba(0,0,0,0.05)]`
- 暗色模式: `border-white/10` 或 `shadow-[0_0_0_1px_rgba(255,255,255,0.1)]`

**顶部高光 (边框效果)**: 每个浮动容器 (卡片、弹窗、侧边栏) 必须有内部顶部白色高光，模拟顶部工作室照明。
```
shadow-[inset_0_1px_0_0_rgba(255,255,255,0.4)]
```

### C. 阴影与深度策略

使用分层阴影创建体积感。

**窗口深度**: 锐利环境阴影 + 大面积扩散阴影
```
shadow-[0px_0px_1px_rgba(0,0,0,0.4),0px_16px_36px_-8px_rgba(0,0,0,0.2)]
```

**交互深度**: 活动元素有深色、略带颜色的阴影；非活动元素后退（更低透明度阴影）。

---

## 2. 字体与图标

**字体族**:
```css
font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Inter", "PingFang SC", "Microsoft YaHei", sans-serif;
```

**渲染**: 始终强制 `-webkit-font-smoothing: antialiased`

**字距 (Letter Spacing)**:
- 小于 14px: `tracking-wide` (宽松)
- 大于 20px: `tracking-tight` (紧凑)

**图标规范**:
- 使用 `lucide-vue-next`
- 描边宽度: 1.5px (匹配 SF Symbols 默认值)
- 对齐: 图标必须光学居中，通常在按钮内 16px-18px

---

## 3. 组件规范

### A. 窗口外壳与侧边栏

**侧边栏导航**:
- 选中状态: "气泡"样式，圆角矩形 (`rounded-md`)
  - 主选中: `bg-blue-500 text-white`
  - 次选中: `bg-black/5 dark:bg-white/10 text-current`
- 内边距: 项目必须有水平内边距 (`px-2`)，不跨越全边缘

### B. 按钮与操作

**主按钮**:
```vue
<button class="
  bg-gradient-to-b from-blue-500 to-blue-600
  text-white font-medium
  px-4 py-2 rounded-lg
  shadow-sm
  border-[0.5px] border-white/20
  hover:from-blue-600 hover:to-blue-700
  active:scale-[0.98]
  transition-all duration-150
">
  确认
</button>
```

**分段控件 (Tab 切换器)**:
- 容器: `bg-gray-200/50 dark:bg-white/10 rounded-lg p-[2px]`
- 激活标签: `bg-white dark:bg-gray-600 shadow-sm rounded-[6px]`
- 必须有过渡动画

### C. 输入与表单

**文本输入框**:
```vue
<input class="
  w-full px-3 py-2
  bg-white dark:bg-white/5
  rounded-lg
  border-[0.5px] border-black/10 dark:border-white/10
  shadow-[inset_0_1px_2px_rgba(0,0,0,0.06)]
  focus:outline-none focus:ring-4 focus:ring-blue-500/20
  transition-shadow duration-200
" />
```

**开关 (Toggle)**:
- Apple "胶囊"样式，宽 26px，高 16px
- 切换时使用弹簧动画

### D. 数据展示 (列表与网格)

**表格/列表行**:
- 斑马纹: 交替 `bg-transparent` 和 `bg-black/[0.02]`
- 分隔线: 全宽 `border-b border-black/5`，但缩进以匹配文本起始位置

**Bento 网格卡片**:
```vue
<div class="
  bg-white/50 dark:bg-[#1e1e1e]/50
  backdrop-blur-md
  rounded-2xl
  border border-white/10
  hover:scale-[1.02]
  transition-transform duration-300
">
  <!-- 内容 -->
</div>
```

### E. 反馈 (弹窗与菜单)

**右键菜单**:
```
rounded-lg border border-black/10 bg-white/80 backdrop-blur-xl
```
- 分隔线: `h-[1px] bg-black/5 my-1`

**模态框 (Sheet)**:
- 必须从底部或中心以"弹簧"弹跳方式出现
- 背景遮罩: `bg-black/20` (不要太暗)

---

## 4. 动画与过渡

### Vue Transition 配置

```vue
<template>
  <Transition
    enter-active-class="transition-all duration-300 ease-out"
    leave-active-class="transition-all duration-200 ease-in"
    enter-from-class="opacity-0 scale-95"
    enter-to-class="opacity-100 scale-100"
    leave-from-class="opacity-100 scale-100"
    leave-to-class="opacity-0 scale-95"
  >
    <div v-if="show">内容</div>
  </Transition>
</template>
```

### @vueuse/motion 弹簧配置

```vue
<script setup>
import { useMotion } from '@vueuse/motion'

const target = ref(null)
const { motionProperties } = useMotion(target, {
  initial: { scale: 0.9, opacity: 0 },
  enter: {
    scale: 1,
    opacity: 1,
    transition: {
      type: 'spring',
      stiffness: 300,
      damping: 30
    }
  }
})
</script>
```

### 微交互

- 按钮点击: `active:scale-[0.96]`
- 悬停过渡: `transition-all duration-200 ease-out`

---

## 5. 颜色系统

### 主题色

```javascript
// tailwind.config.js 扩展
colors: {
  // macOS 系统蓝
  'mac-blue': '#007AFF',
  'mac-blue-dark': '#0A84FF',

  // 语义色
  'mac-red': '#FF3B30',
  'mac-orange': '#FF9500',
  'mac-yellow': '#FFCC00',
  'mac-green': '#34C759',
  'mac-teal': '#5AC8FA',
  'mac-purple': '#AF52DE',
  'mac-pink': '#FF2D55',

  // 灰度 (亮色模式)
  'mac-gray': {
    50: '#F5F5F7',
    100: '#E8E8ED',
    200: '#D2D2D7',
    300: '#AEAEB2',
    400: '#8E8E93',
    500: '#636366',
    600: '#48484A',
    700: '#3A3A3C',
    800: '#2C2C2E',
    900: '#1C1C1E',
  }
}
```

### 暗色模式优先

所有颜色必须使用 `dark:` 修饰符:
```
bg-white dark:bg-gray-900
text-gray-900 dark:text-white
border-black/5 dark:border-white/10
```

---

## 6. 代码实现指南

1. **暗色模式优先**: 所有组件必须同时支持亮色和暗色模式
2. **Tailwind 任意值**: 使用 `[]` 语法实现精确的 macOS 颜色，如 `bg-[#007AFF]`
3. **组合优先**: 优先使用具体的工具类，而非自定义 CSS 类
4. **语义化命名**: 组件和类名应反映其用途，而非外观

---

## 7. 常用组件 Tailwind 类速查

```javascript
// 卡片容器
const card = `
  bg-white/80 dark:bg-[#282828]/70
  backdrop-blur-3xl
  rounded-2xl
  border-[0.5px] border-black/5 dark:border-white/10
  shadow-[0px_0px_1px_rgba(0,0,0,0.4),0px_16px_36px_-8px_rgba(0,0,0,0.2)]
  shadow-[inset_0_1px_0_0_rgba(255,255,255,0.4)]
`

// 主按钮
const primaryButton = `
  bg-gradient-to-b from-blue-500 to-blue-600
  text-white font-medium
  px-4 py-2 rounded-lg
  shadow-sm border-[0.5px] border-white/20
  hover:from-blue-600 hover:to-blue-700
  active:scale-[0.98]
  transition-all duration-150
`

// 输入框
const input = `
  w-full px-3 py-2
  bg-white dark:bg-white/5
  rounded-lg
  border-[0.5px] border-black/10 dark:border-white/10
  shadow-[inset_0_1px_2px_rgba(0,0,0,0.06)]
  focus:outline-none focus:ring-4 focus:ring-blue-500/20
  transition-shadow duration-200
`

// 毛玻璃背景
const glassPane = `
  bg-white/60 dark:bg-[#1e1e1e]/60
  backdrop-blur-2xl saturate-150
  border-[0.5px] border-white/20
`
```
