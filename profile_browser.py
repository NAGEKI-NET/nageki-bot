import asyncio
import html
import logging
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, Tuple

logger = logging.getLogger(__name__)


def _find_chrome_path() -> str | None:
    candidates = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return None


def _level_exp_requirement(level: int) -> int:
    if 0 <= level <= 9:
        return 200
    if 10 <= level <= 19:
        return 400
    if 20 <= level <= 29:
        return 600
    if 30 <= level <= 39:
        return 800
    if 40 <= level <= 49:
        return 1000
    if 50 <= level <= 59:
        return 1200
    if 60 <= level <= 69:
        return 1400
    if 70 <= level <= 79:
        return 1600
    if 80 <= level <= 89:
        return 1800
    return 2000


def _exp_progress(level: int, total_exp: int) -> Tuple[int, int, float]:
    level = min(level or 0, 99)
    used = 0
    for lv in range(level):
        used += _level_exp_requirement(lv)
    current_exp = max(0, total_exp - used)
    required = _level_exp_requirement(level)
    current_exp = min(current_exp, required)
    progress = (current_exp / required * 100) if required else 0
    return current_exp, required, progress


def _avg_score(profile: Dict[str, Any], sum_key: str, count_key: str) -> str:
    score = int(profile.get(sum_key, 0) or 0)
    count = int(profile.get(count_key, 0) or 0)
    if count <= 0:
        return "0"
    return f"{score // count:,}"


def _format_rating(profile: Dict[str, Any]) -> Tuple[str, str]:
    new_rating = profile.get("newPlayerRating")
    new_highest = profile.get("newHighestRating")
    current = (
        f"{new_rating / 1000:.3f}"
        if new_rating
        else f"{profile.get('playerRating', 0) / 100:.2f}"
    )
    highest = (
        f"{new_highest / 1000:.3f}"
        if new_highest
        else f"{profile.get('highestRating', 0) / 100:.2f}"
    )
    return current, highest


def _render_profile_html(profile: Dict[str, Any], api_client) -> str:
    card_id = str(int(profile.get("cardId", 0) or 0)).zfill(6)
    avatar_url = f"{api_client.cdn_base_url}/web/assets/ongeki/card/UI_Card_Icon_{card_id}.webp"
    chara_url = f"{api_client.cdn_base_url}/web/assets/ongeki/card/UI_Card_Chara_{card_id}.webp"

    current_rating, highest_rating = _format_rating(profile)
    current_exp, required_exp, progress = _exp_progress(
        int(profile.get("level", 0) or 0),
        int(profile.get("exp", 0) or 0),
    )
    signature = html.escape(
        (profile.get("profileContent") or "").strip() or "这个玩家还没有设置个性签名。"
    )
    username = html.escape(profile.get("userName", "Unknown"))

    tech_items = [
        ("Basic", _avg_score(profile, "sumTechBasicHighScore", "playedMusicCountBasic"), int(profile.get("playedMusicCountBasic", 0) or 0), "basic"),
        ("Advanced", _avg_score(profile, "sumTechAdvancedHighScore", "playedMusicCountAdvanced"), int(profile.get("playedMusicCountAdvanced", 0) or 0), "advanced"),
        ("Expert", _avg_score(profile, "sumTechExpertHighScore", "playedMusicCountExpert"), int(profile.get("playedMusicCountExpert", 0) or 0), "expert"),
        ("Master", _avg_score(profile, "sumTechMasterHighScore", "playedMusicCountMaster"), int(profile.get("playedMusicCountMaster", 0) or 0), "master"),
        ("Lunatic", _avg_score(profile, "sumTechLunaticHighScore", "playedMusicCountLunatic"), int(profile.get("playedMusicCountLunatic", 0) or 0), "lunatic"),
        ("Total", _avg_score(profile, "sumTechHighScore", "playedMusicCountTotal"), int(profile.get("playedMusicCountTotal", 0) or 0), "total"),
    ]
    tech_cards = "\n".join(
        f"""
        <div class="tech-item {variant}">
          <div class="tech-score">{score}</div>
          <div class="tech-label">{label}</div>
          <div class="tech-count">{count} 首</div>
        </div>
        """
        for label, score, count, variant in tech_items
    )

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>ONGEKI Profile</title>
  <style>
    :root {{
      --bg: #f8fafc;
      --card: #ffffff;
      --line: #dbe4f0;
      --text: #111827;
      --subtle: #6b7280;
      --blue: #2563eb;
      --green: #16a34a;
      --orange: #ea580c;
      --purple: #9333ea;
      --red: #dc2626;
      --cyan: #0891b2;
    }}
    * {{ box-sizing: border-box; }}
    html, body {{ margin: 0; width: 1600px; height: 1280px; overflow: hidden; }}
    body {{
      background: var(--bg);
      color: var(--text);
      font-family: "Segoe UI", "Microsoft YaHei", "PingFang SC", "Hiragino Sans GB", sans-serif;
    }}
    .page {{ padding: 48px; width: 1600px; height: 1280px; }}
    .title {{ font-size: 58px; font-weight: 800; line-height: 1; margin: 20px 0 10px; }}
    .subtitle {{ font-size: 24px; color: var(--subtle); margin-bottom: 28px; }}
    .card {{
      background: var(--card);
      border: 1px solid var(--line);
      border-radius: 28px;
      box-shadow: 0 2px 8px rgba(15, 23, 42, 0.03);
    }}
    .main-card {{
      position: relative;
      min-height: 560px;
      padding: 36px;
      margin-bottom: 36px;
    }}
    .username {{ font-size: 48px; font-weight: 800; margin: 6px 0 30px; }}
    .hero {{
      position: absolute;
      top: 18px;
      right: 26px;
      width: 300px;
      height: 500px;
      border-radius: 24px;
      display: flex;
      align-items: center;
      justify-content: center;
      overflow: hidden;
    }}
    .hero img {{ width: 270px; height: 460px; object-fit: contain; }}
    .content {{ width: calc(100% - 340px); }}
    .avatar-row {{
      display: flex;
      align-items: center;
      gap: 24px;
      margin-bottom: 34px;
      padding-right: 8px;
    }}
    .avatar {{
      width: 96px;
      height: 96px;
      border-radius: 18px;
      border: 2px solid #d1d5db;
      object-fit: cover;
      flex: 0 0 auto;
    }}
    .exp-wrap {{ flex: 1; }}
    .exp-head {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 10px;
      font-size: 22px;
      color: var(--subtle);
    }}
    .exp-bar {{
      width: 100%;
      height: 16px;
      background: #e5e7eb;
      border-radius: 999px;
      overflow: hidden;
    }}
    .exp-fill {{
      height: 100%;
      width: {progress:.3f}%;
      background: linear-gradient(90deg, #3b82f6 0%, #7c3aed 100%);
      border-radius: 999px;
    }}
    .summary {{
      display: grid;
      grid-template-columns: minmax(0, 1.35fr) minmax(420px, 1fr);
      gap: 22px;
      align-items: stretch;
    }}
    .rating-box {{
      border-radius: 22px;
      padding: 24px 26px 22px;
      background: linear-gradient(135deg, rgba(219, 234, 254, 0.85) 0%, rgba(233, 213, 255, 0.75) 60%, rgba(252, 231, 243, 0.82) 100%);
    }}
    .rating-label {{ font-size: 28px; font-weight: 700; margin-bottom: 22px; }}
    .rating-line {{ display: flex; align-items: baseline; gap: 16px; }}
    .rating-value {{ font-size: 72px; line-height: 1; font-weight: 800; color: var(--blue); }}
    .rating-highest {{ font-size: 24px; color: var(--subtle); }}
    .stats-grid {{
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 14px;
    }}
    .stat {{
      min-height: 160px;
      min-width: 0;
      padding: 18px 14px;
      border-radius: 20px;
      display: flex;
      align-items: center;
      justify-content: center;
      text-align: center;
      overflow: hidden;
    }}
    .stat.level {{ background: #eff6ff; }}
    .stat.play {{ background: #f0fdf4; }}
    .stat.rank {{ background: #fff7ed; }}
    .stat-value {{
      font-size: 48px;
      font-weight: 900;
      line-height: 1;
      white-space: nowrap;
      letter-spacing: -0.03em;
    }}
    .stat.level .stat-value {{ color: var(--blue); }}
    .stat.play .stat-value {{ color: var(--green); }}
    .stat.rank .stat-value {{ color: var(--orange); }}
    .stat.level .stat-value {{ font-size: 64px; }}
    .stat.play .stat-value {{ font-size: 44px; }}
    .stat.rank .stat-value {{ font-size: 40px; }}
    .stat-label {{
      margin-top: 10px;
      font-size: 22px;
      font-weight: 700;
      color: var(--subtle);
      white-space: nowrap;
    }}
    .section-card {{ padding: 32px 36px; margin-bottom: 36px; }}
    .section-title {{ font-size: 34px; font-weight: 800; margin-bottom: 24px; }}
    .tech-grid {{
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 16px;
    }}
    .tech-item {{
      padding: 22px 16px 18px;
      border-radius: 18px;
      text-align: center;
    }}
    .tech-item.basic {{ background: #f0fdf4; }}
    .tech-item.advanced {{ background: #fffbeb; }}
    .tech-item.expert {{ background: #fdf2f8; }}
    .tech-item.master {{ background: #faf5ff; }}
    .tech-item.lunatic {{ background: #fef2f2; }}
    .tech-item.total {{ background: #ecfeff; }}
    .tech-score {{ font-size: 28px; font-weight: 900; margin-bottom: 4px; }}
    .tech-item.basic .tech-score {{ color: var(--green); }}
    .tech-item.advanced .tech-score {{ color: #ca8a04; }}
    .tech-item.expert .tech-score {{ color: var(--red); }}
    .tech-item.master .tech-score {{ color: var(--purple); }}
    .tech-item.lunatic .tech-score {{ color: var(--red); }}
    .tech-item.total .tech-score {{ color: var(--cyan); }}
    .tech-label {{ font-size: 16px; font-weight: 700; color: var(--subtle); }}
    .tech-count {{ font-size: 14px; color: var(--subtle); margin-top: 2px; }}
    .signature-box {{
      background: #f9fafb;
      border-radius: 16px;
      padding: 20px 22px;
      font-size: 24px;
      color: #374151;
      min-height: 78px;
      display: flex;
      align-items: center;
      white-space: pre-wrap;
      word-break: break-word;
    }}
  </style>
</head>
<body>
  <div class="page">
    <div class="title">个人资料</div>
    <div class="subtitle">查看您的游戏资料</div>

    <div class="card main-card">
      <div class="hero"><img src="{html.escape(chara_url)}" alt="character" /></div>
      <div class="content">
        <div class="username">{username}</div>
        <div class="avatar-row">
          <img class="avatar" src="{html.escape(avatar_url)}" alt="avatar" />
          <div class="exp-wrap">
            <div class="exp-head">
              <span>经验值</span>
              <span>{current_exp}/{required_exp}</span>
            </div>
            <div class="exp-bar"><div class="exp-fill"></div></div>
          </div>
        </div>

        <div class="summary">
          <div class="rating-box">
            <div class="rating-label">当前评分</div>
            <div class="rating-line">
              <div class="rating-value">{current_rating}</div>
              <div class="rating-highest">(最高: {highest_rating})</div>
            </div>
          </div>
          <div class="stats-grid">
            <div class="stat level">
              <div>
                <div class="stat-value">{int(profile.get("level", 0) or 0)}</div>
                <div class="stat-label">等级</div>
              </div>
            </div>
            <div class="stat play">
              <div>
                <div class="stat-value">{int(profile.get("playCount", 0) or 0):,}</div>
                <div class="stat-label">游玩次数</div>
              </div>
            </div>
            <div class="stat rank">
              <div>
                <div class="stat-value">#{html.escape(str(profile.get("userRanking", "N/A")))}</div>
                <div class="stat-label">排名</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div class="card section-card">
      <div class="section-title">技术分统计</div>
      <div class="tech-grid">
        {tech_cards}
      </div>
    </div>

    <div class="card section-card">
      <div class="section-title">个性签名</div>
      <div class="signature-box">{signature}</div>
    </div>
  </div>
</body>
</html>
"""


async def generate_profile_browser_image(
    output_path: str,
    profile: Dict[str, Any],
    api_client,
) -> str:
    chrome_path = _find_chrome_path()
    if not chrome_path:
        raise RuntimeError("未找到可用的 Chrome/Edge 浏览器。")

    output_file = Path(output_path)
    plugin_dir = output_file.parent.parent
    temp_dir = plugin_dir / "cache" / "browser"
    temp_dir.mkdir(parents=True, exist_ok=True)

    html_path = temp_dir / "profile_render.html"
    profile_dir = temp_dir / "chrome_profile"
    profile_dir.mkdir(parents=True, exist_ok=True)

    html_path.write_text(
        _render_profile_html(profile, api_client),
        encoding="utf-8",
    )

    html_uri = html_path.resolve().as_uri()
    output_abs = str(output_file.resolve())

    script_path = temp_dir / "render_profile.ps1"
    ps_literal = lambda s: str(s).replace("'", "''")
    script_path.write_text(
        "\n".join(
            [
                f"$chrome = '{ps_literal(chrome_path)}'",
                f"$userDataDir = '{ps_literal(profile_dir)}'",
                f"$output = '{ps_literal(output_abs)}'",
                f"$html = '{ps_literal(html_uri)}'",
                "& $chrome "
                + "--headless=new "
                + "--disable-gpu "
                + "--hide-scrollbars "
                + "--disable-breakpad "
                + "--disable-crash-reporter "
                + "--no-first-run "
                + "--no-default-browser-check "
                + '--user-data-dir="$userDataDir" '
                + '--screenshot="$output" '
                + "--window-size=1600,1280 "
                + '"$html"',
            ]
        ),
        encoding="utf-8",
    )
    cmd = [
        r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script_path),
    ]

    def _run():
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
        )

    proc = await asyncio.to_thread(_run)
    await asyncio.sleep(0.2)
    if output_file.exists():
        return output_abs
    if proc.returncode != 0:
        raise RuntimeError(
            "浏览器截图失败: "
            f"stdout={proc.stdout.strip()} "
            f"stderr={proc.stderr.strip()}"
        )
    if not output_file.exists():
        raise RuntimeError("浏览器截图未生成输出文件。")
    return output_abs
