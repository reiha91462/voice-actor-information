import argparse
import json
import re
from pathlib import Path
from pprint import pprint
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


AGENCY_NAME = "アイムエンタープライズ"
PROFILE_URL = "https://www.imenterprise.jp/profile.php?id=26"
OUTPUT_PATH = Path(__file__).resolve().parent / "uchida_maaya_data.json"
HEADERS = {
    "User-Agent": "VoiceActorStudyScraper/1.0 (educational use)",
}


def normalize_text(text: str) -> str:
    """全角空白や改行を整理し、単語間の空白を1つにする。"""
    return re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()


def extract_name(soup: BeautifulSoup) -> str:
    """プロフィール表から声優名を取得する。"""
    for row in soup.select("table tr"):
        cells = row.find_all(["th", "td"])
        if len(cells) < 2:
            continue
        label = normalize_text(cells[0].get_text(" ", strip=True))
        if label == "氏名":
            return normalize_text(cells[1].get_text(" ", strip=True))

    raise ValueError("声優名が見つかりません。")


def extract_appearance_cell(soup: BeautifulSoup):
    """出演履歴見出し直後のセルを取得する。"""
    for heading in soup.find_all("h2"):
        if normalize_text(heading.get_text(" ", strip=True)) != "出演履歴":
            continue
        table = heading.find_next("table")
        if table is None:
            continue
        cell = table.select_one("td.bg-white")
        if cell is not None:
            return cell
    return None


def extract_appearances(soup: BeautifulSoup) -> dict[str, list[str]]:
    """【カテゴリ】と・項目で構成された出演歴を取得する。"""
    cell = extract_appearance_cell(soup)
    if cell is None:
        raise ValueError("出演履歴のセルが見つかりません。")

    appearances: dict[str, list[str]] = {}
    current_category = None
    for raw_line in cell.get_text("\n", strip=True).splitlines():
        line = normalize_text(raw_line)
        if not line:
            continue

        category_match = re.match(r"^【(?P<category>.+?)】$", line)
        if category_match:
            current_category = category_match.group("category")
            appearances.setdefault(current_category, [])
            continue

        if current_category is None:
            continue

        entry = line.lstrip("・").strip()
        if entry and entry not in appearances[current_category]:
            appearances[current_category].append(entry)

    appearances = {
        category: entries
        for category, entries in appearances.items()
        if entries
    }
    if not appearances:
        raise ValueError("出演歴を1件も取得できませんでした。")
    return appearances


def classify_voice_sample(label: str) -> str:
    """ボイスサンプルの表示ラベルから分類名を決める。"""
    normalized_label = normalize_text(label)
    if normalized_label == "名前":
        return "クレジット"
    if "ナレーション" in normalized_label:
        return "ナレーション"
    if "セリフ" in normalized_label:
        return "セリフ"
    return "サンプル"


def extract_voice_sample_groups(soup: BeautifulSoup, base_url: str) -> dict[str, list[str]]:
    """a[data-src]からボイスサンプルURLを分類付きで取得する。"""
    voice_sample_groups: dict[str, list[str]] = {}

    for link in soup.select("ol.voiceList a[data-src]"):
        label = normalize_text(link.get_text(" ", strip=True))
        sample_url = urljoin(base_url, link.get("data-src", ""))
        if not sample_url:
            continue

        group_name = classify_voice_sample(label)
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


def scrape_imenterprise_profile(url: str) -> dict:
    """アイムエンタープライズの声優プロフィールを1回の通信で取得する。"""
    response = requests.get(url, headers=HEADERS, timeout=(5, 20))
    response.raise_for_status()
    response.encoding = response.apparent_encoding

    soup = BeautifulSoup(response.text, "html.parser")
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
        description="アイムエンタープライズ公式プロフィールから声優情報をスクレイピングします。"
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
        scraped_data = scrape_imenterprise_profile(args.url)
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
