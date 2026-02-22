# 🚀 开发环境快速启动指南

## ✅ 已完成：开发环境跳过认证功能

现在可以在开发环境中无需登录直接使用聊天功能！

---

## 📦 快速启动

### 1️⃣ 启动后端

```bash
cd D:\AGEO\aeo-platform\backend
uvicorn app.main:socket_app --reload --port 8000
```

### 2️⃣ 启动前端

```bash
cd D:\AGEO\frontend
npm run dev
```

### 3️⃣ 访问应用

```
http://localhost:3000/chat/new
```

**无需登录，直接使用！** 🎉

---

## 🔍 验证配置

```bash
cd D:\AGEO
python verify_dev_mode.py
```

应该看到：
```
[OK] 开发模式已启用
```

---

## ⚙️ 配置文件

### 后端配置：`aeo-platform/backend/.env.local`

```env
DEBUG=true
DEV_MODE_ENABLED=true
DEV_TOKEN=dev-token
DEV_USER_EMAIL=dev@test.com
DEV_USER_NAME=Development User
```

### 前端配置：`frontend/.env.local`

```env
NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1
NEXT_PUBLIC_WS_URL=ws://localhost:8000
```

---

## 🔒 安全提示

⚠️ **开发模式仅用于本地开发！**

生产环境必须设置：
```env
DEBUG=false
# 或
DEV_MODE_ENABLED=false
```

---

## 📋 工作原理

```
前端 (开发模式)
  ↓ 自动使用 'dev-token'
后端 (开发模式)
  ↓ 识别 dev-token
  ↓ 创建/使用测试用户 (dev@test.com)
  ↓ 允许连接
✅ 连接成功
```

---

## 🛠️ 故障排查

### WebSocket 连接失败？

1. 检查 `.env.local` 配置
2. 重启后端服务
3. 运行验证脚本：`python verify_dev_mode.py`

### 仍然提示需要登录？

1. 确认使用 `npm run dev`（开发模式）
2. 清除浏览器缓存
3. 检查浏览器控制台错误

---

## 📚 详细文档

- **实施总结**：`D:\AGEO\IMPLEMENTATION_SUMMARY.md`
- **详细文档**：`D:\AGEO\DEV_MODE_SETUP.md`
- **验证脚本**：`D:\AGEO\verify_dev_mode.py`

---

## 🎯 修改的文件

### 后端（5个文件）
- ✅ `app/core/config.py` - 添加开发模式配置
- ✅ `app/services/user_service.py` - 添加测试用户创建
- ✅ `app/main.py` - 修改 WebSocket 认证逻辑
- ✅ `.env.local` - 配置开发模式
- ✅ `.env.local.example` - 更新配置示例

### 前端（1个文件）
- ✅ `src/hooks/useWebSocket.ts` - 自动使用 dev-token

---

## 💡 提示

开发模式启用时，你会看到警告日志：

**后端日志**：
```
[WebSocket] ⚠️  DEVELOPMENT MODE: Using dev user (dev@test.com)
```

**前端控制台**：
```
[WebSocket] ⚠️  DEVELOPMENT MODE: Using default dev-token
```

这是正常的，表示开发模式正在工作！

---

**祝开发愉快！** 🚀
