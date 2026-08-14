import argparse
import json
import re
from pathlib import Path
from pprint import pprint

import requests
from bs4 import BeautifulSoup

try:
    from voice_sample_extractors import (
        extract_audio_tag_urls,
        extract_select_value_voice_sample_groups,
        flatten_voice_sample_groups,
    )
except ModuleNotFoundError:
    from .voice_sample_extractors import (
        extract_audio_tag_urls,
        extract_select_value_voice_sample_groups,
        flatten_voice_sample_groups,
    )


AGENCY_NAME = "インテンション"
PROFILE_URL = "https://intention-k.com/profile/nao_toyama"
OUTPUT_PATH = Path(__file__).resolve().parent / "toyama_nao_data.json"
HEADERS = {
    "User-Agent": "VoiceActorStudyScraper/1.0 (educational use)",
}
APPEARANCE_CATEGORIES = {
    "アニメ",
    "吹き替え",
    "ゲーム",
    "特撮",
    "ナレーション",
    "ラジオ",
}


def normalize_text(text: str) -> str:
    """全角空白や改行を整理し、単語間の空白を1つにする。"""
    return re.sub(r"\s+", " ", text).strip()


def extract_name(soup: BeautifulSoup) -> str:
    """プロフィール見出しから声優名を取得する。"""
    heading = soup.find("h2")
    if heading is None:
        raise ValueError("声優名の見出しが見つかりません。")
    first_span = heading.find("span")
    if first_span is not None:
        return normalize_text(first_span.get_text(" ", strip=True))
    return normalize_text(heading.get_text(" ", strip=True))


def extract_appearances(soup: BeautifulSoup) -> dict[str, list[str]]:
    """出演作品をカテゴリごとに取得する。"""
    career_appearances = extract_career_definition_list_appearances(soup)
    if career_appearances:
        return career_appearances

    appearances: dict[str, list[str]] = {}
    current_category = None

    for element in soup.find_all(["h3", "h4", "p", "ul"]):
        text = normalize_text(element.get_text(" ", strip=True))
        if text in APPEARANCE_CATEGORIES:
            current_category = text
            appearances.setdefault(current_category, [])
            continue

        if current_category is None:
            continue

        if element.name == "ul":
            for item in element.find_all("li", recursive=False):
                entry = normalize_text(item.get_text(" ", strip=True))
                if entry:
                    appearances[current_category].append(format_appearance_entry(entry))
        elif element.name == "p" and current_category == "ラジオ":
            if text and not text.startswith("2017年"):
                appearances[current_category].append(format_appearance_entry(text))

    appearances = {
        category: dedupe_preserve_order(entries)
        for category, entries in appearances.items()
        if entries
    }
    if not appearances:
        raise ValueError("出演歴を1件も取得できませんでした。")
    return appearances


def extract_career_definition_list_appearances(
    soup: BeautifulSoup,
) -> dict[str, list[str]]:
    """dt.profiledetail-Career_Media + dd形式の出演歴を取得する。"""
    appearances: dict[str, list[str]] = {}

    for category_tag in soup.select("dt.profiledetail-Career_Media"):
        category = normalize_text(category_tag.get_text(" ", strip=True))
        if category not in APPEARANCE_CATEGORIES:
            continue

        entries_tag = category_tag.find_next_sibling("dd")
        if entries_tag is None:
            continue

        entries = [
            format_appearance_entry(normalize_text(item.get_text(" ", strip=True)))
            for item in entries_tag.find_all("li")
            if normalize_text(item.get_text(" ", strip=True))
        ]
        entries = dedupe_preserve_order(entries)
        if entries:
            appearances[category] = entries

    return appearances


def format_appearance_entry(entry: str) -> str:
    """「作品」役名 の表記を 作品（役名）へ寄せる。"""
    entry = normalize_text(entry)
    match = re.match(r"^「(?P<title>.+)」(?P<role>.+)$", entry)
    if not match:
        return entry

    title = normalize_text(match.group("title"))
    role = normalize_text(match.group("role"))
    return f"{title}（{role}）" if role else title


def dedupe_preserve_order(items: list[str]) -> list[str]:
    """順序を保って重複を取り除く。"""
    deduped = []
    for item in items:
        if item not in deduped:
            deduped.append(item)
    return deduped


def extract_voice_sample_groups(soup: BeautifulSoup, base_url: str) -> dict[str, list[str]]:
    """select#audio_fileのoptionからボイスサンプルURLをカテゴリ別に取得する。"""
    return extract_select_value_voice_sample_groups(
        soup,
        base_url,
        select_selector="select#audio_file",
        url_template="/wp-content/themes/intention/media/sounds/profile/{value}.mp3",
    )


def extract_voice_samples(soup: BeautifulSoup, base_url: str) -> list[str]:
    """audio/sourceタグ、またはINTENTIONのselect形式からボイスサンプルURLを取得する。"""
    grouped_samples = extract_voice_sample_groups(soup, base_url)
    if grouped_samples:
        return [
            sample_url
            for sample_urls in grouped_samples.values()
            for sample_url in sample_urls
        ]

    return extract_audio_tag_urls(soup, base_url)


def scrape_intention_profile(url: str) -> dict:
    """INTENTIONの声優プロフィールを1回の通信で取得する。"""
    response = requests.get(url, headers=HEADERS, timeout=(5, 20))
    response.raise_for_status()

    soup = BeautifulSoup(response.content, "html.parser")
    name = extract_name(soup)
    voice_sample_groups = extract_voice_sample_groups(soup, response.url)
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
    """既存の手入力データを残しつつ、取得結果を日本語のまま読みやすく保存する。"""
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
        description="INTENTION公式プロフィールから声優情報をスクレイピングします。"
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
        scraped_data = scrape_intention_profile(args.url)
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
