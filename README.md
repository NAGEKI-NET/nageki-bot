# Nageki-Bot

Nageki-Net Rating 查询插件，支持完整的 API 获取、图片获取、数据分析功能。

## 功能特性

- ✅ **API 数据获取**：从 Nageki-Net API 获取玩家资料、B50、NEW10、PSCORE50 数据
- ✅ **图片获取**：自动下载音乐封面图片并缓存到本地
- ✅ **数据分析**：完整的 Rating 计算逻辑（谱面定数、分数加成、PScore Bonus）
- ✅ **前端截图渲染**：Profile 与 Rating 优先使用前端渲染页截图，失败时自动回退到 Pillow 绘图
- ✅ **QQ机器人集成**：支持QQ号绑定、查询绑定状态、查询用户资料等功能

## 安装依赖

```bash
pip install pillow aiohttp playwright
python -m playwright install chromium
```

或在 AstrBot 环境中：

```bash
uv run pip install pillow aiohttp playwright
uv run python -m playwright install chromium
```

说明：`playwright` 用于打开前端 `/render/ongeki-profile` 和 `/render/ongeki-rating` 并截图；如果运行环境已安装 Python 依赖但缺少 Playwright Chromium，插件会在首次浏览器截图时自动执行 `python -m playwright install chromium`。截图前会自动注入 `assets/fonts` 中随插件分发的字体，避免 bot 运行环境缺少系统中文/日文字体导致文字显示异常。如果运行环境没有安装 Playwright、Chromium 安装失败或前端渲染页不可访问，会自动回退到 Pillow 绘图版本。浏览器渲染和 Pillow 回退都会以 `base64://` 图片 URL 返回，不会写入截图文件，避免并发查询互相覆盖。

## 配置

### AstrBot 插件配置

现在可以直接在 AstrBot 后台填写插件配置，不需要提前手动设置环境变量。

在 AstrBot 中打开本插件配置后，填写以下字段：

```text
NAGEKI_API_URL = https://nageki-net.com/
NAGEKI_CDN_URL = https://cdn-nageki-next.sys-all.com.cn
NAGEKI_TOKEN = 从 Nageki-Net 网站登录后获取的 JWT Token
NAGEKI_PROFILE_RENDER_URL = http://localhost:4200/render/ongeki-profile
NAGEKI_RATING_RENDER_URL = http://localhost:4200/render/ongeki-rating
NAGEKI_PROFILE_RENDER_THEME = dark
NAGEKI_PROFILE_RENDER_LANGUAGE = zh
NAGEKI_PLAYWRIGHT_AUTO_INSTALL = true
NAGEKI_PLAYWRIGHT_BROWSER_TIMEOUT = 60
NAGEKI_PLAYWRIGHT_INSTALL_TIMEOUT = 600
BOT_API_URL = http://localhost:8080
BOT_API_KEY = 你的 QQ 机器人 API 密钥
```

说明：
- `NAGEKI_TOKEN` 为 Rating 查询必填。
- `NAGEKI_PROFILE_RENDER_URL` 为资料截图使用的前端渲染页；需要指向 NAGEKI-NET-NEXT 的 `/render/ongeki-profile`。
- `NAGEKI_RATING_RENDER_URL` 为 Rating 截图使用的前端渲染页；需要指向 NAGEKI-NET-NEXT 的 `/render/ongeki-rating`。
- `NAGEKI_PROFILE_RENDER_THEME` 控制前端截图主题，可填 `dark` 或 `light`。
- `NAGEKI_PROFILE_RENDER_LANGUAGE` 控制前端截图语言，可填 `zh`、`en` 或 `ja`。
- `NAGEKI_PLAYWRIGHT_AUTO_INSTALL` 控制是否在缺少 Chromium 时自动安装，默认 `true`；如服务器禁止运行时下载，可设为 `false` 并提前手动执行 `python -m playwright install chromium`。
- `NAGEKI_PLAYWRIGHT_BROWSER_TIMEOUT` 控制浏览器截图超时时间，默认 `60` 秒；用于启动浏览器、打开渲染页、等待前端 ready 和截图。
- `NAGEKI_PLAYWRIGHT_INSTALL_TIMEOUT` 控制自动安装超时时间，默认 `600` 秒。
- `NAGEKI_PLAYWRIGHT_INSTALL_WITH_DEPS` 默认为关闭；Linux 环境如果需要同时安装系统依赖，可设为 `true`，但这通常需要更高权限。
- `BOT_API_URL` 和 `BOT_API_KEY` 仅在使用 QQ 绑定、查绑、资料查询等功能时需要填写。
- 为兼容旧部署方式，插件仍支持从环境变量读取同名配置；如果插件配置里已填写，会优先使用插件配置。

## 使用方法

### 基础功能（Rating查询）

1. 确保已安装依赖（pillow、aiohttp、playwright，并安装 Playwright Chromium）
2. 在 AstrBot 插件配置中填写参数（特别是 `NAGEKI_TOKEN`）
3. 重启 AstrBot 以加载插件
4. 在聊天中发送消息：`nageki`
5. 插件会自动获取数据、下载图片、计算 Rating，并生成图片回复

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
├── rating_canvas.py       # Canvas 绘制模块
├── test_rating_style.py   # 样式测试脚本（独立运行）
├── cache/                 # 缓存目录（自动创建）
│   ├── images/           # 图片缓存
│   └── music/            # 音乐数据缓存
└── assets/                # 输出目录（自动创建）
    └── nageki_rating.png # 生成的图片
```

## 测试样式

如果想只测试图片样式（不连接 API），可以运行：

```bash
python test_rating_style.py
```

这会生成一个示例图片并自动打开。

## 注意事项

1. **Token 获取**：需要从 Nageki-Net 网站登录后获取 JWT token
2. **网络连接**：需要能够访问 Nageki-Net API 和 CDN
3. **Playwright 浏览器运行时**：Profile 与 Rating 的浏览器截图会在缺少 Chromium 时自动执行 `python -m playwright install chromium`；如果自动安装失败，可手动运行该命令。插件会在截图时加载 `assets/fonts` 内置字体，通常不需要额外安装系统字体
4. **首次运行**：首次运行会下载音乐列表和封面图片，可能需要一些时间
5. **缓存**：数据会缓存到本地，后续运行会更快
6. **QQ机器人API**：使用QQ机器人功能需要在 AstrBot 插件配置中填写 `BOT_API_KEY`，并确保 API 密钥安全
7. **API地址**：默认QQ机器人API地址为 `http://localhost:8080`，可根据实际情况修改

## 开发说明

本插件完全实现了前端 `rating.component.ts` 的所有功能：

- API 调用逻辑（对应 `ApiService`）
- 图片获取逻辑（对应 `ImageService`）
- 音乐缓存逻辑（对应 `MusicCacheService`）
- Rating 计算逻辑（对应 `RatingCalculator`）
- Canvas 绘制布局（对应前端 HTML/CSS）

## 许可证

MIT
