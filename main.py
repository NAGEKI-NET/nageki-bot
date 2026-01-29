from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
import os
import aiohttp

from .nageki_api import NagekiApiClient
from .rating_data import RatingDataProcessor
from .rating_canvas import generate_rating_canvas_image


@register("nageki-bot", "NagekiBot", "Nageki-Net Rating 查询插件，支持完整的 API 获取、图片获取、数据分析功能", "1.0.0")
class NagekiBot(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.api_client = None
        self._init_api_client()
    
    def _init_api_client(self):
        """初始化 API 客户端"""
        plugin_dir = os.path.dirname(__file__)
        cache_dir = os.path.join(plugin_dir, "cache")
        
        # 从配置或环境变量获取 API 地址和 token
        # 注意：实际使用时需要配置这些值
        api_url = os.getenv("NAGEKI_API_URL", "https://nageki-net.com/")
        cdn_url = os.getenv("NAGEKI_CDN_URL", "https://cdn-nageki-next.sys-all.com.cn")
        token = os.getenv("NAGEKI_TOKEN")  # 需要用户配置 JWT token
        
        # QQ机器人API配置（测试阶段默认使用localhost和测试密钥）
        # 默认使用测试密钥，方便测试
        bot_api_key = os.getenv("BOT_API_KEY", "HAO_CHI_JB_0_CM_HS7Kf2Q9Xl0WBZ8N3MVPY6R1UDCEe5j")
        # 默认使用localhost:8080，方便测试
        bot_api_url = os.getenv("BOT_API_URL", "https://nageki-net.com")
        
        logger.info(f"[初始化] BOT_API_KEY 来源: {'环境变量' if os.getenv('BOT_API_KEY') else '默认值'}")
        logger.info(f"[初始化] BOT_API_KEY 长度: {len(bot_api_key) if bot_api_key else 0}")
        logger.info(f"[初始化] BOT_API_KEY 预览: {bot_api_key[:10] + '...' if bot_api_key and len(bot_api_key) > 10 else (bot_api_key or 'None')}")
        logger.info(f"[初始化] BOT_API_URL: {bot_api_url}")
        
        self.api_client = NagekiApiClient(
            api_base_url=api_url,
            cdn_base_url=cdn_url,
            token=token,
            cache_dir=cache_dir,
            bot_api_key=bot_api_key,
            bot_api_url=bot_api_url
        )
        
        logger.info(f"[初始化] API客户端已创建，bot_api_key已设置: {bool(self.api_client.bot_api_key)}")
    
    async def initialize(self):
        """插件初始化"""
        logger.info("NagekiBot 插件已初始化")
    
    @filter.event_message_type(filter.EventMessageType.ALL)
    async def reply_nageki(self, event: AstrMessageEvent):
        """处理各种命令"""
        message_str = event.message_str.strip()
        
        # 处理测试命令：test 或 /test
        if message_str == "/test" or message_str == "test":
            yield event.plain_result("在呢")
        # 处理绑定命令：nageki bind <绑定码>
        elif message_str.startswith("nageki bind "):
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
        elif message_str == "nageki rating":
            async for result in self._handle_rating_command(event):
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
                    "请在环境变量中设置 BOT_API_KEY。"
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
                    "请在环境变量中设置 BOT_API_KEY。"
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
                    "请在环境变量中设置 BOT_API_KEY。"
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
            
            # 记录API返回的完整数据，用于调试
            logger.info(f"[查询资料命令] Net API返回数据: {result}")
            logger.info(f"[查询资料命令] Net API返回数据的所有键: {list(result.keys()) if isinstance(result, dict) else 'Not a dict'}")
            
            # 格式化输出用户资料
            # 根据提供的JSON结构映射字段
            
            # Rating 处理: 
            # newPlayerRating: 19032 -> 19.032 (除以1000)
            # playerRating: 1490 -> 14.90 (除以100)
            
            new_rating = result.get('newPlayerRating')
            if new_rating:
                current_rating_str = f"{new_rating / 1000:.3f}"
            else:
                current_rating_str = f"{result.get('playerRating', 0) / 100:.2f}"
            
            new_max = result.get('newHighestRating')
            if new_max:
                max_rating_str = f"{new_max / 1000:.3f}"
            else:
                max_rating_str = f"{result.get('highestRating', 0) / 100:.2f}"
            
            # 排名处理
            ranking = result.get('userRanking', 0)
            total_players = result.get('player', 0)
            
            
            profile_text = (
                f"玩家名：{result.get('userName', username)}\n"
                f"等级：{result.get('level', 0)}\n"
                # f"转生次数：{result.get('reincarnationNum', 0)}\n" # JSON无此字段
                f"当前Rating：{current_rating_str}\n"
                f"最高Rating：{max_rating_str}\n"
                # f"战斗点数：{result.get('battlePoint', 0)}\n"
                f"总游玩次数：{result.get('playCount', 0)}\n"
                f"排名：{ranking}\n"
            )
            
            yield event.plain_result(profile_text)
            
        except aiohttp.ClientResponseError as e:
            logger.error(f"[查询资料命令] HTTP错误: 状态码={e.status}, 消息={e.message}")
            if e.status == 401:
                yield event.plain_result(f"认证失败：请检查 BOT_API_KEY 是否正确，或该QQ号未绑定")
            elif e.status == 404:
                yield event.plain_result(f"未找到该QQ号的绑定信息，请前往 https://next.nageki-net.com/net/profile 绑定QQ账号")
            else:
                yield event.plain_result(f"查询失败：服务器返回错误 {e.status}")
        except Exception as e:
            logger.error(f"查询资料命令处理出错: {e}", exc_info=True)
            yield event.plain_result(f"查询时发生错误: {str(e)}")
    
    async def _handle_rating_command(self, event: AstrMessageEvent):
        """处理 Rating 命令：nageki rating"""
        try:
            if not self.api_client.bot_api_key:
                yield event.plain_result(
                    "未配置 BOT_API_KEY，无法使用QQ机器人功能。\n"
                    "请在环境变量中设置 BOT_API_KEY。"
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
            logger.info(f"[Rating命令] 数据处理完成: Profile={profile.get('userName')}, Categories={len(categories)}")
            
            # 3. 生成图片
            plugin_dir = os.path.dirname(__file__)
            output_dir = os.path.join(plugin_dir, "assets")
            output_path = os.path.join(output_dir, "nageki_rating.png")
            
            logger.info(f"[Rating命令] 开始绘制图片: {output_path}")
            actual_path = await generate_rating_canvas_image(
                output_path,
                profile,
                categories,
                api_client=self.api_client
            )
            logger.info(f"[Rating命令] 图片绘制完成: {actual_path}")
            
            # 4. 发送图片
            logger.info(f"[Rating命令] 准备发送图片")
            yield event.image_result(actual_path)
            logger.info(f"[Rating命令] 图片已发送")
            
        except aiohttp.ClientResponseError as e:
            logger.error(f"[Rating命令] HTTP错误: 状态码={e.status}, 消息={e.message}")
            if e.status == 401:
                yield event.plain_result(f"认证失败：请检查 BOT_API_KEY 是否正确，或该QQ号未绑定。请前往 https://next.nageki-net.com/net/profile 绑定QQ账号")
            else:
                yield event.plain_result(f"请求失败：服务器返回错误 {e.status}")
        except RuntimeError as e:
            if "Pillow" in str(e):
                yield event.plain_result("当前环境未安装 pillow，无法绘制图片。")
            else:
                logger.error(f"生成图片错误: {e}", exc_info=True)
                yield event.plain_result(f"生成图片时发生错误: {str(e)}")
        except Exception as e:
            logger.error(f"Rating命令处理出错: {e}", exc_info=True)
            yield event.plain_result(f"发生错误: {str(e)}")

    async def _handle_health_command(self, event: AstrMessageEvent):
        """处理健康检查命令：nageki health"""
        try:
            if not self.api_client.bot_api_key:
                yield event.plain_result(
                    "未配置 BOT_API_KEY，无法使用QQ机器人功能。\n"
                    "请在环境变量中设置 BOT_API_KEY。"
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
        logger.info("NagekiBot 插件已卸载")
