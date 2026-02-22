## 测试计划概述

基于对 [Specta-AI-UI-Design-Specification.md](file:///d:/AGEO/Doc/Specta-AI-UI-Design-Specification.md) 和前端代码的全面分析，制定以下端到端测试计划：

### 测试范围

**核心用户路径 (8个)**
1. 会话创建与导航
2. 用户消息发送与显示
3. TPAOR 流程可视化（思考→规划→行动→观察→回复）
4. Agent 调用指示器展示
5. 进度指示器与执行步骤
6. 用户确认卡片交互
7. Canvas 面板动态内容展示
8. 停止/恢复执行控制

**边界场景 (6个)**
1. 空输入/超长输入处理
2. 网络中断与重连
3. 快速连续操作
4. 浏览器刷新恢复
5. 移动端触摸交互
6. 错误状态展示

**响应式断点 (4个)**
- Desktop (≥1440px): 三栏完整显示
- Laptop (1024-1439px): Canvas 可折叠
- Tablet (768-1023px): 导航栏折叠为图标
- Mobile (<768px): 单栏 + 底部导航

### 比对基准

1. **设计规范比对**: 与 [Specta-AI-UI-Design-Specification.md](file:///d:/AGEO/Doc/Specta-AI-UI-Design-Specification.md) 中定义的 13 个章节逐项核对
2. **Manus 基准对比**: 与 [Manus借鉴.png](file:///d:/AGEO/Doc/Manus借鉴.png) 的交互模式进行横向对比

### 测试工具

- **Browser Automation**: agent-browser (已加载)
- **性能分析**: Chrome DevTools Performance API
- **截图对比**: 自动化截图与视觉回归

### 预期交付物

1. 功能差异清单（功能缺失/交互偏差/视觉差异/性能偏离）
2. 差异率量化数据
3. 与 Manus 的横向对比矩阵
4. 根因分类（需求理解偏差/技术约束/实现疏漏）
5. 影响评级（高/中/低）与修复优先级
6. 改进方案与预防措施

请确认此计划后，我将开始执行测试流程。