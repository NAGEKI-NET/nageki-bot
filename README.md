# Nageki-Bot

Nageki-Net Rating 查询插件，支持完整的 API 获取、图片获取、数据分析功能。

## 功能特性

- ✅ **API 数据获取**：从 Nageki-Net API 获取玩家资料、B50、NEW10、PSCORE50 数据
- ✅ **图片获取**：自动下载音乐封面图片并缓存到本地
- ✅ **数据分析**：完整的 Rating 计算逻辑（谱面定数、分数加成、PScore Bonus）
- ✅ **Canvas 绘制**：使用 Pillow 绘制精美的 Rating 图片，布局与前端保持一致
- ✅ **QQ机器人集成**：支持QQ号绑定、查询绑定状态、查询用户资料等功能

## 安装依赖

```bash
pip install pillow aiohttp
```

或在 AstrBot 环境中：

```bash
uv run pip install pillow aiohttp
```

## 配置

### AstrBot 插件配置

现在可以直接在 AstrBot 后台填写插件配置，不需要提前手动设置环境变量。

在 AstrBot 中打开本插件配置后，填写以下字段：

```text
NAGEKI_API_URL = https://nageki-net.com/
NAGEKI_CDN_URL = https://cdn-nageki-next.sys-all.com.cn
NAGEKI_TOKEN = 从 Nageki-Net 网站登录后获取的 JWT Token
BOT_API_URL = http://localhost:8080
BOT_API_KEY = 你的 QQ 机器人 API 密钥
```

说明：
- `NAGEKI_TOKEN` 为 Rating 查询必填。
- `BOT_API_URL` 和 `BOT_API_KEY` 仅在使用 QQ 绑定、查绑、资料查询等功能时需要填写。
- 为兼容旧部署方式，插件仍支持从环境变量读取同名配置；如果插件配置里已填写，会优先使用插件配置。

## 使用方法

### 基础功能（Rating查询）

1. 确保已安装依赖（pillow、aiohttp）
2. 在 AstrBot 插件配置中填写参数（特别是 `NAGEKI_TOKEN`）
3. 重启 AstrBot 以加载插件
4. 在聊天中发送消息：`nageki`
5. 插件会自动获取数据、下载图片、计算 Rating，并生成图片回复

### QQ机器人功能

配置 `BOT_API_KEY` 和 `BOT_API_URL` 后，可以使用以下命令：

- **健康检查**：`nageki health` - 检查QQ机器人API服务状态
- **绑定QQ号**：`nageki bind <QQ号> <绑定码>` - 将QQ号与游戏账号绑定
  - 示例：`nageki bind 123456789 123456`
- **查询绑定状态**：`nageki check <QQ号>` - 查询指定QQ号的绑定状态
  - 示例：`nageki check 123456789`
- **查询用户资料**：`nageki profile <QQ号>` - 查询指定QQ号绑定的用户游戏资料
  - 示例：`nageki profile 123456789`

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
3. **首次运行**：首次运行会下载音乐列表和封面图片，可能需要一些时间
4. **缓存**：数据会缓存到本地，后续运行会更快
5. **QQ机器人API**：使用QQ机器人功能需要在 AstrBot 插件配置中填写 `BOT_API_KEY`，并确保 API 密钥安全
6. **API地址**：默认QQ机器人API地址为 `http://localhost:8080`，可根据实际情况修改

## 开发说明

本插件完全实现了前端 `rating.component.ts` 的所有功能：

- API 调用逻辑（对应 `ApiService`）
- 图片获取逻辑（对应 `ImageService`）
- 音乐缓存逻辑（对应 `MusicCacheService`）
- Rating 计算逻辑（对应 `RatingCalculator`）
- Canvas 绘制布局（对应前端 HTML/CSS）

## 许可证

MIT
