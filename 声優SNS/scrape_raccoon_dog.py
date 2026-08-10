import json
import re
from pathlib import Path
from pprint import pprint
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from agency_rules import classify_voice_sample_by_agency


AGENCY_NAME = "ラクーンドッグ"
PROFILE_URL = "https://www.raccoon-dog.co.jp/talent/r11-hasegawa.html"
OUTPUT_PATH = Path(__file__).resolve().parent / "hasegawa_ikumi_data.json"
HEADERS = {
    "User-Agent": "VoiceActorStudyScraper/1.0 (educational use)",
}


def normalize_text(text: str) -> str:
    """全角空白や改行を整理し、単語間の空白を1つにする。"""
    return re.sub(r"\s+", " ", text).strip()


def extract_name(soup: BeautifulSoup) -> str:
    """プロフィールの「名前」欄から声優名を取得する。"""
    profile = soup.select_one("div.profile dl")
    if profile is None:
        raise ValueError("プロフィール領域が見つかりません。")

    for label in profile.find_all("dt", recursive=False):
        if normalize_text(label.get_text(" ", strip=True)) == "名前":
            value = label.find_next_sibling("dd")
            if value is not None:
                return normalize_text(value.get_text(" ", strip=True))

    raise ValueError("声優名が見つかりません。")


def extract_appearances(soup: BeautifulSoup) -> dict[str, list[str]]:
    """出演作品をカテゴリごとに取得する。"""
    appearance_area = soup.select_one("div.appearance")
    if appearance_area is None:
        raise ValueError("出演作品領域が見つかりません。")

    appearances: dict[str, list[str]] = {}
    for heading in appearance_area.find_all("h4"):
        category = normalize_text(heading.get_text(" ", strip=True))
        category_block = heading.find_next_sibling("div", class_="danraku")
        if category_block is None:
            continue

        entries = []
        for work_element in category_block.select("dl > dt"):
            role_element = work_element.find_next_sibling("dd")
            work = normalize_text(work_element.get_text(" ", strip=True))
            role = (
                normalize_text(role_element.get_text(" ", strip=True))
                if role_element is not None
                else ""
            )

            if work and role:
                entries.append(f"{work}（{role}）")
            elif work:
                entries.append(work)

        if entries:
            appearances[category] = entries

    if not appearances:
        raise ValueError("出演歴を1件も取得できませんでした。")
    return appearances


def extract_voice_sample_groups(soup: BeautifulSoup, base_url: str) -> dict[str, list[str]]:
    """ボイスサンプルのURLを分類ごとに取得する。"""
    voice_heading = next(
        (
            heading
            for heading in soup.find_all("h3")
            if normalize_text(heading.get_text(" ", strip=True)) == "ボイスサンプル"
        ),
        None,
    )
    if voice_heading is None:
        raise ValueError("ボイスサンプルの見出しが見つかりません。")

    voice_block = voice_heading.find_next_sibling("div", class_="danraku")
    if voice_block is None:
        raise ValueError("ボイスサンプル領域が見つかりません。")

    voice_sample_groups: dict[str, list[str]] = {}
    for source in voice_block.select("audio source[src]"):
        source_url = source.get("src")
        if not source_url:
            continue
        absolute_url = urljoin(base_url, source_url)
        group_name = classify_voice_sample_by_agency(AGENCY_NAME, absolute_url)
        voice_sample_groups.setdefault(group_name, [])
        if absolute_url not in voice_sample_groups[group_name]:
            voice_sample_groups[group_name].append(absolute_url)

    if not voice_sample_groups:
        raise ValueError("ボイスサンプルURLを1件も取得できませんでした。")
    return voice_sample_groups


def flatten_voice_sample_groups(voice_sample_groups: dict[str, list[str]]) -> list[str]:
    """互換用の voice_samples を分類付きデータから作る。"""
    voice_samples = []
    for sample_urls in voice_sample_groups.values():
        for sample_url in sample_urls:
            if sample_url not in voice_samples:
                voice_samples.append(sample_url)
    return voice_samples


def scrape_raccoon_dog_profile(url: str) -> dict:
    """ラクーンドッグの声優プロフィールを1回の通信で取得する。"""
    response = requests.get(url, headers=HEADERS, timeout=(5, 20))
    response.raise_for_status()

    soup = BeautifulSoup(response.content, "html.parser")
    name = extract_name(soup)
    voice_sample_groups = extract_voice_sample_groups(soup, response.url)
    return {
        name: {
            "agency": AGENCY_NAME,
            "appearances": extract_appearances(soup),
            "voice_sample_groups": voice_sample_groups,
            "voice_samples": flatten_voice_sample_groups(voice_sample_groups),
        }
    }


def save_json(data: dict, output_path: Path) -> None:
    """取得結果を日本語のまま読みやすく保存する。"""
    with output_path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=4)


def main() -> None:
    try:
        scraped_data = scrape_raccoon_dog_profile(PROFILE_URL)
        save_json(scraped_data, OUTPUT_PATH)
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
    print(f"\nJSON保存先: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
