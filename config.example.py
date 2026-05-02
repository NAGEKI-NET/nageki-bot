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

# ========== QQ机器人API 配置 ==========

# QQ机器人API服务器地址（测试阶段默认：http://localhost:8080）
# 不配置时默认使用 localhost:8080，方便本地测试
BOT_API_URL = "http://localhost:8080"

# QQ机器人API密钥（必需，用于QQ机器人API认证）
# 所有QQ机器人API请求都需要在HTTP Header中携带此密钥：X-Bot-Api-Key
# 测试阶段使用默认密钥，生产环境请替换为实际密钥
BOT_API_KEY = "THIS_IS_A_SAMPLE_API_KEY_REPLACE_ME"
