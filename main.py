from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
import astrbot.api.message_components as Comp
import os
import aiohttp

from .nageki_api import NagekiApiClient, NagekiApiException
from .rating_data import RatingDataProcessor
from .rating_browser import generate_rating_browser_image
from .profile_browser import generate_profile_browser_image
from .maimai_browser import generate_maimai_profile_browser_image, generate_maimai_rating_browser_image
from . import browser_pool


@register("nageki-bot", "NagekiBot", "Nageki-Net Rating 查询插件，支持完整的 API 获取、图片获取、数据分析功能", "1.0.0")
class NagekiBot(Star):
    def __init__(self, context: Context, config=None):
        super().__init__(context)
        self.config = config
        self.api_client = None
        self._init_api_client()

    def _get_plugin_config_value(self, key: str, default=None):
        if self.config and key in self.config:
            value = self.config.get(key)
            if isinstance(value, str):
                value = value.strip()
            if value not in (None, ""):
                return value
        return os.getenv(key, default)
    
    def _init_api_client(self):
        """初始化 API 客户端"""
        # 从配置或环境变量获取 API 地址和 token
        # 注意：实际使用时需要配置这些值
        api_url = self._get_plugin_config_value("NAGEKI_API_URL", "https://nageki-net.com/")
        cdn_url = self._get_plugin_config_value("NAGEKI_CDN_URL", "https://cdn-nageki-next.sys-all.com.cn")
        token = self._get_plugin_config_value("NAGEKI_TOKEN")
        
        # QQ机器人 API 配置
        bot_api_key = self._get_plugin_config_value("BOT_API_KEY", "")
        bot_api_url = self._get_plugin_config_value("BOT_API_URL", "https://nageki-net.com")
        profile_render_url = self._get_plugin_config_value("NAGEKI_PROFILE_RENDER_URL", "https://next.nageki-net.com/render/ongeki-profile")
        rating_render_url = self._get_plugin_config_value("NAGEKI_RATING_RENDER_URL", "https://next.nageki-net.com/render/ongeki-rating")
        maimai_profile_render_url = self._get_plugin_config_value("NAGEKI_MAIMAI_PROFILE_RENDER_URL", "https://next.nageki-net.com/render/maimai2-profile")
        maimai_rating_render_url = self._get_plugin_config_value("NAGEKI_MAIMAI_RATING_RENDER_URL", "https://next.nageki-net.com/render/maimai2-rating")
        profile_render_theme = self._get_plugin_config_value("NAGEKI_PROFILE_RENDER_THEME", "dark")
        profile_render_language = self._get_plugin_config_value("NAGEKI_PROFILE_RENDER_LANGUAGE", "zh")
        for key in (
            "NAGEKI_PLAYWRIGHT_AUTO_INSTALL",
            "NAGEKI_PLAYWRIGHT_BROWSER_TIMEOUT",
            "NAGEKI_PLAYWRIGHT_INSTALL_TIMEOUT",
            "NAGEKI_PLAYWRIGHT_INSTALL_WITH_DEPS",
        ):
            value = self._get_plugin_config_value(key)
            if value is not None:
                os.environ[key] = str(value)
        bot_api_key_source = "插件配置" if self.config and self.config.get("BOT_API_KEY") not in (None, "") else ("环境变量" if os.getenv("BOT_API_KEY") else "默认值")
        
        logger.info(f"[初始化] BOT_API_KEY 来源: {bot_api_key_source}")
        logger.info(f"[初始化] BOT_API_KEY 长度: {len(bot_api_key) if bot_api_key else 0}")
        logger.info(f"[初始化] BOT_API_KEY 预览: {bot_api_key[:10] + '...' if bot_api_key and len(bot_api_key) > 10 else (bot_api_key or 'None')}")
        logger.info(f"[初始化] BOT_API_URL: {bot_api_url}")
        
        self.api_client = NagekiApiClient(
            api_base_url=api_url,
            cdn_base_url=cdn_url,
            token=token,
            bot_api_key=bot_api_key,
            bot_api_url=bot_api_url,
            profile_render_url=profile_render_url,
            rating_render_url=rating_render_url,
            maimai_profile_render_url=maimai_profile_render_url,
            maimai_rating_render_url=maimai_rating_render_url,
            profile_render_theme=profile_render_theme,
            profile_render_language=profile_render_language
        )
        
        logger.info(f"[初始化] API客户端已创建，bot_api_key已设置: {bool(self.api_client.bot_api_key)}")

    def _image_result(self, event: AstrMessageEvent, image_ref: str) -> MessageEventResult:
        if image_ref.startswith("base64://"):
            base64_data = image_ref.removeprefix("base64://")
            return event.chain_result([Comp.Image.fromBase64(base64_data)])
        if image_ref.startswith("data:image/") and ";base64," in image_ref:
            base64_data = image_ref.split(";base64,", 1)[1]
            return event.chain_result([Comp.Image.fromBase64(base64_data)])
        return event.image_result(image_ref)
    
    def _format_bot_token_error(self, e: NagekiApiException) -> str:
        error_text = f"{e.message}\n{e.raw_response or ''}"
        if (
            e.status >= 500
            and (
                "api/game/ongeki/profile" in error_text
                or "用户不存在" in error_text
                or "鐢ㄦ埛涓嶅瓨鍦" in error_text
            )
        ):
            return "该卡号没有 Ongeki 数据，请先用这张卡游玩并上传一次 Ongeki 数据后再查询。"
        if e.status == 401:
            return "认证失败：请检查 BOT_API_KEY 是否正确"
        if e.status == 404:
            return "未找到该QQ号的绑定信息，请前往 https://next.nageki-net.com/net/profile 绑定QQ账号"
        if e.status == 409 or "未绑卡" in e.message:
            return "该账号未绑卡，暂时无法查询 rating 或 profile"
        return f"获取Token失败：{e.message}"

    async def _get_sender_qq(self, event: AstrMessageEvent):
        sender = event.message_obj.sender
        qq_number = None
        if hasattr(sender, 'id'):
            qq_number = str(sender.id)
        elif hasattr(sender, 'user_id'):
            qq_number = str(sender.user_id)
        elif hasattr(sender, 'qq'):
            qq_number = str(sender.qq)
        if not qq_number and hasattr(event.message_obj, 'raw_message'):
            raw = event.message_obj.raw_message
            if hasattr(raw, 'user_id'):
                qq_number = str(raw.user_id)
            elif hasattr(raw, 'sender') and hasattr(raw.sender, 'user_id'):
                qq_number = str(raw.sender.user_id)
        return qq_number, sender

    async def _apply_user_bio_to_profile(self, token: str, profile: dict):
        try:
            user_profile = await self.api_client.get_user_profile_with_token(token)
            bio = (user_profile.get("bio") or "").strip() if isinstance(user_profile, dict) else ""
            if bio:
                profile["profileContent"] = bio
                logger.info("[资料命令] 已使用 /api/user/profile 的 bio 覆盖 profileContent")
        except Exception as user_profile_error:
            logger.warning(f"[资料命令] 获取 /api/user/profile 失败，继续使用原始资料: {user_profile_error}")
        return profile

    async def _get_user_profile_for_browser(self, token: str, profile: dict):
        try:
            user_profile = await self.api_client.get_user_profile_with_token(token)
            if isinstance(user_profile, dict):
                if (user_profile.get("bio") or "").strip():
                    profile["profileContent"] = user_profile.get("bio", "")
                return user_profile
        except Exception as user_profile_error:
            logger.warning(f"[浏览器截图] 获取 /api/user/profile 失败，将使用最小用户信息: {user_profile_error}")
        return {
            "id": "bot-render",
            "username": profile.get("userName", "bot-render"),
            "name": profile.get("userName", "bot-render"),
            "email": "",
            "bio": profile.get("profileContent", ""),
            "joinDate": "",
        }

    async def initialize(self):
        """插件初始化"""
        logger.info("NagekiBot 插件已初始化")
    
    @filter.event_message_type(filter.EventMessageType.ALL)
    async def reply_nageki(self, event: AstrMessageEvent):
        """处理各种命令"""
        message_str = event.message_str.strip()
        
        # 处理绑定说明命令
        if message_str.startswith("nageki bind") or message_str == "nageki 绑定":
             # 检查是否是帮助命令
             if message_str == "nageki bind" or message_str == "nageki 绑定":
                yield event.plain_result(
                    "绑定命令格式：\n"
                    "nageki bind <绑定码>\n\n"
                    "请前往 https://next.nageki-net.com/net/profile 获取绑定码"
                )
             else:
                async for result in self._handle_bind_command(event, message_str):
                    yield result
        # 处理查询绑定状态命令：nageki check <QQ号>
        elif message_str.startswith("nageki check "):
            async for result in self._handle_check_bind_command(event, message_str):
                yield result
        # 处理查询资料命令：nageki profile
        elif message_str == "nageki profile" or message_str.startswith("nageki profile "):
            async for result in self._handle_profile_command(event, message_str):
                yield result
        # 处理 Rating 命令：nageki rating
        elif message_str == "nageki maiprofile":
            async for result in self._handle_maimai_profile_command(event):
                yield result
        elif message_str == "nageki rating":
            async for result in self._handle_rating_command(event):
                yield result
        # 处理 B50 命令：nageki b50
        elif message_str == "nageki b50":
            async for result in self._handle_b50_command(event):
                yield result
        # 处理健康检查命令：nageki health
        elif message_str == "nageki health":
            async for result in self._handle_health_command(event):
                yield result
    
    async def _handle_bind_command(self, event: AstrMessageEvent, message_str: str):
        """处理绑定命令：nageki bind <绑定码>"""
        try:
            if not self.api_client.bot_api_key:
                yield event.plain_result(
                    "未配置 BOT_API_KEY，无法使用QQ机器人功能。\n"
                    "请在 AstrBot 插件配置中填写 BOT_API_KEY。"
                )
                return
            
            # 从事件中获取发送者的QQ号
            # 根据 AstrBot 文档，通过 event.message_obj.sender 获取发送者信息
            sender = event.message_obj.sender
            # 尝试多种方式获取用户ID
            qq_number = None
            if hasattr(sender, 'id'):
                qq_number = str(sender.id)
            elif hasattr(sender, 'user_id'):
                qq_number = str(sender.user_id)
            elif hasattr(sender, 'qq'):
                qq_number = str(sender.qq)
            # 如果以上都没有，尝试从 raw_message 获取
            if not qq_number and hasattr(event.message_obj, 'raw_message'):
                raw = event.message_obj.raw_message
                if hasattr(raw, 'user_id'):
                    qq_number = str(raw.user_id)
                elif hasattr(raw, 'sender') and hasattr(raw.sender, 'user_id'):
                    qq_number = str(raw.sender.user_id)
            
            if not qq_number:
                # 输出调试信息
                logger.error(f"无法获取QQ号，sender对象: {sender}, sender类型: {type(sender)}, sender属性: {dir(sender)}")
                yield event.plain_result("无法获取您的QQ号，请稍后重试")
                return
            
            parts = message_str.split()
            if len(parts) != 3:
                yield event.plain_result(
                    "绑定命令格式错误！\n"
                    "正确格式：nageki bind <绑定码>\n"
                    "示例：nageki bind 123456"
                )
                return
            
            code = parts[2]
            
            logger.info(f"[绑定命令] QQ号: {qq_number}, 绑定码: {code}")
            logger.info(f"[绑定命令] API密钥配置: {self.api_client.bot_api_key[:10] + '...' if self.api_client.bot_api_key and len(self.api_client.bot_api_key) > 10 else (self.api_client.bot_api_key or 'None')}")
            logger.info(f"[绑定命令] API地址: {self.api_client.bot_api_url}")
            
            yield event.plain_result(f"正在验证绑定码，请稍候...")
            
            result = await self.api_client.bot_bind(qq_number, code)
            message = result.get("message", "绑定成功！")
            logger.info(f"[绑定命令] 绑定成功: {message}")
            yield event.plain_result(message)
            
        except NagekiApiException as e:
            logger.error(f"[绑定命令] API API错误: {e.status} - {e.message}")
            if e.status == 400:
                 yield event.plain_result(f"绑定失败：{e.message}")
            elif e.status == 401:
                 logger.error(f"[绑定命令] 认证失败 - API密钥可能不正确")
                 yield event.plain_result(f"认证失败：请检查 BOT_API_KEY 是否正确")
            else:
                 yield event.plain_result(f"绑定失败 ({e.status})：{e.message}")
        except aiohttp.ClientResponseError as e:
            logger.error(f"[绑定命令] HTTP错误: 状态码={e.status}, 消息={e.message}")
            if hasattr(e, 'headers'):
                logger.error(f"[绑定命令] 响应头: {dict(e.headers)}")
            if e.status == 400:
                logger.error(f"[绑定命令] 绑定码错误或已过期")
                yield event.plain_result(f"绑定失败：绑定码错误或已过期")
            elif e.status == 401:
                logger.error(f"[绑定命令] 认证失败 - API密钥可能不正确")
                logger.error(f"[绑定命令] 使用的API密钥: {self.api_client.bot_api_key[:10] + '...' if self.api_client.bot_api_key and len(self.api_client.bot_api_key) > 10 else (self.api_client.bot_api_key or 'None')}")
                yield event.plain_result(f"认证失败：请检查 BOT_API_KEY 是否正确")
            else:
                logger.error(f"[绑定命令] 服务器返回错误: {e.status}")
                yield event.plain_result(f"绑定失败：服务器返回错误 {e.status}")
        except Exception as e:
            logger.error(f"[绑定命令] 处理出错: {type(e).__name__}: {e}", exc_info=True)
            yield event.plain_result(f"绑定时发生错误: {str(e)}")
    
    async def _handle_check_bind_command(self, event: AstrMessageEvent, message_str: str):
        """处理查询绑定状态命令：nageki check <QQ号>"""
        try:
            if not self.api_client.bot_api_key:
                yield event.plain_result(
                    "未配置 BOT_API_KEY，无法使用QQ机器人功能。\n"
                    "请在 AstrBot 插件配置中填写 BOT_API_KEY。"
                )
                return
            
            parts = message_str.split()
            if len(parts) != 3:
                yield event.plain_result(
                    "查询绑定状态命令格式错误！\n"
                    "正确格式：nageki check <QQ号>\n"
                    "示例：nageki check 123456789"
                )
                return
            
            qq_number = parts[2]
            
            yield event.plain_result("正在查询绑定状态，请稍候...")
            
            result = await self.api_client.bot_check_bind(qq_number)
            
            if result.get("bound", False):
                username = result.get("username", "未知")
                bind_time = result.get("bindTime", "未知")
                yield event.plain_result(
                    f"✅ 已绑定\n"
                    f"QQ号：{qq_number}\n"
                    f"玩家昵称：{username}\n"
                    f"绑定时间：{bind_time}"
                )
            else:
                yield event.plain_result(f"❌ 未绑定\nQQ号：{qq_number} 尚未绑定\n请前往 https://next.nageki-net.com/net/profile 绑定QQ账号")
            
        except aiohttp.ClientResponseError as e:
            if e.status == 401:
                yield event.plain_result(f"认证失败：请检查 BOT_API_KEY 是否正确")
            else:
                yield event.plain_result(f"查询失败：服务器返回错误 {e.status}")
        except Exception as e:
            logger.error(f"查询绑定状态命令处理出错: {e}", exc_info=True)
            yield event.plain_result(f"查询时发生错误: {str(e)}")
    
    async def _handle_profile_command(self, event: AstrMessageEvent, message_str: str):
        """处理查询资料命令：nageki profile"""
        try:
            if not self.api_client.bot_api_key:
                yield event.plain_result(
                    "未配置 BOT_API_KEY，无法使用QQ机器人功能。\n"
                    "请在 AstrBot 插件配置中填写 BOT_API_KEY。"
                )
                return
            
            # 从事件中获取发送者的QQ号
            sender = event.message_obj.sender
            # 尝试多种方式获取用户ID
            qq_number = None
            if hasattr(sender, 'id'):
                qq_number = str(sender.id)
            elif hasattr(sender, 'user_id'):
                qq_number = str(sender.user_id)
            elif hasattr(sender, 'qq'):
                qq_number = str(sender.qq)
            # 如果以上都没有，尝试从 raw_message 获取
            if not qq_number and hasattr(event.message_obj, 'raw_message'):
                raw = event.message_obj.raw_message
                if hasattr(raw, 'user_id'):
                    qq_number = str(raw.user_id)
                elif hasattr(raw, 'sender') and hasattr(raw.sender, 'user_id'):
                    qq_number = str(raw.sender.user_id)
            
            if not qq_number:
                # 输出调试信息
                logger.error(f"无法获取QQ号，sender对象: {sender}, sender类型: {type(sender)}, sender属性: {dir(sender)}")
                yield event.plain_result("无法获取您的QQ号，请稍后重试")
                return
            
            logger.info(f"[查询资料命令] QQ号: {qq_number}")
            

            
            # 步骤1: 获取JWT Token
            token_result = await self.api_client.bot_get_token(qq_number)
            token = token_result.get("token")
            
            if not token:
                logger.error(f"[查询资料命令] 获取Token失败: {token_result}")
                yield event.plain_result("获取Token失败，请确认该QQ号已绑定")
                return
            
            logger.info(f"[查询资料命令] Token获取成功")
            username = token_result.get("username", "未知")
            
            yield event.plain_result("正在获取用户资料，请稍候...")
            
            # 步骤2: 使用Token调用Net API获取资料
            result = await self.api_client.get_profile_with_token(token)
            try:
                user_profile = await self.api_client.get_user_profile_with_token(token)
                bio = (user_profile.get("bio") or "").strip() if isinstance(user_profile, dict) else ""
                if bio:
                    result["profileContent"] = bio
                    logger.info("[查询资料命令] 已使用 /api/user/profile 的 bio 覆盖 profileContent")
            except Exception as user_profile_error:
                logger.warning(f"[查询资料命令] 获取 /api/user/profile 失败，继续使用游戏资料签名: {user_profile_error}")
            
            # 记录API返回的完整数据，用于调试
            logger.info(f"[查询资料命令] Net API返回数据: {result}")
            logger.info(f"[查询资料命令] Net API返回数据的所有键: {list(result.keys()) if isinstance(result, dict) else 'Not a dict'}")
            
            image_url = await generate_profile_browser_image(
                "",
                result,
                api_client=self.api_client
            )
            yield self._image_result(event, image_url)
            
        except aiohttp.ClientResponseError as e:
            logger.error(f"[查询资料命令] HTTP错误: 状态码={e.status}, 消息={e.message}")
            if e.status == 401:
                yield event.plain_result(f"认证失败：请检查 BOT_API_KEY 是否正确，或该QQ号未绑定")
            elif e.status == 404:
                yield event.plain_result(f"未找到该QQ号的绑定信息，请前往 https://next.nageki-net.com/net/profile 绑定QQ账号")
            else:
                yield event.plain_result(f"查询失败：服务器返回错误 {e.status}")
        except NagekiApiException as e:
            logger.error(f"[查询资料命令] Bot API错误: {e.status} - {e.message}")
            yield event.plain_result(self._format_bot_token_error(e))
        except RuntimeError as e:
            logger.error(f"生成资料图片错误: {e}", exc_info=True)
            yield event.plain_result(f"线上资料截图生成失败: {str(e)}")
        except Exception as e:
            logger.error(f"查询资料命令处理出错: {e}", exc_info=True)
            yield event.plain_result(f"查询时发生错误: {str(e)}")
    
    async def _handle_rating_command(self, event: AstrMessageEvent):
        """处理 Rating 命令：nageki rating"""
        try:
            if not self.api_client.bot_api_key:
                yield event.plain_result(
                    "未配置 BOT_API_KEY，无法使用QQ机器人功能。\n"
                    "请在 AstrBot 插件配置中填写 BOT_API_KEY。"
                )
                return
            
            # 从事件中获取发送者的QQ号
            sender = event.message_obj.sender
            qq_number = None
            if hasattr(sender, 'id'):
                qq_number = str(sender.id)
            elif hasattr(sender, 'user_id'):
                qq_number = str(sender.user_id)
            elif hasattr(sender, 'qq'):
                qq_number = str(sender.qq)
            
            if not qq_number and hasattr(event.message_obj, 'raw_message'):
                raw = event.message_obj.raw_message
                if hasattr(raw, 'user_id'):
                    qq_number = str(raw.user_id)
                elif hasattr(raw, 'sender') and hasattr(raw.sender, 'user_id'):
                    qq_number = str(raw.sender.user_id)
            
            if not qq_number:
                logger.error(f"无法获取QQ号，sender对象: {sender}")
                yield event.plain_result("无法获取您的QQ号，请稍后重试")
                return
            
            yield event.plain_result("正在生成 Rating 图片，请稍候...")
            
            logger.info(f"[Rating命令] 开始处理 QQ号: {qq_number}")
            
            # 1. 获取 Token
            token_result = await self.api_client.bot_get_token(qq_number)
            token = token_result.get("token")
            
            if not token:
                logger.error(f"[Rating命令] 获取Token失败: {token_result}")
                yield event.plain_result("获取Token失败，请确认该QQ号已绑定。请前往 https://next.nageki-net.com/net/profile 绑定QQ账号")
                return
            
            logger.info(f"[Rating命令] Token获取成功")
            
            # 2. 处理数据
            logger.info(f"[Rating命令] 开始处理Rating数据...")
            processor = RatingDataProcessor(self.api_client)
            profile, categories = await processor.process_rating_data(token)
            profile = await self._apply_user_bio_to_profile(token, profile)
            logger.info(f"[Rating命令] 数据处理完成: Profile={profile.get('userName')}, Categories={len(categories)}")
            
            # 3. 生成图片
            logger.info(f"[Rating命令] 开始浏览器截图渲染")
            actual_path = await generate_rating_browser_image(
                "",
                profile,
                categories,
                api_client=self.api_client
            )
            logger.info(f"[Rating命令] 图片生成完成: {actual_path}")
            
            # 4. 发送图片
            logger.info(f"[Rating命令] 准备发送图片")
            yield self._image_result(event, actual_path)
            logger.info(f"[Rating命令] 图片已发送")
            
        except aiohttp.ClientResponseError as e:
            logger.error(f"[Rating命令] HTTP错误: 状态码={e.status}, 消息={e.message}")
            if e.status == 401:
                yield event.plain_result(f"认证失败：请检查 BOT_API_KEY 是否正确，或该QQ号未绑定。请前往 https://next.nageki-net.com/net/profile 绑定QQ账号")
            else:
                yield event.plain_result(f"请求失败：服务器返回错误 {e.status}")
        except RuntimeError as e:
            logger.error(f"生成图片错误: {e}", exc_info=True)
            yield event.plain_result(f"线上 Rating 截图生成失败: {str(e)}")
        except Exception as e:
            logger.error(f"Rating命令处理出错: {e}", exc_info=True)
            yield event.plain_result(f"发生错误: {str(e)}")

    async def _handle_b50_command(self, event: AstrMessageEvent):
        """处理 B50 命令：nageki b50"""
        try:
            if not self.api_client.bot_api_key:
                yield event.plain_result(
                    "未配置 BOT_API_KEY，无法使用QQ机器人功能。\n"
                    "请在 AstrBot 插件配置中填写 BOT_API_KEY。"
                )
                return
            
            # 从事件中获取发送者的QQ号
            sender = event.message_obj.sender
            qq_number = None
            if hasattr(sender, 'id'):
                qq_number = str(sender.id)
            elif hasattr(sender, 'user_id'):
                qq_number = str(sender.user_id)
            elif hasattr(sender, 'qq'):
                qq_number = str(sender.qq)
            
            if not qq_number and hasattr(event.message_obj, 'raw_message'):
                raw = event.message_obj.raw_message
                if hasattr(raw, 'user_id'):
                    qq_number = str(raw.user_id)
                elif hasattr(raw, 'sender') and hasattr(raw.sender, 'user_id'):
                    qq_number = str(raw.sender.user_id)
            
            if not qq_number:
                logger.error(f"无法获取QQ号，sender对象: {sender}")
                yield event.plain_result("无法获取您的QQ号，请稍后重试")
                return
            
            yield event.plain_result("正在生成 Maimai B50 图片，请稍候...")
            
            logger.info(f"[B50命令] 开始处理 QQ号: {qq_number}")
            
            # 1. 获取 Token
            token_result = await self.api_client.bot_get_token(qq_number)
            token = token_result.get("token")
            
            if not token:
                logger.error(f"[B50命令] 获取Token失败: {token_result}")
                yield event.plain_result("获取Token失败，请确认该QQ号已绑定。请前往 https://next.nageki-net.com/net/profile 绑定QQ账号")
                return
            
            logger.info(f"[B50命令] Token获取成功")
            
            # 2. 处理数据
            logger.info(f"[B50命令] 开始处理B50数据...")
            processor = RatingDataProcessor(self.api_client)
            # 使用新的处理 Maimai 数据的函数
            profile, categories = await processor.process_maimai_rating_data(token)
            profile = await self._apply_user_bio_to_profile(token, profile)
            logger.info(f"[B50命令] 数据处理完成: Profile={profile.get('userName')}, Categories={len(categories)}")
            
            current_user = await self._get_user_profile_for_browser(token, profile)

            logger.info(f"[B50命令] 开始生成 Maimai B50 网页截图")
            actual_path = await generate_maimai_rating_browser_image(
                "",
                profile,
                categories,
                api_client=self.api_client,
                current_user=current_user
            )
            logger.info(f"[B50命令] 图片生成完成: {actual_path}")
            
            # 4. 发送图片
            logger.info(f"[B50命令] 准备发送图片")
            yield self._image_result(event, actual_path)
            logger.info(f"[B50命令] 图片已发送")
            
        except aiohttp.ClientResponseError as e:
            logger.error(f"[B50命令] HTTP错误: 状态码={e.status}, 消息={e.message}")
            if e.status == 401:
                yield event.plain_result(f"认证失败：请检查 BOT_API_KEY 是否正确，或该QQ号未绑定。请前往 https://next.nageki-net.com/net/profile 绑定QQ账号")
            else:
                yield event.plain_result(f"请求失败：服务器返回错误 {e.status}")
        except RuntimeError as e:
            logger.error(f"生成图片错误: {e}", exc_info=True)
            yield event.plain_result(f"线上 Maimai B50 截图生成失败: {str(e)}")
        except Exception as e:
            logger.error(f"B50命令处理出错: {e}", exc_info=True)
            yield event.plain_result(f"发生错误: {str(e)}")

    async def _handle_maimai_profile_command(self, event: AstrMessageEvent):
        """处理 Maimai 资料命令：nageki maiprofile"""
        try:
            if not self.api_client.bot_api_key:
                yield event.plain_result(
                    "未配置 BOT_API_KEY，无法使用 QQ 机器人功能。\n"
                    "请在 AstrBot 插件配置中填写 BOT_API_KEY。"
                )
                return

            qq_number, sender = await self._get_sender_qq(event)
            if not qq_number:
                logger.error(f"无法获取QQ号，sender对象: {sender}")
                yield event.plain_result("无法获取您的QQ号，请稍后重试")
                return

            yield event.plain_result("正在获取 Maimai 资料，请稍候...")
            logger.info(f"[Maimai资料命令] 开始处理 QQ号: {qq_number}")

            token_result = await self.api_client.bot_get_token(qq_number)
            token = token_result.get("token")
            if not token:
                logger.error(f"[Maimai资料命令] 获取Token失败: {token_result}")
                yield event.plain_result("获取Token失败，请确认该QQ号已绑定。请前往 https://next.nageki-net.com/net/profile 绑定QQ账号")
                return

            profile = await self.api_client.get_maimai_profile(token)
            current_user = await self._get_user_profile_for_browser(token, profile)
            logger.info(f"[Maimai资料命令] 资料获取完成: {profile.get('userName')}")

            image_url = await generate_maimai_profile_browser_image(
                "",
                profile,
                api_client=self.api_client,
                current_user=current_user
            )
            yield self._image_result(event, image_url)

        except NagekiApiException as e:
            logger.error(f"[Maimai资料命令] Bot API错误: {e.status} - {e.message}")
            yield event.plain_result(self._format_bot_token_error(e))
        except aiohttp.ClientResponseError as e:
            logger.error(f"[Maimai资料命令] HTTP错误: 状态码={e.status}, 消息={e.message}")
            if e.status == 401:
                yield event.plain_result("认证失败：请检查 BOT_API_KEY 是否正确，或该QQ号未绑定。")
            else:
                yield event.plain_result(f"查询失败：服务器返回错误 {e.status}")
        except RuntimeError as e:
            logger.error(f"[Maimai资料命令] 生成图片错误: {e}", exc_info=True)
            yield event.plain_result(f"线上 Maimai 资料截图生成失败: {str(e)}")
        except Exception as e:
            logger.error(f"[Maimai资料命令] 处理出错: {e}", exc_info=True)
            yield event.plain_result(f"查询时发生错误: {str(e)}")

    async def _handle_health_command(self, event: AstrMessageEvent):
        """处理健康检查命令：nageki health"""
        try:
            if not self.api_client.bot_api_key:
                yield event.plain_result(
                    "未配置 BOT_API_KEY，无法使用QQ机器人功能。\n"
                    "请在 AstrBot 插件配置中填写 BOT_API_KEY。"
                )
                return
            
            yield event.plain_result("正在检查服务状态，请稍候...")
            
            result = await self.api_client.bot_health_check()
            
            status = result.get("status", "unknown")
            timestamp = result.get("timestamp", "未知")
            version = result.get("version", "未知")
            
            yield event.plain_result(
                f"✅ 服务状态：{status}\n"
                f"版本：{version}\n"
                f"时间：{timestamp}"
            )
            
        except aiohttp.ClientResponseError as e:
            if e.status == 401:
                yield event.plain_result(f"认证失败：请检查 BOT_API_KEY 是否正确")
            else:
                yield event.plain_result(f"健康检查失败：服务器返回错误 {e.status}")
        except Exception as e:
            logger.error(f"健康检查命令处理出错: {e}", exc_info=True)
            yield event.plain_result(f"健康检查时发生错误: {str(e)}")
    
    async def terminate(self):
        """插件销毁"""
        try:
            await browser_pool.shutdown()
        except Exception as e:
            logger.warning(f"关闭共享浏览器失败: {e}")
        logger.info("NagekiBot 插件已卸载")
