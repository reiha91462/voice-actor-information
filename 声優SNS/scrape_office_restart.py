import argparse
import json
import re
from pathlib import Path
from pprint import pprint

import requests
from bs4 import BeautifulSoup


AGENCY_NAME = "オフィス リスタート"
PROFILE_URL = "https://endless-glory.com/talent_ak/"
OUTPUT_PATH = Path(__file__).resolve().parent / "koshimizu_ami_data.json"
HEADERS = {
    "User-Agent": "VoiceActorStudyScraper/1.0 (educational use)",
}


def normalize_text(text: str) -> str:
    """全角空白や改行を整理し、単語間の空白を1つにする。"""
    return re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()


def extract_name(soup: BeautifulSoup) -> str:
    """プロフィール見出しから声優名を取得する。"""
    heading = soup.select_one(".profile__intro__name")
    if heading is None:
        heading = soup.find(["h1", "h2"])
    if heading is None:
        raise ValueError("声優名の見出しが見つかりません。")

    name_text = normalize_text(heading.get_text(" ", strip=True))
    name_text = re.sub(r"声優\s*", "", name_text)
    name_text = re.sub(r"AMI\s+KOSHIMIZU", "", name_text, flags=re.IGNORECASE)
    return normalize_text(name_text)


def split_br_entries(element) -> list[str]:
    """br区切りの出演歴をリストに変換する。"""
    entries = []
    for text in element.stripped_strings:
        entry = normalize_text(text)
        if entry and entry not in entries:
            entries.append(entry)
    return entries


def extract_appearances(soup: BeautifulSoup) -> dict[str, list[str]]:
    """出演作品をカテゴリごとに取得する。"""
    appearances: dict[str, list[str]] = {}

    for category_tag in soup.select("dt.profile__appearance__cnt__main__ttl"):
        category = normalize_text(category_tag.get_text(" ", strip=True))
        entries_tag = category_tag.find_next_sibling("dd")
        if entries_tag is None:
            continue

        entries = split_br_entries(entries_tag)
        if entries:
            appearances[category] = entries

    if not appearances:
        raise ValueError("出演歴を1件も取得できませんでした。")
    return appearances


def scrape_office_restart_profile(url: str) -> dict:
    """オフィス リスタートの声優プロフィールを1回の通信で取得する。"""
    response = requests.get(url, headers=HEADERS, timeout=(5, 20))
    response.raise_for_status()
    response.encoding = response.apparent_encoding

    soup = BeautifulSoup(response.text, "html.parser")
    name = extract_name(soup)
    return {
        name: {
            "agency": AGENCY_NAME,
            "source_url": response.url,
            "appearances": extract_appearances(soup),
            "voice_sample_groups": {},
            "voice_samples": [],
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
        description="オフィス リスタート公式プロフィールから声優情報をスクレイピングします。"
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
        scraped_data = scrape_office_restart_profile(args.url)
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
