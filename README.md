# Nageki-Bot

Nageki-Net Rating 查询插件，支持完整的 API 获取、图片获取、数据分析功能。

## 功能特性

- ✅ **API 数据获取**：从 Nageki-Net API 获取玩家资料、B50、NEW10、PSCORE50 数据
- ✅ **图片获取**：音乐与封面资源均通过线上 API/CDN 获取
- ✅ **数据分析**：完整的 Rating 计算逻辑（谱面定数、分数加成、PScore Bonus）
- ✅ **前端截图渲染**：Profile 与 Rating 使用线上前端渲染页截图，不再回退到本地 canvas/Pillow 绘图
- ✅ **QQ机器人集成**：支持QQ号绑定、查询绑定状态、查询用户资料等功能

## 安装依赖

```bash
pip install aiohttp playwright
python -m playwright install chromium
```

或在 AstrBot 环境中：

```bash
uv run pip install aiohttp playwright
uv run python -m playwright install chromium
```

说明：`playwright` 用于打开线上前端 `/render/ongeki-profile`、`/render/ongeki-rating`、`/render/maimai2-profile` 和 `/render/maimai2-rating` 并截图；请在部署时安装 Playwright Chromium，插件默认不会在运行时自动安装本地浏览器。截图结果以 `base64://` 图片 URL 返回，不会写入截图文件，也不会回退到本地 canvas/Pillow 绘图。

## 配置

### AstrBot 插件配置

现在可以直接在 AstrBot 后台填写插件配置，不需要提前手动设置环境变量。

在 AstrBot 中打开本插件配置后，填写以下字段：

```text
NAGEKI_API_URL = https://nageki-net.com/
NAGEKI_CDN_URL = https://cdn-nageki-next.sys-all.com.cn
NAGEKI_TOKEN = 从 Nageki-Net 网站登录后获取的 JWT Token
NAGEKI_PROFILE_RENDER_URL = https://next.nageki-net.com/render/ongeki-profile
NAGEKI_RATING_RENDER_URL = https://next.nageki-net.com/render/ongeki-rating
NAGEKI_MAIMAI_PROFILE_RENDER_URL = https://next.nageki-net.com/render/maimai2-profile
NAGEKI_MAIMAI_RATING_RENDER_URL = https://next.nageki-net.com/render/maimai2-rating
NAGEKI_PROFILE_RENDER_THEME = dark
NAGEKI_PROFILE_RENDER_LANGUAGE = zh
NAGEKI_PLAYWRIGHT_AUTO_INSTALL = false
NAGEKI_PLAYWRIGHT_BROWSER_TIMEOUT = 60
NAGEKI_PLAYWRIGHT_INSTALL_TIMEOUT = 600
BOT_API_URL = https://nageki-net.com
BOT_API_KEY = 你的 QQ 机器人 API 密钥
```

说明：
- `NAGEKI_TOKEN` 为 Rating 查询必填。
- `NAGEKI_PROFILE_RENDER_URL` 为资料截图使用的前端渲染页；需要指向 NAGEKI-NET-NEXT 的 `/render/ongeki-profile`。
- `NAGEKI_RATING_RENDER_URL` 为 Rating 截图使用的前端渲染页；需要指向 NAGEKI-NET-NEXT 的 `/render/ongeki-rating`。
- `NAGEKI_MAIMAI_PROFILE_RENDER_URL` 为 Maimai 资料截图使用的前端渲染页；默认指向线上 `/render/maimai2-profile`。
- `NAGEKI_MAIMAI_RATING_RENDER_URL` 为 Maimai Rating 截图使用的前端渲染页；默认指向线上 `/render/maimai2-rating`。
- `NAGEKI_PROFILE_RENDER_THEME` 控制前端截图主题，可填 `dark` 或 `light`。
- `NAGEKI_PROFILE_RENDER_LANGUAGE` 控制前端截图语言，可填 `zh`、`en` 或 `ja`。
- `NAGEKI_PLAYWRIGHT_AUTO_INSTALL` 控制是否在缺少 Chromium 时自动安装，默认 `false`；建议部署时提前手动执行 `python -m playwright install chromium`。
- `NAGEKI_PLAYWRIGHT_BROWSER_TIMEOUT` 控制浏览器截图超时时间，默认 `60` 秒；用于启动浏览器、打开渲染页、等待前端 ready 和截图。
- `NAGEKI_PLAYWRIGHT_INSTALL_TIMEOUT` 控制自动安装超时时间，默认 `600` 秒。
- `NAGEKI_PLAYWRIGHT_INSTALL_WITH_DEPS` 默认为关闭；Linux 环境如果需要同时安装系统依赖，可设为 `true`，但这通常需要更高权限。
- `BOT_API_URL` 和 `BOT_API_KEY` 仅在使用 QQ 绑定、查绑、资料查询等功能时需要填写。
- 为兼容旧部署方式，插件仍支持从环境变量读取同名配置；如果插件配置里已填写，会优先使用插件配置。

## 使用方法

### 基础功能（Rating查询）

1. 确保已安装依赖（aiohttp、playwright，并安装 Playwright Chromium）
2. 在 AstrBot 插件配置中填写参数（特别是 `NAGEKI_TOKEN`）
3. 重启 AstrBot 以加载插件
4. 在聊天中发送消息：`nageki rating`
5. 插件会自动通过线上 API 获取数据、计算 Rating，并通过线上渲染页生成图片回复

### QQ机器人功能

配置 `BOT_API_KEY` 和 `BOT_API_URL` 后，可以使用以下命令：

- **健康检查**：`nageki health` - 检查QQ机器人API服务状态
- **绑定QQ号**：`nageki bind <绑定码>` - 将当前QQ号与游戏账号绑定
  - 示例：`nageki bind 123456`
- **查询绑定状态**：`nageki check <QQ号>` - 查询指定QQ号的绑定状态
  - 示例：`nageki check 123456789`
- **查询用户资料**：`nageki profile` - 查询当前QQ号绑定的用户游戏资料
  - 示例：`nageki profile`

## 文件结构

```
nageki-bot/
├── main.py                 # 主插件文件
├── nageki_api.py          # API 客户端
├── rating_calculator.py    # Rating 计算逻辑
├── rating_data.py         # 数据处理模块
├── rating_browser.py      # Ongeki Rating 线上前端截图模块
├── profile_browser.py     # Ongeki Profile 线上前端截图模块
├── maimai_browser.py      # Maimai 线上前端截图模块
└── assets/                # 前端截图所需字体等静态资源
```

## 注意事项

1. **Token 获取**：需要从 Nageki-Net 网站登录后获取 JWT token
2. **网络连接**：需要能够访问 Nageki-Net API 和 CDN
3. **Playwright 浏览器运行时**：Profile 与 Rating 的浏览器截图需要 Chromium；默认不会在运行时自动安装，请部署时手动运行 `python -m playwright install chromium`
4. **首次运行**：首次运行会从线上 API 获取音乐列表，可能需要一些时间
5. **缓存**：插件不再写入本地音乐或封面缓存，每次数据处理都以线上 API/CDN 为准
6. **QQ机器人API**：使用QQ机器人功能需要在 AstrBot 插件配置中填写 `BOT_API_KEY`，并确保 API 密钥安全
7. **API地址**：默认QQ机器人API地址为 `https://nageki-net.com`，可根据实际情况修改

## 开发说明

本插件完全实现了前端 `rating.component.ts` 的所有功能：

- API 调用逻辑（对应 `ApiService`）
- 图片获取逻辑（对应 `ImageService`，走线上 CDN）
- Rating 计算逻辑（对应 `RatingCalculator`）
- 前端截图渲染逻辑（对应线上 render 页面）

## 许可证

MIT
