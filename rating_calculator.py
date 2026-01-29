"""Rating 计算逻辑，对应前端 rating.component.ts 中的计算函数。"""
from typing import Dict, Any, Optional, List


class RatingCalculator:
    """Rating 计算器"""
    
    @staticmethod
    def get_chart_constant(music: Dict[str, Any], difficulty_index: int) -> float:
        """
        获取谱面定数
        
        Args:
            music: 音乐信息字典，包含 level0, level1, level2, level3, level4 字段
            difficulty_index: 难度索引 (0=Basic, 1=Advanced, 2=Expert, 3=Master, 10=Lunatic)
        
        Returns:
            谱面定数（浮点数）
        """
        level_key_map = {
            0: "level0",
            1: "level1",
            2: "level2",
            3: "level3",
            10: "level4"  # Lunatic
        }
        
        level_key = level_key_map.get(difficulty_index)
        if not level_key:
            return 0.0
        
        level_string = music.get(level_key, "")
        if not level_string:
            return 0.0
        
        # 处理逗号格式 "14,7" -> "14.7"
        formatted = level_string.replace(",", ".")
        try:
            return float(formatted)
        except ValueError:
            return 0.0
    
    @staticmethod
    def calculate_rating_bonus(score: int) -> float:
        """
        计算 Rating 加成
        
        新版本公式: Rating = 谱面定数 + 分数加成 + 各种 Bonus
        - 分数加成: 最高 2.0 (SSS+)
        - SSS Bonus: +0.2 (score >= 1,000,000)
        - SSS+ Bonus: +0.3 (score >= 1,007,500)
        - FB Bonus: +0.1 (需要额外数据，暂不计算)
        
        最大总加成: 2.0 + 0.3 + 0.1 = 2.4 (SSS+ 且 FB)
        
        Args:
            score: 分数
        
        Returns:
            加成值（浮点数）
        """
        if score < 970000:
            return 0.0  # 不到 S 的统统算 0
        
        base_bonus = 0.0  # 分数加成 (最高2.0)
        rank_bonus = 0.0  # 评级加成 (SSS: +0.2, SSS+: +0.3)
        
        # 计算分数加成
        if score >= 1007500:
            base_bonus = 2.0
            rank_bonus = 0.3  # SSS+ Bonus
        elif score >= 1000000:
            # 1000000 - 1007500 : 1.5 - 2.0
            base_bonus = 1.5 + (score - 1000000) / 7500 * 0.5
            rank_bonus = 0.2  # SSS Bonus
        elif score >= 990000:
            # 990000 - 1000000 : 1.0 - 1.5
            base_bonus = 1.0 + (score - 990000) / 10000 * 0.5
        elif score >= 970000:
            # 970000 - 990000 : 0.0 - 1.0
            base_bonus = (score - 970000) / 20000
        
        # 总加成 = 分数加成 + 评级加成
        # 注: FB Bonus (+0.1) 需要额外数据，暂不计算
        return base_bonus + rank_bonus
    
    @staticmethod
    def calculate_pscore_bonus(star: int) -> float:
        """
        计算 PScore 的 Bonus
        ★5: +0.0, ★4: -1.5, ★3: -3.0, ★2: -4.5, ★1: -6.0
        
        Args:
            star: 白金星数 (0-5)
        
        Returns:
            Bonus 值
        """
        bonus_map = {
            5: 0.0,
            4: -1.5,
            3: -3.0,
            2: -4.5,
            1: -6.0
        }
        return bonus_map.get(star, -6.0)  # 0星或未知默认为 -6.0
    
    @staticmethod
    def calculate_rating(
        music: Dict[str, Any],
        difficulty_index: int,
        score: int,
        is_pscore: bool = False,
        platinum_score_star: Optional[int] = None,
        all_break: bool = False,
        full_bell: bool = False
    ) -> Dict[str, float]:
        """
        计算单曲 Rating
        
        Args:
            music: 音乐信息
            difficulty_index: 难度索引
            score: 分数
            is_pscore: 是否为 PScore 项目
            platinum_score_star: PScore 白金星数（仅当 is_pscore=True 时有效）
            all_break: 是否 All Break（普通 Rating +0.35）
            full_bell: 是否 Full Bell（普通 Rating +0.05）
        
        Returns:
            包含 chartConstant, ratingBonus, rating 的字典
        """
        chart_constant = RatingCalculator.get_chart_constant(music, difficulty_index)
        
        if is_pscore:
            # PScore Rating = (谱面定数 + Bonus) / 750
            # 50首 ☆5 曲目 ≈ 1.0 总 Rating
            # PScore 不适用 AB/FB
            pscore_bonus = RatingCalculator.calculate_pscore_bonus(platinum_score_star or 0)
            rating_bonus = pscore_bonus
            raw_rating = (chart_constant + pscore_bonus) / 750
            rating = round(raw_rating * 1000) / 1000  # PScore 保留3位小数
        else:
            # 普通 Rating 计算
            # 总加成 = 分数加成 + AB加成 + FB加成
            score_bonus = RatingCalculator.calculate_rating_bonus(score)
            ab_bonus = 0.35 if all_break else 0.0
            fb_bonus = 0.05 if full_bell else 0.0
            
            # 修正浮点误差
            total_bonus = round((score_bonus + ab_bonus + fb_bonus) * 100) / 100
            rating_bonus = total_bonus
            
            raw_rating = chart_constant + total_bonus
            rating = round(raw_rating * 100) / 100  # 保留2位小数
        
        return {
            "chartConstant": chart_constant,
            "ratingBonus": rating_bonus,
            "rating": rating
        }
    
    @staticmethod
    def calculate_total_rating(items: List[Dict[str, Any]]) -> float:
        """计算总 Rating"""
        return sum(item.get("rating", 0) for item in items)
    
    @staticmethod
    def calculate_average_rating(items: List[Dict[str, Any]]) -> float:
        """计算平均 Rating"""
        if not items:
            return 0.0
        return RatingCalculator.calculate_total_rating(items) / len(items)
    
    @staticmethod
    def format_value(value: int) -> str:
        """
        格式化数值，添加千位分隔符（日本格式：每4位一个逗号）
        例如：1008265 -> 100,8265
        """
        string_value = str(value)
        
        # 如果包含小数点，只取整数部分
        if "." in string_value:
            string_value = string_value.split(".")[0]
        
        # 使用日本数字格式：每4位数字添加逗号（从右往左）
        reversed_str = string_value[::-1]
        formatted = ",".join(
            reversed_str[i:i+4] for i in range(0, len(reversed_str), 4)
        )
        return formatted[::-1]
    
    @staticmethod
    def format_rating(rating: float, is_pscore: bool = False) -> str:
        """
        格式化 Rating 显示
        
        Args:
            rating: Rating 值
            is_pscore: 是否为 PScore
        
        Returns:
            格式化后的字符串
        """
        if is_pscore:
            return f"+{rating:.3f}"
        return f"{rating:.2f}"
    
    @staticmethod
    def format_bonus(bonus: float) -> str:
        """
        格式化 bonus 显示 (保留最多2位小数，带正号)
        """
        val = round(bonus * 100) / 100
        formatted = f"+{val:.2f}".rstrip("0").rstrip(".")
        return formatted
