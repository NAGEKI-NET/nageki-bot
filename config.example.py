"""
配置示例文件

使用方法：
1. 复制此文件为 config.py
2. 填入你的实际配置值
3. 或者在 AstrBot 插件配置中填写这些值
"""

# ========== Nageki-Net API 配置 ==========

# API 服务器地址
NAGEKI_API_URL = "https://nageki-net.com/"

# CDN 服务器地址
NAGEKI_CDN_URL = "https://cdn-nageki-next.sys-all.com.cn"

# JWT Token（必需）
# 从 Nageki-Net 网站登录后，在浏览器开发者工具中查看网络请求的 Authorization header
NAGEKI_TOKEN = "your_jwt_token_here"

# 前端资料截图渲染页地址
# 默认使用本机 Angular 开发服务；生产环境可改为已部署前端的 /render/ongeki-profile
NAGEKI_PROFILE_RENDER_URL = "http://localhost:4200/render/ongeki-profile"

# 前端 Rating 截图渲染页地址
# 默认使用本机 Angular 开发服务；生产环境可改为已部署前端的 /render/ongeki-rating
NAGEKI_RATING_RENDER_URL = "http://localhost:4200/render/ongeki-rating"

# 前端截图主题：dark 或 light
NAGEKI_PROFILE_RENDER_THEME = "dark"

# 前端截图语言：zh、en 或 ja
NAGEKI_PROFILE_RENDER_LANGUAGE = "zh"

# 缺少 Playwright Chromium 时自动执行：
# python -m playwright install chromium
NAGEKI_PLAYWRIGHT_AUTO_INSTALL = True

# 自动安装 Chromium 的超时时间（秒）
NAGEKI_PLAYWRIGHT_INSTALL_TIMEOUT = 600

# Linux 环境如果需要同时安装系统依赖可开启；通常需要更高权限
NAGEKI_PLAYWRIGHT_INSTALL_WITH_DEPS = False

# ========== QQ机器人API 配置 ==========

# QQ机器人API服务器地址（测试阶段默认：http://localhost:8080）
# 不配置时默认使用 localhost:8080，方便本地测试
BOT_API_URL = "http://localhost:8080"

# QQ机器人API密钥（必需，用于QQ机器人API认证）
# 所有QQ机器人API请求都需要在HTTP Header中携带此密钥：X-Bot-Api-Key
# 测试阶段使用默认密钥，生产环境请替换为实际密钥
BOT_API_KEY = "THIS_IS_A_SAMPLE_API_KEY_REPLACE_ME"
