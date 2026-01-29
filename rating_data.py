"""Rating 数据处理模块，将 API 返回的原始数据转换为绘制所需的结构。"""
from typing import Dict, Any, List, Optional
from .rating_calculator import RatingCalculator


class RatingDataProcessor:
    """Rating 数据处理器"""
    
    def __init__(self, api_client, music_list: Optional[List[Dict[str, Any]]] = None):
        """
        初始化数据处理器
        
        Args:
            api_client: API 客户端
            music_list: 音乐列表（可选，如果提供则使用，否则从 API 获取）
        """
        self.api_client = api_client
        self.music_list = music_list or []
        self.music_cache = {}
        
        # 构建音乐缓存
        if self.music_list:
            for music in self.music_list:
                self.music_cache[music.get("id")] = music
    
    async def load_music_list(self):
        """加载音乐列表"""
        if not self.music_list:
            self.music_list = await self.api_client.get_music_list()
            self.api_client.save_music_cache(self.music_list)
            # 重新构建缓存
            self.music_cache = {}
            for music in self.music_list:
                self.music_cache[music.get("id")] = music
        else:
            # 尝试从缓存加载
            cached = self.api_client.load_music_cache()
            if cached:
                self.music_list = cached
                self.music_cache = {}
                for music in self.music_list:
                    self.music_cache[music.get("id")] = music
    
    def parse_rating_category(self, property_value: str, is_pscore: bool = False) -> List[Dict[str, Any]]:
        """
        解析 Rating 分类数据
        
        Args:
            property_value: API 返回的 propertyValue 字符串
            is_pscore: 是否为 PScore 数据
        
        Returns:
            解析后的项目列表
        """
        if not property_value or "," not in property_value:
            return []
        
        items = []
        records = property_value.split(",")
        
        for record in records:
            if not record:
                continue
            
            values = record.split(":")
            if len(values) < 4:
                continue
            
            try:
                music_id = int(values[0])
                level = int(values[1])
                # rom_version_code = int(values[2])  # 暂不使用
                score = int(values[3])
                
                item: Dict[str, Any] = {
                    "musicId": music_id,
                    "level": level,
                    "value": score,
                    "rating": 0,
                    "musicInfo": None,
                    "fullMusicInfo": None
                }
                
                if is_pscore:
                    item["isPScore"] = True
                    item["platinumScoreMax"] = int(values[4]) if len(values) > 4 else 0
                    item["platinumScoreStar"] = int(values[5]) if len(values) > 5 else 0
                else:
                    item["isPScore"] = False
                
                # 查找音乐信息
                music_info = self.music_cache.get(music_id)
                if music_info:
                    item["musicInfo"] = music_info
                    item["fullMusicInfo"] = {"music": music_info}
                
                items.append(item)
            except (ValueError, IndexError):
                continue
        
        return items
    
    def calculate_ratings(self, items: List[Dict[str, Any]]):
        """计算所有项目的 Rating"""
        for item in items:
            music_info = item.get("musicInfo")
            if not music_info:
                continue
            
            level = item.get("level", 0)
            score = item.get("value", 0)
            is_pscore = item.get("isPScore", False)
            platinum_score_star = item.get("platinumScoreStar") if is_pscore else None
            
            # 获取 AB/FB 标志
            all_break = item.get("isAllBreak", False) or item.get("allBreak", False)
            full_bell = item.get("isFullBell", False) or item.get("fullBell", False)
            
            result = RatingCalculator.calculate_rating(
                music_info,
                level,
                score,
                is_pscore=is_pscore,
                platinum_score_star=platinum_score_star,
                all_break=all_break,
                full_bell=full_bell
            )
            
            item["chartConstant"] = result["chartConstant"]
            item["ratingBonus"] = result["ratingBonus"]
            item["rating"] = result["rating"]
    
    async def process_rating_data(self, token: str):
        """
        处理完整的 Rating 数据
        
        Args:
            token: JWT Token
            
        Returns:
            (profile, categories) 元组
        """
        # 加载音乐列表
        await self.load_music_list()
        
        # 使用Token获取玩家资料
        profile = await self.api_client.get_profile_with_token(token)
        
        # 使用新的API端点获取三个分类数据（直接返回列表）
        b50_items_raw = await self.api_client.get_rating_bestlist(token)
        new10_items_raw = await self.api_client.get_rating_newlist(token)
        pscore_items_raw = await self.api_client.get_rating_pscorelist(token)
        
        # 规范化字段名（API 返回 difficultId/score，内部使用 level/value）
        def normalize_item(raw_item, is_pscore=False):
            """将 API 返回的字段名映射到内部格式"""
            item = {
                "musicId": raw_item.get("musicId"),
                "level": raw_item.get("difficultId", raw_item.get("level", 0)),
                "value": raw_item.get("score", raw_item.get("value", 0)),
                "isAllBreak": raw_item.get("isAllBreak", False),
                "isFullBell": raw_item.get("isFullBell", False),
                "isFullCombo": raw_item.get("isFullCombo", False),
                "isPScore": is_pscore,
            }
            
            if is_pscore:
                item["platinumScoreMax"] = raw_item.get("platinumScoreMax", 0)
                item["platinumScoreStar"] = raw_item.get("platinumScoreStar", 0)
            
            # 如果 API 直接返回了 musicName 和 artistName，暂存起来
            if raw_item.get("musicName"):
                item["_apiMusicName"] = raw_item.get("musicName")
            if raw_item.get("artistName"):
                item["_apiArtistName"] = raw_item.get("artistName")
            
            return item
        
        b50_items = [normalize_item(item) for item in b50_items_raw]
        new10_items = [normalize_item(item) for item in new10_items_raw]
        pscore_items = [normalize_item(item, is_pscore=True) for item in pscore_items_raw]
        
        # 为每个项目添加音乐信息
        for item in b50_items:
            music_id = item.get("musicId")
            if music_id:
                music_info = self.music_cache.get(music_id)
                if music_info:
                    item["musicInfo"] = music_info
                    item["fullMusicInfo"] = {"music": music_info}
                elif item.get("_apiMusicName"):
                    # 如果缓存中没有，但 API 返回了名称，创建临时 music_info
                    item["musicInfo"] = {
                        "id": music_id,
                        "name": item["_apiMusicName"],
                        "artistName": item.get("_apiArtistName", "")
                    }
                    item["fullMusicInfo"] = {"music": item["musicInfo"]}
        
        for item in new10_items:
            music_id = item.get("musicId")
            if music_id:
                music_info = self.music_cache.get(music_id)
                if music_info:
                    item["musicInfo"] = music_info
                    item["fullMusicInfo"] = {"music": music_info}
                elif item.get("_apiMusicName"):
                    item["musicInfo"] = {
                        "id": music_id,
                        "name": item["_apiMusicName"],
                        "artistName": item.get("_apiArtistName", "")
                    }
                    item["fullMusicInfo"] = {"music": item["musicInfo"]}
        
        for item in pscore_items:
            music_id = item.get("musicId")
            if music_id:
                music_info = self.music_cache.get(music_id)
                if music_info:
                    item["musicInfo"] = music_info
                    item["fullMusicInfo"] = {"music": music_info}
                elif item.get("_apiMusicName"):
                    item["musicInfo"] = {
                        "id": music_id,
                        "name": item["_apiMusicName"],
                        "artistName": item.get("_apiArtistName", "")
                    }
                    item["fullMusicInfo"] = {"music": item["musicInfo"]}
        
        # 计算 Rating
        self.calculate_ratings(b50_items)
        self.calculate_ratings(new10_items)
        self.calculate_ratings(pscore_items)
        
        # 构建分类
        categories = [
            {
                "title": "B50",
                "description": "BEST 50",
                "items": b50_items,
                "totalRating": RatingCalculator.calculate_total_rating(b50_items),
                "averageRating": RatingCalculator.calculate_average_rating(b50_items)
            },
            {
                "title": "NEW10",
                "description": "NEW 10",
                "items": new10_items,
                "totalRating": RatingCalculator.calculate_total_rating(new10_items),
                "averageRating": RatingCalculator.calculate_average_rating(new10_items)
            },
            {
                "title": "PSCORE 50",
                "description": "PLATINUM SCORE 50",
                "items": pscore_items,
                "totalRating": RatingCalculator.calculate_total_rating(pscore_items),
                "averageRating": RatingCalculator.calculate_average_rating(pscore_items)
            }
        ]
        
        return profile, categories
