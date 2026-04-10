# 系统设置安全中心改密码设计

日期：2026-04-10  
状态：已评审草案

## 目标

在现有“系统设置”页中新增“安全中心”区域，让当前已登录用户可以通过邮箱验证码验证后直接修改登录密码。

本次只做邮箱验证码改密码，不扩展手机号改密码、设备管理、异地登录提醒等能力。

## 用户流程

1. 用户进入系统设置页。
2. 页面在现有“账户中心”信息卡下方新增“安全中心”卡片。
3. 用户点击“发送验证码”。
4. 后端读取当前登录用户的邮箱，并向该邮箱发送验证码。
5. 用户输入验证码、新密码、确认新密码。
6. 用户点击“确认修改”。
7. 后端验证验证码并更新当前账号的密码哈希。
8. 前端显示“密码修改成功”，并清空验证码和密码输入框。

## 交互规则

- 只允许当前登录账号修改自己的密码。
- 不要求输入旧密码。
- 新密码长度沿用当前注册规则，至少 6 位。
- “确认新密码”与“新密码”不一致时，前端直接拦截，不发送请求。
- 发送验证码成功后，按钮进入 60 秒倒计时。
- 如果当前账号没有绑定邮箱，则安全中心显示不可操作提示，不展示可提交的改密流程。

## 前端设计

### 页面结构

文件：`frontend/src/pages/SettingsPage.tsx`

在当前“账户中心”静态信息卡下新增一个“安全中心”卡片，包含：

- 当前邮箱展示
- 发送验证码按钮
- 验证码输入框
- 新密码输入框
- 确认新密码输入框
- 错误提示区域
- 成功提示区域
- 提交按钮

### 状态设计

建议在 `SettingsPage` 内部维护这些状态：

- `code`
- `newPassword`
- `confirmPassword`
- `isSendingCode`
- `isSubmitting`
- `countdown`
- `errorMessage`
- `successMessage`
- `devCode`

### 前端请求

#### 发送验证码

`POST /api/auth/security/send-password-code`

请求头：

- `Authorization: Bearer <token>`

返回：

- 成功：`{ success: true }`
- 开发模式：`{ success: true, dev_code: "123456" }`

#### 提交改密

`POST /api/auth/security/reset-password`

请求体：

```json
{
  "code": "123456",
  "new_password": "new-password"
}
```

请求头：

- `Authorization: Bearer <token>`

返回：

```json
{
  "success": true,
  "message": "密码修改成功"
}
```

## 后端设计

### 新增 schema

文件：`backend/src/schemas.py`

新增：

- `SecurityResetPasswordRequest`
  - `code: str`
  - `new_password: str`

### auth 层能力

文件：`backend/src/auth.py`

新增一个用于当前用户改密的函数，例如：

- `reset_password_with_email_code(user_id: str, code: str, new_password: str) -> dict`

职责：

1. 根据 `user_id` 读取用户
2. 校验该用户存在且已绑定邮箱
3. 校验邮箱验证码
4. 新密码长度校验
5. 用现有 bcrypt 哈希逻辑生成新密码哈希
6. 调用 `update_user_password_credentials(...)` 更新密码
7. 返回统一结果

### API 端点

文件：`backend/src/main.py`

新增两个受保护接口：

#### `POST /api/auth/security/send-password-code`

行为：

- 要求已登录
- 从当前用户读取邮箱
- 如果没有邮箱，返回 `400`
- 通过现有 `send_verification_code(email)` 发验证码
- 复用现有限流逻辑，action 可命名为 `auth-password-reset-code`

#### `POST /api/auth/security/reset-password`

行为：

- 要求已登录
- 读取当前用户
- 调用 `auth.reset_password_with_email_code(...)`
- 成功时返回 `success + message`

## 错误处理

- 未登录：`401`
- 当前账号没有邮箱：`400`
- 验证码错误或过期：`400`
- 新密码少于 6 位：`400`
- 邮件发送失败：`500`

前端提示文案以清晰直接为主，不暴露内部实现细节。

## 样式方向

文件：`frontend/src/styles/index.css`

沿用当前系统设置页已有的像素边框和卡片风格，不单独引入新视觉体系。

安全中心卡片建议包含：

- 与账户卡一致的外框
- 正常字体的表单文字
- 明显的主按钮和次按钮
- 成功提示使用绿色，错误提示使用红色

## 测试范围

### 后端

- 已登录邮箱用户可发送改密验证码
- 验证码正确时可修改密码
- 验证码错误时返回失败
- 无邮箱用户无法发送改密验证码

### 前端

- 设置页渲染安全中心
- 点击发送验证码会发请求
- 两次密码不一致时阻止提交
- 修改成功后显示成功提示并清空输入

## 不做的内容

- 不增加旧密码校验
- 不增加手机号验证码改密
- 不增加二次登录确认
- 不强制改密后立即登出

## 实现边界

这次只在现有系统设置页内增加安全中心，不新增独立安全中心路由页。
