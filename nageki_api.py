"""Nageki-Net API 客户端，用于获取游戏数据和图片资源。"""
import os
import json
import aiohttp
import asyncio
import logging
from typing import Optional, Dict, Any, List
from urllib.parse import urljoin, urlencode

logger = logging.getLogger(__name__)


class NagekiApiException(Exception):
    def __init__(self, status: int, message: str, raw_response: str = ""):
        self.status = status
        self.message = message
        self.raw_response = raw_response
        super().__init__(f"API Error {status}: {message}")

class NagekiApiClient:
    """Nageki-Net API 客户端"""
    
    def __init__(
        self,
        api_base_url: Optional[str] = None,
        cdn_base_url: Optional[str] = None,
        token: Optional[str] = None,
        cache_dir: Optional[str] = None,
        bot_api_key: Optional[str] = None,
        bot_api_url: Optional[str] = None
    ):
        """
        初始化 API 客户端
        
        Args:
            api_base_url: API 服务器地址（默认从环境变量或配置文件读取）
            cdn_base_url: CDN 服务器地址（默认从环境变量或配置文件读取）
            token: JWT token（用于认证）
            cache_dir: 缓存目录（用于存储图片和音乐数据）
            bot_api_key: QQ机器人API密钥（用于QQ机器人API认证）
            bot_api_url: QQ机器人API服务器地址
        """
        # 默认 API 地址（需要解码，这里先使用占位符，实际使用时需要配置）
        self.api_base_url = api_base_url or os.getenv("NAGEKI_API_URL", "https://nageki-net.com/")
        self.cdn_base_url = cdn_base_url or os.getenv("NAGEKI_CDN_URL", "https://cdn-nageki-next.sys-all.com.cn")
        self.token = token or os.getenv("NAGEKI_TOKEN")
        self.cache_dir = cache_dir
        
        # QQ机器人API配置（测试阶段默认使用localhost和测试密钥）
        # 默认使用测试密钥，方便测试
        self.bot_api_key = bot_api_key or os.getenv("BOT_API_KEY", "THIS_IS_A_SAMPLE_API_KEY_REPLACE_ME")
        # 默认使用localhost:8080，方便测试
        self.bot_api_url = bot_api_url or os.getenv("BOT_API_URL", "http://localhost:8080")
        
        # 确保 API URL 以 / 结尾
        if not self.api_base_url.endswith("/"):
            self.api_base_url += "/"
        # CDN URL 不以 / 结尾
        if self.cdn_base_url.endswith("/"):
            self.cdn_base_url = self.cdn_base_url.rstrip("/")
        
        # 创建缓存目录
        if self.cache_dir:
            os.makedirs(os.path.join(self.cache_dir, "images"), exist_ok=True)
            os.makedirs(os.path.join(self.cache_dir, "music"), exist_ok=True)
    
    def _get_headers(self) -> Dict[str, str]:
        """获取请求头（包含认证 token）"""
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers
    
    def _get_bot_headers(self) -> Dict[str, str]:
        """获取QQ机器人API请求头（包含API密钥）"""
        headers = {}
        # 只有在有数据时才设置 Content-Type
        # 但为了兼容性，我们总是设置
        headers["Content-Type"] = "application/json"
        if self.bot_api_key:
            headers["X-Bot-Api-Key"] = self.bot_api_key
        else:
            logger.warning("[Bot API] bot_api_key 未设置！")
        return headers
    
    async def _request(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
        max_retries: int = 3,
        timeout: int = 60
    ) -> Any:
        """发送 HTTP 请求，带重试机制和超时设置"""
        url = urljoin(self.api_base_url, path)
        
        # 超时配置
        timeout_obj = aiohttp.ClientTimeout(total=timeout, connect=10)
        
        last_error = None
        for attempt in range(max_retries):
            try:
                async with aiohttp.ClientSession(timeout=timeout_obj) as session:
                    kwargs = {"headers": self._get_headers()}
                    if params:
                        url_with_params = url + "?" + urlencode(params)
                    else:
                        url_with_params = url
                    if data:
                        kwargs["json"] = data
                    
                    logger.info(f"[Net API] 请求 {method} {url_with_params} (尝试 {attempt + 1}/{max_retries})")
                    
                    async with session.request(method, url_with_params, **kwargs) as resp:
                        resp.raise_for_status()
                        
                        # 先读取完整响应文本，避免传输错误
                        response_text = await resp.text()
                        
                        # 解析 JSON
                        try:
                            result = json.loads(response_text) if response_text else {}
                            logger.info(f"[Net API] 请求成功，响应长度: {len(response_text)} 字符")
                            return result
                        except json.JSONDecodeError as e:
                            logger.error(f"[Net API] JSON解析失败: {e}")
                            logger.error(f"[Net API] 响应前500字符: {response_text[:500]}")
                            raise
                            
            except (aiohttp.ClientPayloadError, aiohttp.ClientError, asyncio.TimeoutError) as e:
                last_error = e
                logger.warning(f"[Net API] 请求失败 (尝试 {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    # 等待后重试，指数退避
                    wait_time = 2 ** attempt
                    logger.info(f"[Net API] {wait_time}秒后重试...")
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"[Net API] 所有重试均失败")
                    raise
            except Exception as e:
                logger.error(f"[Net API] 未预期的错误: {e}")
                raise
        
        # 如果所有重试都失败，抛出最后一个错误
        if last_error:
            raise last_error
    
    async def _bot_request(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None
    ) -> Any:
        """发送QQ机器人API HTTP 请求"""
        # 确保bot_api_url不以/结尾，测试阶段默认使用localhost:8080
        base_url = self.bot_api_url.rstrip("/") if self.bot_api_url else "http://localhost:8080"
        url = urljoin(base_url + "/", path)
        
        headers = self._get_bot_headers()
        
        # 记录请求信息（隐藏API密钥的完整内容）
        api_key_preview = self.bot_api_key[:10] + "..." if self.bot_api_key and len(self.bot_api_key) > 10 else (self.bot_api_key or "None")
        logger.info(f"[Bot API] 请求: {method} {url}")
        logger.info(f"[Bot API] 请求头: {dict((k, v[:20] + '...' if k == 'X-Bot-Api-Key' and len(v) > 20 else v) for k, v in headers.items())}")
        if params:
            logger.info(f"[Bot API] 请求参数: {params}")
        if data:
            logger.info(f"[Bot API] 请求体: {data}")
        logger.info(f"[Bot API] API密钥预览: {api_key_preview}")
        logger.info(f"[Bot API] API密钥长度: {len(self.bot_api_key) if self.bot_api_key else 0}")
        
        async with aiohttp.ClientSession() as session:
            kwargs = {"headers": headers}
            if params:
                url += "?" + urlencode(params)
            if data:
                kwargs["json"] = data
            
            try:
                async with session.request(method, url, **kwargs) as resp:
                    status = resp.status
                    logger.info(f"[Bot API] 响应状态码: {status}")
                    logger.info(f"[Bot API] 响应头: {dict(resp.headers)}")
                    
                    # 先读取响应内容（用于日志和解析）
                    response_text = await resp.text()
                    logger.info(f"[Bot API] 响应内容: {response_text[:500]}")  # 只记录前500字符
                    
                    # 检查状态码
                    if status >= 400:
                        logger.error(f"[Bot API] HTTP错误响应: {status}")
                        logger.error(f"[Bot API] 错误响应体: {response_text}")
                        
                        # 尝试解析错误信息
                        err_msg = f"HTTP Error {status}"
                        try:
                            err_json = json.loads(response_text)
                            if "message" in err_json:
                                err_msg = err_json["message"]
                            elif "error" in err_json:
                                err_msg = err_json["error"]
                        except:
                            pass
                            
                        raise NagekiApiException(status, err_msg, response_text)
                    
                    # 尝试解析JSON
                    try:
                        result = json.loads(response_text) if response_text else {}
                        logger.info(f"[Bot API] 响应JSON: {result}")
                        return result
                    except json.JSONDecodeError as e:
                        logger.error(f"[Bot API] 解析JSON响应失败: {e}")
                        logger.error(f"[Bot API] 原始响应: {response_text}")
                        # 如果不是JSON，返回文本内容
                        return {"message": response_text}
                        
            except NagekiApiException:
                raise
            except aiohttp.ClientResponseError as e:
                # 理论上不会走到这里，因为我们处理了 status >= 400的情况
                # 但以防万一
                logger.error(f"[Bot API] HTTP错误: 状态码={e.status}, 消息={e.message}")
                if e.status == 401:
                    logger.error(f"[Bot API] 认证失败 - 请检查API密钥是否正确")
                raise
            except Exception as e:
                logger.error(f"[Bot API] 请求异常: {type(e).__name__}: {e}", exc_info=True)
                raise
    
    async def get_profile(self) -> Dict[str, Any]:
        """获取玩家资料"""
        return await self._request("GET", "api/game/ongeki/profile")
    
    async def get_general_with_token(self, token: str, key: str) -> Dict[str, Any]:
        """
        使用Token获取通用数据（调用Net API）
        
        Args:
            token: JWT Token
            key: 查询键
        """
        # 使用 bot_api_url 作为基础URL
        base_url = self.bot_api_url.rstrip("/") if self.bot_api_url else "http://localhost:8080"
        url = urljoin(base_url + "/", "api/game/ongeki/general")
        
        # 设置请求头，使用Bearer Token认证
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}"
        }
        
        params = {"key": key}
        
        logger.info(f"[Net API] 请求: GET {url} params={params}")
        logger.info(f"[Net API] 请求头: {dict((k, v[:20] + '...' if k == 'Authorization' and len(v) > 20 else v) for k, v in headers.items())}")
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, params=params) as resp:
                status = resp.status
                logger.info(f"[Net API] 响应状态码: {status}")
                
                # 读取响应内容
                response_text = await resp.text()
                logger.info(f"[Net API] 响应内容: {response_text[:500]}")
                
                if status >= 400:
                    logger.error(f"[Net API] HTTP错误响应: {status}")
                    logger.error(f"[Net API] 错误响应体: {response_text}")
                
                resp.raise_for_status()
                
                # 解析JSON
                try:
                    result = json.loads(response_text) if response_text else {}
                    logger.info(f"[Net API] 响应JSON: {result}")
                    return result
                except json.JSONDecodeError as e:
                    logger.error(f"[Net API] 解析JSON响应失败: {e}")
                    logger.error(f"[Net API] 原始响应: {response_text}")
                    raise
    
    async def get_maimai_profile(self, token: str) -> Dict[str, Any]:
        """获取 Maimai 玩家资料"""
        base_url = self.api_base_url.rstrip("/")
        url = urljoin(base_url + "/", "api/game/maimai2/profile")
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}"
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                resp.raise_for_status()
                return await resp.json()

    async def get_maimai_music_list(self) -> List[Dict[str, Any]]:
        """获取 Maimai 音乐列表"""
        logger.info("[Net API] 开始获取 Maimai 音乐列表...")
        # Maimai 音乐列表 API 路径推测为 api/game/maimai2/data/musicList
        resp = await self._request("GET", "api/game/maimai2/data/musicList", timeout=120)
        if isinstance(resp, list):
            logger.info(f"[Net API] Maimai 音乐列表获取成功，共 {len(resp)} 首")
            return resp
        result = resp.get("data", [])
        logger.info(f"[Net API] Maimai 音乐列表获取成功，共 {len(result)} 首")
        return result

    async def get_maimai_general(self, token: str, key: str) -> Dict[str, Any]:
        """
        获取 Maimai 通用数据
        """
        base_url = self.api_base_url.rstrip("/")
        url = urljoin(base_url + "/", "api/game/maimai2/general")
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}"
        }
        
        params = {"key": key}
        
        logger.info(f"[Net API] 请求: GET {url} params={params}")
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, params=params) as resp:
                resp.raise_for_status()
                response_text = await resp.text()
                try:
                    result = json.loads(response_text) if response_text else {}
                    logger.info(f"[Net API] Maimai general 响应: {len(str(result))} 字符")
                    return result
                except json.JSONDecodeError:
                    return {}

    def get_maimai_jacket_url(self, music_id: int) -> str:
        """获取 Maimai 音乐封面 URL"""
        # 假设 ID 是数字，需要补零到 4 位 (或者 5 位? Maimai ID 经常是 5 位，如 10001)
        # 暂时尝试 6 位? Maimai DX 通常是 1xxxx.
        # 按照 Nageki 的习惯，通常是 padded string.
        # 观察 Ongeki 是 4 位。
        # Maimai 封面通常路径是 .../maimai2/jacket/UI_Jacket_XXXXXX.webp ?
        # 让我们先假设是不补零或者补零到6位。Maimai ID范围很大。
        # 暂时使用 padded 6位 (000001) 或者 5位。
        # 标准 Maimai ID: 1 ~ 1000+ (Standard), 10001 ~ (DX).
        # 还是先假设直接使用 ID 字符串，或者 padded 6位。
        # 这里的 cdn_base_url 是 "https://cdn-nageki-next.sys-all.com.cn"
        # 访问 web/assets/maimai2/jacket/UI_Jacket_{id}.png ?
        # 参照 Ongeki: web/assets/ongeki/jacket/UI_Jacket_{padded_id}_{size}.webp
        
        # 简单处理：先转字符串，不补零试试，或者补零到6位。
        # 大部分 Maimai 资源库习惯用 6 位。
        padded_id = str(music_id).zfill(6)
        # 注意 Maimai 只有一种封面尺寸通常
        url = f"{self.cdn_base_url}/web/assets/maimai2/jacket/UI_Jacket_{padded_id}.webp"
        return url

    
    def get_jacket_url(self, music_id: int, size: str = "S", game: str = "ongeki") -> str:
        """获取音乐封面 URL"""
        if game == "maimai":
             return self.get_maimai_jacket_url(music_id)
             
        padded_id = str(music_id).zfill(4)
        url = f"{self.cdn_base_url}/web/assets/ongeki/jacket/UI_Jacket_{padded_id}_{size}.webp"
        # logger.debug(f"[图片] 生成封面URL: {url}")
        return url
    
    async def download_image(self, url: str, save_path: Optional[str] = None, timeout: int = 10) -> bytes:
        """下载图片"""
        timeout_obj = aiohttp.ClientTimeout(total=timeout)
        async with aiohttp.ClientSession(timeout=timeout_obj) as session:
            try:
                async with session.get(url) as resp:
                    resp.raise_for_status()
                    data = await resp.read()
                    
                    if save_path:
                        os.makedirs(os.path.dirname(save_path), exist_ok=True)
                        with open(save_path, "wb") as f:
                            f.write(data)
                    
                    return data
            except Exception as e:
                logger.warning(f"[图片] 下载失败 URL={url}, Error={e}")
                raise
    
    async def get_jacket_image(
        self,
        music_id: int,
        size: str = "S",
        cache: bool = True,
        game: str = "ongeki"
    ) -> Optional[bytes]:
        """获取音乐封面图片（带缓存）"""
        url = self.get_jacket_url(music_id, size, game)
        
        if cache and self.cache_dir:
            cache_path = os.path.join(
                self.cache_dir,
                "images",
                f"{game}_jacket_{music_id}_{size}.webp"
            )
            if os.path.exists(cache_path):
                with open(cache_path, "rb") as f:
                    return f.read()
            
            try:
                data = await self.download_image(url, cache_path)
                return data
            except Exception:
                return None
        
        try:
            return await self.download_image(url)
        except Exception:
            return None
    
    def save_music_cache(self, music_list: List[Dict[str, Any]]):
        """保存音乐列表到本地缓存"""
        if not self.cache_dir:
            return
        
        cache_path = os.path.join(self.cache_dir, "music", "music_list.json")
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(music_list, f, ensure_ascii=False, indent=2)
    
    def load_music_cache(self) -> Optional[List[Dict[str, Any]]]:
        """从本地缓存加载音乐列表"""
        if not self.cache_dir:
            return None
        
        cache_path = os.path.join(self.cache_dir, "music", "music_list.json")
        if os.path.exists(cache_path):
            with open(cache_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return None
    
    def get_music_by_id(self, music_id: int, music_list: Optional[List[Dict[str, Any]]] = None) -> Optional[Dict[str, Any]]:
        """根据 ID 查找音乐信息"""
        if music_list is None:
            music_list = self.load_music_cache() or []
        
        for music in music_list:
            if music.get("id") == music_id:
                return music
        return None
    
    # ========== QQ机器人API方法 ==========
    
    async def bot_health_check(self) -> Dict[str, Any]:
        """健康检查"""
        return await self._bot_request("GET", "api/bot/health")
    
    async def bot_bind(self, qq_number: str, code: str) -> Dict[str, Any]:
        """
        验证绑定码
        
        Args:
            qq_number: QQ号码
            code: 绑定码
        """
        return await self._bot_request("POST", "api/bot/bind", data={
            "qqNumber": qq_number,
            "code": code
        })
    
    async def bot_check_bind(self, qq_number: str) -> Dict[str, Any]:
        """
        检查绑定状态
        
        Args:
            qq_number: QQ号码
        """
        return await self._bot_request("GET", "api/bot/checkBind", params={
            "qqNumber": qq_number
        })
    
    async def bot_get_token(self, qq_number: str) -> Dict[str, Any]:
        """
        获取JWT Token（核心接口）
        
        Args:
            qq_number: QQ号码
        
        Returns:
            包含 token, username, email, aimeId 的字典
        """
        return await self._bot_request("GET", "api/bot/token", params={
            "qqNumber": qq_number
        })
    
    async def get_profile_with_token(self, token: str) -> Dict[str, Any]:
        """
        使用Token获取玩家资料（调用Net API）
        
        Args:
            token: JWT Token
        
        使用 bot_api_url 作为基础URL，调用 /api/game/ongeki/profile
        """
        # 使用 api_base_url 作为基础URL (确保请求发送到 Net API)
        base_url = self.api_base_url.rstrip("/")
        url = urljoin(base_url + "/", "api/game/ongeki/profile")
        
        # 设置请求头，使用Bearer Token认证
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}"
        }
        
        logger.info(f"[Net API] 请求: GET {url}")
        logger.info(f"[Net API] 请求头: {dict((k, v[:20] + '...' if k == 'Authorization' and len(v) > 20 else v) for k, v in headers.items())}")
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                status = resp.status
                logger.info(f"[Net API] 响应状态码: {status}")
                
                # 读取响应内容
                response_text = await resp.text()
                logger.info(f"[Net API] 响应内容: {response_text[:500]}")
                
                if status >= 400:
                    logger.error(f"[Net API] HTTP错误响应: {status}")
                    logger.error(f"[Net API] 错误响应体: {response_text}")
                
                resp.raise_for_status()
                
                # 解析JSON
                try:
                    result = json.loads(response_text) if response_text else {}
                    logger.info(f"[Net API] 响应JSON: {result}")
                    return result
                except json.JSONDecodeError as e:
                    logger.error(f"[Net API] 解析JSON响应失败: {e}")
                    logger.error(f"[Net API] 原始响应: {response_text}")
                    raise
    
    async def get_rating_bestlist(self, token: str) -> List[Dict[str, Any]]:
        """
        使用Token获取最佳成绩列表（调用Net API）
        
        Args:
            token: JWT Token
        
        Returns:
            最佳成绩列表
        """
        base_url = self.api_base_url.rstrip("/")
        url = urljoin(base_url + "/", "api/game/ongeki/rating/bestlist")
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}"
        }
        
        logger.info(f"[Net API] 请求: GET {url}")
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                status = resp.status
                logger.info(f"[Net API] 响应状态码: {status}")
                
                response_text = await resp.text()
                logger.info(f"[Net API] 响应内容前500字符: {response_text[:500]}")
                
                if status >= 400:
                    logger.error(f"[Net API] HTTP错误响应: {status}")
                    logger.error(f"[Net API] 错误响应体: {response_text}")
                
                resp.raise_for_status()
                
                try:
                    result = json.loads(response_text) if response_text else []
                    logger.info(f"[Net API] 获取到 {len(result)} 条最佳成绩")
                    return result
                except json.JSONDecodeError as e:
                    logger.error(f"[Net API] 解析JSON响应失败: {e}")
                    logger.error(f"[Net API] 原始响应: {response_text}")
                    raise
    
    async def get_rating_newlist(self, token: str) -> List[Dict[str, Any]]:
        """
        使用Token获取新歌最佳成绩列表（调用Net API）
        
        Args:
            token: JWT Token
        
        Returns:
            新歌最佳成绩列表
        """
        base_url = self.api_base_url.rstrip("/")
        url = urljoin(base_url + "/", "api/game/ongeki/rating/newlist")
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}"
        }
        
        logger.info(f"[Net API] 请求: GET {url}")
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                status = resp.status
                logger.info(f"[Net API] 响应状态码: {status}")
                
                response_text = await resp.text()
                logger.info(f"[Net API] 响应内容前500字符: {response_text[:500]}")
                
                if status >= 400:
                    logger.error(f"[Net API] HTTP错误响应: {status}")
                    logger.error(f"[Net API] 错误响应体: {response_text}")
                
                resp.raise_for_status()
                
                try:
                    result = json.loads(response_text) if response_text else []
                    logger.info(f"[Net API] 获取到 {len(result)} 条新歌成绩")
                    return result
                except json.JSONDecodeError as e:
                    logger.error(f"[Net API] 解析JSON响应失败: {e}")
                    logger.error(f"[Net API] 原始响应: {response_text}")
                    raise
    
    async def get_rating_pscorelist(self, token: str) -> List[Dict[str, Any]]:
        """
        使用Token获取白金分数列表（调用Net API）
        
        Args:
            token: JWT Token
        
        Returns:
            白金分数列表
        """
        base_url = self.api_base_url.rstrip("/")
        url = urljoin(base_url + "/", "api/game/ongeki/rating/pscorelist")
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}"
        }
        
        logger.info(f"[Net API] 请求: GET {url}")
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                status = resp.status
                logger.info(f"[Net API] 响应状态码: {status}")
                
                response_text = await resp.text()
                logger.info(f"[Net API] 响应内容前500字符: {response_text[:500]}")
                
                if status >= 400:
                    logger.error(f"[Net API] HTTP错误响应: {status}")
                    logger.error(f"[Net API] 错误响应体: {response_text}")
                
                resp.raise_for_status()
                
                try:
                    result = json.loads(response_text) if response_text else []
                    logger.info(f"[Net API] 获取到 {len(result)} 条白金分数")
                    return result
                except json.JSONDecodeError as e:
                    logger.error(f"[Net API] 解析JSON响应失败: {e}")
                    logger.error(f"[Net API] 原始响应: {response_text}")
                    raise
    
    async def get_general_with_token(self, token: str, key: str) -> Dict[str, Any]:
        """
        使用Token获取通用数据（调用Net API）
        
        **已弃用**: 请使用新的专用方法:
        - get_rating_bestlist() 替代 key="new_rating_base_best_list"
        - get_rating_newlist() 替代 key="new_rating_base_best_new_list"
        - get_rating_pscorelist() 替代 key="new_rating_base_pscore_list"
        
        Args:
            token: JWT Token
            key: 查询键
        """
        # 使用 bot_api_url 作为基础URL
        base_url = self.bot_api_url.rstrip("/") if self.bot_api_url else "http://localhost:8080"
        url = urljoin(base_url + "/", "api/game/ongeki/general")
        
        # 设置请求头，使用Bearer Token认证
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}"
        }
        
        params = {"key": key}
        
        logger.info(f"[Net API] 请求: GET {url} params={params}")
        logger.info(f"[Net API] 请求头: {dict((k, v[:20] + '...' if k == 'Authorization' and len(v) > 20 else v) for k, v in headers.items())}")
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, params=params) as resp:
                status = resp.status
                logger.info(f"[Net API] 响应状态码: {status}")
                
                # 读取响应内容
                response_text = await resp.text()
                logger.info(f"[Net API] 响应内容: {response_text[:500]}")
                
                if status >= 400:
                    logger.error(f"[Net API] HTTP错误响应: {status}")
                    logger.error(f"[Net API] 错误响应体: {response_text}")
                
                resp.raise_for_status()
                
                # 解析JSON
                try:
                    result = json.loads(response_text) if response_text else {}
                    logger.info(f"[Net API] 响应JSON: {result}")
                    return result
                except json.JSONDecodeError as e:
                    logger.error(f"[Net API] 解析JSON响应失败: {e}")
                    logger.error(f"[Net API] 原始响应: {response_text}")
                    raise
