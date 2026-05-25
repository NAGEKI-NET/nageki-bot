"""Rating 数据处理模块，将 API 返回的原始数据转换为绘制所需的结构。"""
from typing import Dict, Any, List, Optional

from .rating_calculator import RatingCalculator


class RatingDataProcessor:
    """Rating 数据处理器。"""

    def __init__(self, api_client, music_list: Optional[List[Dict[str, Any]]] = None):
        self.api_client = api_client
        self.music_list = music_list or []
        self.music_cache = {}

        if self.music_list:
            for music in self.music_list:
                self.music_cache[music.get("id")] = music

    async def load_music_list(self, token: Optional[str] = None):
        """加载 Ongeki 音乐列表。"""
        if self.music_list:
            return

        self.music_list = await self.api_client.get_music_list(token=token)
        self.music_cache = {}
        for music in self.music_list:
            self.music_cache[music.get("id")] = music

    async def load_maimai_music_list(self, token: Optional[str] = None):
        """加载 Maimai 音乐列表。"""
        if self.music_list:
            return

        self.music_list = await self.api_client.get_maimai_music_list(token=token)
        self.music_cache = {}
        for music in self.music_list:
            self.music_cache[music.get("id")] = music

    def calculate_ratings(self, items: List[Dict[str, Any]]):
        """计算 Ongeki Rating。"""
        for item in items:
            music_info = item.get("musicInfo")
            if not music_info:
                continue

            level = item.get("level", 0)
            score = item.get("value", 0)
            is_pscore = item.get("isPScore", False)
            platinum_score_star = item.get("platinumScoreStar") if is_pscore else None

            all_break = item.get("isAllBreak", False) or item.get("allBreak", False)
            full_bell = item.get("isFullBell", False) or item.get("fullBell", False)

            result = RatingCalculator.calculate_rating(
                music_info,
                level,
                score,
                is_pscore=is_pscore,
                platinum_score_star=platinum_score_star,
                all_break=all_break,
                full_bell=full_bell,
            )

            item["chartConstant"] = result["chartConstant"]
            item["ratingBonus"] = result["ratingBonus"]
            item["rating"] = result["rating"]

    async def process_maimai_rating_data(self, token: str):
        """处理 Maimai B50 数据。"""
        await self.load_maimai_music_list(token)

        profile = await self.api_client.get_maimai_profile(token)
        old_items_raw = await self.api_client.get_maimai_rating_bestlist(token)
        new_items_raw = await self.api_client.get_maimai_rating_newlist(token)

        def normalize_maimai_item(item: Dict[str, Any]) -> Dict[str, Any]:
            music_id = item.get("musicId", 0)
            level = item.get("level", 0)
            achievement = item.get("achievement", 0)

            music_info = self.music_cache.get(music_id)
            if not music_info:
                music_info = {
                    "id": music_id,
                    "name": item.get("musicName"),
                    "artistName": item.get("artistName"),
                    "genre": item.get("genre"),
                    "releaseVersion": item.get("releaseVersion"),
                }

            chart_constant = RatingCalculator.get_chart_constant(music_info, level)
            rating = (
                RatingCalculator.calculate_maimai_rating(chart_constant, achievement)
                if chart_constant > 0
                else 0
            )

            return {
                "musicId": music_id,
                "level": level,
                "value": achievement,
                "achievement": achievement,
                "chartConstant": chart_constant,
                "rating": rating,
                "musicInfo": music_info,
                "fullMusicInfo": {"music": music_info} if music_info else None,
                "comboStatus": item.get("comboStatus"),
                "syncStatus": item.get("syncStatus"),
                "scoreRank": item.get("scoreRank"),
                "deluxscoreMax": item.get("deluxscoreMax"),
                "isDxMusic": item.get("isDxMusic"),
            }

        old_items = [normalize_maimai_item(item) for item in old_items_raw][:35]
        new_items = [normalize_maimai_item(item) for item in new_items_raw][:15]

        categories = [
            {
                "title": "Standard (Old)",
                "items": old_items,
                "averageRating": RatingCalculator.calculate_average_rating(old_items),
                "totalRating": RatingCalculator.calculate_total_rating(old_items),
                "averageAchievement": (sum(item.get("achievement", 0) for item in old_items) / len(old_items) / 10000) if old_items else 0,
            },
            {
                "title": "New (DX)",
                "items": new_items,
                "averageRating": RatingCalculator.calculate_average_rating(new_items),
                "totalRating": RatingCalculator.calculate_total_rating(new_items),
                "averageAchievement": (sum(item.get("achievement", 0) for item in new_items) / len(new_items) / 10000) if new_items else 0,
            },
        ]

        return profile, categories

    def parse_rating_category(self, property_value: str, is_pscore: bool = False) -> List[Dict[str, Any]]:
        """解析 Ongeki Rating 分类字符串。"""
        if not property_value or "," not in property_value:
            return []

        items = []
        for record in property_value.split(","):
            if not record:
                continue

            values = record.split(":")
            if len(values) < 4:
                continue

            try:
                music_id = int(values[0])
                level = int(values[1])
                score = int(values[3])
            except (ValueError, IndexError):
                continue

            item: Dict[str, Any] = {
                "musicId": music_id,
                "level": level,
                "value": score,
                "rating": 0,
                "musicInfo": None,
                "fullMusicInfo": None,
                "isPScore": is_pscore,
            }

            if is_pscore:
                item["platinumScoreMax"] = int(values[4]) if len(values) > 4 else 0
                item["platinumScoreStar"] = int(values[5]) if len(values) > 5 else 0

            music_info = self.music_cache.get(music_id)
            if music_info:
                item["musicInfo"] = music_info
                item["fullMusicInfo"] = {"music": music_info}

            items.append(item)

        return items

    async def process_rating_data(self, token: str):
        """处理完整的 Ongeki Rating 数据。"""
        await self.load_music_list(token)

        profile = await self.api_client.get_profile_with_token(token)

        b50_items_raw = await self.api_client.get_rating_bestlist(token)
        new10_items_raw = await self.api_client.get_rating_newlist(token)
        pscore_items_raw = await self.api_client.get_rating_pscorelist(token)

        def normalize_item(raw_item: Dict[str, Any], is_pscore: bool = False):
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

            if raw_item.get("musicName"):
                item["_apiMusicName"] = raw_item.get("musicName")
            if raw_item.get("artistName"):
                item["_apiArtistName"] = raw_item.get("artistName")

            return item

        b50_items = [normalize_item(item) for item in b50_items_raw]
        new10_items = [normalize_item(item) for item in new10_items_raw]
        pscore_items = [normalize_item(item, is_pscore=True) for item in pscore_items_raw]

        for group in (b50_items, new10_items, pscore_items):
            for item in group:
                music_id = item.get("musicId")
                if not music_id:
                    continue

                music_info = self.music_cache.get(music_id)
                if music_info:
                    item["musicInfo"] = music_info
                    item["fullMusicInfo"] = {"music": music_info}
                elif item.get("_apiMusicName"):
                    item["musicInfo"] = {
                        "id": music_id,
                        "name": item["_apiMusicName"],
                        "artistName": item.get("_apiArtistName", ""),
                    }
                    item["fullMusicInfo"] = {"music": item["musicInfo"]}

        self.calculate_ratings(b50_items)
        self.calculate_ratings(new10_items)
        self.calculate_ratings(pscore_items)

        categories = [
            {
                "title": "B50",
                "description": "BEST 50",
                "items": b50_items,
                "totalRating": RatingCalculator.calculate_total_rating(b50_items),
                "averageRating": RatingCalculator.calculate_average_rating(b50_items),
            },
            {
                "title": "NEW10",
                "description": "NEW 10",
                "items": new10_items,
                "totalRating": RatingCalculator.calculate_total_rating(new10_items),
                "averageRating": RatingCalculator.calculate_average_rating(new10_items),
            },
            {
                "title": "PSCORE 50",
                "description": "PLATINUM SCORE 50",
                "items": pscore_items,
                "totalRating": RatingCalculator.calculate_total_rating(pscore_items),
                "averageRating": RatingCalculator.calculate_average_rating(pscore_items),
            },
        ]

        return profile, categories
