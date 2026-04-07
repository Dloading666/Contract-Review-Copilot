```markdown
# 设计系统文档：权威协作界面 (The Authoritative Copilot)

## 1. 核心设计愿景与“创意北极星”
**创意北极星：数字策展人 (The Digital Curator)**

在法律科技领域，信任不仅仅源于专业，更源于**秩序**与**克制**。本设计系统超越了传统的“工具感”界面，旨在打造一种如高端法律期刊般的“数字策展”体验。我们抛弃了生硬的栅格线条，转而采用**非对称的呼吸感布局**与**多维色调层叠**。

界面不再是冰冷的表单，而是如同一叠整洁排列的优质法律公文纸，通过光影与色调的微妙变化来引导用户的注意力。这种“高级定制感”通过大面积的留白（Negative Space）、精密控制的对比度以及富有节奏感的版式设计来实现，旨在为律师提供一个沉浸式、极度宁静的合同审查环境。

---

## 2. 色彩系统：色彩深度的律动

本系统坚决反对使用“1像素实线边框”来划分区域。我们通过**色彩层级过渡**来定义空间。

### 调色板映射 (Material Design 3 规范)
- **Primary (核心行动):** `#004ac6` (权威蓝) - 用于核心操作，传达坚定与安全。
- **Primary Container (功能交互):** `#2563eb` - 用于 AI 高亮显示。
- **Surface (底座):** `#f7f9fb` - 整个应用的基础，模拟极其洁净的数字化办公台面。
- **Surface Container (Lowest - Highest):** 从 `#ffffff` 到 `#e0e3e5`。
- **Tertiary (警示与深度):** `#943700` - 用于合同风险点的微妙提醒。

### 核心色彩法则
1. **“无边界”原则 (The No-Line Rule)：** 严禁使用 `#000` 或高对比度的 1px 实线进行分区。必须通过背景色的位移（例如：在 `surface` 背景上放置一个 `surface-container-low` 区域）来划分模块。
2. **表面嵌套 (Surface Nesting)：** 模仿物理纸张的堆叠。最底层的看板使用 `surface`，其上的卡片使用 `surface-container-lowest` (#ffffff)，这种微妙的色彩差能产生自然的深度感。
3. **“磨砂与渐变” (Glass & Gradient)：** 
   - 浮动面板（如 AI 侧边栏）应使用 `surface-container-lowest` 并配合 `backdrop-blur` 效果。
   - 核心按钮（CTA）应使用从 `primary` 到 `primary_container` 的微弱线性渐变（45度角），为扁平化设计注入“灵魂”与质感。

---

## 3. 版式系统：法学社论风格

法律文档要求极致的易读性。我们选用了 **Manrope** 处理标题的张力，配合 **Inter** 承载正文的逻辑。

- **Display (大标题):** `Manrope`, 3.5rem - 用于数据概览或欢迎语，建立一种现代且自信的基调。
- **Headline (类目标题):** `Manrope`, 2rem - 明确、威严。
- **Body-lg (合同正文):** `Inter`, 1rem, 行高 1.6 - 确保长时间阅读不产生视觉疲劳。
- **Label (标签与元数据):** `Inter`, 0.75rem, 字间距 +0.05em - 增强小字号的解析度。

**排版哲学：** 标题与正文之间通过显著的字号跳跃（High-Contrast Scale）来打破平庸，模拟高端杂志的编辑布局，让重要的风险提示一目了然。

---

## 4. 深度与高度：音调建模 (Tonal Layering)

传统的阴影往往显得廉价，我们使用“音调层叠”来构建 3D 空间。

1. **层叠原则：** 容器的深度应通过 `surface-container` 的阶梯式变化来实现。例如：
   - 全局背景: `surface`
   - 文档编辑器区: `surface-container-lowest` (纯白，提供最高视觉聚焦)
   - 浮动工具栏: `surface-container-highest` + 10% 透明度渐变。
2. **环境光阴影 (Ambient Shadows)：** 仅在元素浮动时使用阴影。阴影必须极度扩散（Blur > 20px），不透明度控制在 4%-8% 之间，且阴影颜色应带有 2% 的 `primary` 色相，以模拟环境光的散射。
3. **“幽灵边框” (Ghost Border)：** 若因无障碍需求必须使用边框，请使用 `outline-variant` 令牌，并将其不透明度降至 15%。

---

## 5. 组件规范

### 按钮 (Buttons)
- **Primary:** 使用 `surface_tint` 填充，白色文字。边缘圆角固定为 `md` (0.375rem)，传达专业稳重的气质。
- **Secondary:** 放弃背景填充，改用 `outline-variant` 的极细边框（Ghost Border），在悬浮态时填充 `surface-container-high`。

### AI 风险卡片 (AI Alert Cards)
- **样式：** 禁止使用边框。使用 `surface-container-low` 作为底色。
- **点缀：** 在左侧设置一条 4px 宽的竖向 `primary` 色条，用于指示重要性，增加设计的非对称美感。

### 聊天气泡 (Professional Chat Bubbles)
- **AI 端：** 采用 `primary_container` 背景，文字颜色使用 `on_primary_container`，右上角圆角设为 `none`，体现非对称的建筑美。
- **用户端：** 采用 `surface_container_high`，确保低调、无压迫感。

### 合同高亮 (Document Highlighting)
- **原则：** 改变传统的黄色荧光笔思维。使用 `tertiary_fixed` (#ffdbcd) 处理高危条款，使用 `primary_fixed` 处理普通参考条款。背景色应带有极高的透明度，确保不遮盖文字本身。

---

## 6. 行为准则 (Do's and Don'ts)

### ✅ 执行 (Do's)
- **使用非对称布局：** 让左侧的文档流和右侧的 AI 建议区保持不同的留白比例，增加动感。
- **利用垂直间距：** 在列表项之间使用 `spacing-xl` (1.5rem) 的间距，而非横线分割。
- **文本层级化：** 对辅助性说明文字使用 `on_surface_variant`，弱化非核心信息。

### ❌ 避免 (Don'ts)
- **严禁使用 100% 不透明度的实色分割线：** 这会割裂界面的整体感，使其看起来像一个廉价的表格。
- **严禁使用全圆角 (Pill Shape)：** 除非是标签（Chips），否则主容器应保持 `md` (0.375rem) 圆角，过圆的形状会丧失法律行业的权威感。
- **严禁过度装饰：** 去掉所有不具备功能意义的阴影或渐变，所有的视觉元素必须为“合同理解”服务。

---

*这份设计系统通过对光影、色调及版式的极精细控制，将复杂的合同审查逻辑转化为优雅、高效且极具信任感的数字化艺术体验。*```