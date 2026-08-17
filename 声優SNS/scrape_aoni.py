import argparse
import html
import json
import re
from pathlib import Path
from pprint import pprint

import requests
from bs4 import BeautifulSoup


AGENCY_NAME = "青二プロダクション"
PROFILE_URL = "https://www.aoni.co.jp/search/fujii-yukiyo.html"
OUTPUT_PATH = Path(__file__).resolve().parent / "fujii_yukiyo_data.json"
HEADERS = {
    "User-Agent": "VoiceActorStudyScraper/1.0 (educational use)",
}
APPEARANCE_CATEGORIES = {"アニメ", "ゲーム", "洋画", "ラジオ", "テレビ", "その他"}


def normalize_text(text: str) -> str:
    """全角空白や改行を整理し、単語間の空白を1つにする。"""
    return re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()


def extract_name(soup: BeautifulSoup) -> str:
    """プロフィール見出しから声優名を取得する。"""
    heading = soup.select_one("h1 dt")
    if heading is None:
        raise ValueError("声優名の見出しが見つかりません。")
    return normalize_text(heading.get_text(" ", strip=True))


def format_appearance_entry(cells: list[str]) -> str:
    """青二の表形式を 作品（役名など） の表記へ寄せる。"""
    cells = [normalize_text(cell) for cell in cells if normalize_text(cell)]
    if not cells:
        return ""
    if len(cells) == 1:
        return cells[0]

    title = cells[0]
    detail = " / ".join(cells[1:])
    return f"{title}（{detail}）" if detail else title


def extract_appearances(soup: BeautifulSoup) -> dict[str, list[str]]:
    """出演作品をカテゴリごとに取得する。"""
    appearances: dict[str, list[str]] = {}

    for heading in soup.select("h3.cmntitle02"):
        category = normalize_text(heading.get_text(" ", strip=True))
        if category not in APPEARANCE_CATEGORIES:
            continue

        table_block = heading.find_next_sibling("div", class_="detailtable02")
        if table_block is None:
            continue

        entries = []
        for row in table_block.select("tr"):
            cells = [cell.get_text(" ", strip=True) for cell in row.find_all("td")]
            entry = format_appearance_entry(cells)
            if entry and entry not in entries:
                entries.append(entry)

        if entries:
            appearances[category] = entries

    if not appearances:
        raise ValueError("出演歴を1件も取得できませんでした。")
    return appearances


def classify_voice_sample(title: str, sample_url: str) -> str:
    """青二のボイスサンプル名から分類名を決める。"""
    normalized_title = normalize_text(title)
    filename = Path(sample_url).name.lower()

    if normalized_title in {"名前", "氏名"} or "name" in filename:
        return "クレジット"
    if "ナレーション" in normalized_title or "_na" in filename:
        return "ナレーション"
    if "セリフ" in normalized_title:
        return "セリフ"
    return "サンプル"


def extract_voice_sample_groups(html_text: str) -> dict[str, list[str]]:
    """jPlayerPlaylist内のtitle/mp3からボイスサンプルURLを取得する。"""
    voice_sample_groups: dict[str, list[str]] = {}
    pattern = re.compile(
        r'title\s*:\s*"(?P<title>.*?)"\s*,\s*mp3\s*:\s*"(?P<mp3>.*?)"',
        re.DOTALL,
    )

    for match in pattern.finditer(html_text):
        title = normalize_text(html.unescape(match.group("title")))
        sample_url = normalize_text(html.unescape(match.group("mp3")))
        if not sample_url:
            continue

        group_name = classify_voice_sample(title, sample_url)
        voice_sample_groups.setdefault(group_name, [])
        if sample_url not in voice_sample_groups[group_name]:
            voice_sample_groups[group_name].append(sample_url)

    return {
        group_name: sample_urls
        for group_name, sample_urls in voice_sample_groups.items()
        if sample_urls
    }


def flatten_voice_sample_groups(voice_sample_groups: dict[str, list[str]]) -> list[str]:
    """分類済みボイスサンプルを、保存互換用の一次元リストにする。"""
    return [
        sample_url
        for sample_urls in voice_sample_groups.values()
        for sample_url in sample_urls
    ]


def scrape_aoni_profile(url: str) -> dict:
    """青二プロダクションの声優プロフィールを1回の通信で取得する。"""
    response = requests.get(url, headers=HEADERS, timeout=(5, 20))
    response.raise_for_status()
    response.encoding = response.apparent_encoding

    soup = BeautifulSoup(response.text, "html.parser")
    name = extract_name(soup)
    voice_sample_groups = extract_voice_sample_groups(response.text)
    return {
        name: {
            "agency": AGENCY_NAME,
            "source_url": response.url,
            "appearances": extract_appearances(soup),
            "voice_sample_groups": voice_sample_groups,
            "voice_samples": flatten_voice_sample_groups(voice_sample_groups),
        }
    }


def save_json(data: dict, output_path: Path) -> None:
    """既存の手入力データを残しつつ、取得結果を日本語のまま保存する。"""
    if output_path.exists():
        with output_path.open("r", encoding="utf-8") as file:
            existing_data = json.load(file)
    else:
        existing_data = {}

    for actor_name, actor_data in data.items():
        existing_actor_data = existing_data.get(actor_name, {})
        existing_data[actor_name] = {
            **existing_actor_data,
            **actor_data,
        }

    with output_path.open("w", encoding="utf-8") as file:
        json.dump(existing_data, file, ensure_ascii=False, indent=4)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="青二プロダクション公式プロフィールから声優情報をスクレイピングします。"
    )
    parser.add_argument(
        "url",
        nargs="?",
        default=PROFILE_URL,
        help=f"対象プロフィールURL（省略時: {PROFILE_URL}）",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=OUTPUT_PATH,
        help=f"保存先JSON（省略時: {OUTPUT_PATH}）",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        scraped_data = scrape_aoni_profile(args.url)
        output_path = args.output.resolve()
        save_json(scraped_data, output_path)
    except requests.exceptions.Timeout as error:
        print(f"エラー: 公式サイトへの接続がタイムアウトしました: {error}")
        raise SystemExit(1) from error
    except requests.exceptions.RequestException as error:
        print(f"エラー: 公式サイトの取得に失敗しました: {error}")
        raise SystemExit(1) from error
    except (ValueError, AttributeError, TypeError) as error:
        print(f"エラー: HTMLの解析に失敗しました: {error}")
        raise SystemExit(1) from error
    except OSError as error:
        print(f"エラー: JSONファイルの保存に失敗しました: {error}")
        raise SystemExit(1) from error

    pprint(scraped_data, sort_dicts=False)
    print(f"\nJSON保存先: {output_path}")


if __name__ == "__main__":
    main()
