import argparse
import json
import re
from pathlib import Path
from pprint import pprint
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


AGENCY_NAME = "81プロデュース"
PROFILE_URL = "https://www.81produce.co.jp/actor_search/index.php/item%3Fcell003%3D%25E3%2581%2582%25E8%25A1%258C%26cell029%3D%25E5%25A5%25B3%25E6%2580%25A7%26keyword%3D%26cell028%3D%26page%3D2%26cell004%3D%26name%3D%25E5%25A4%25A7%25E4%25B9%2585%25E4%25BF%259D%25E3%2580%2580%25E7%2591%25A0%25E7%25BE%258E%26id%3D169%26label%3D1"
OUTPUT_PATH = Path(__file__).resolve().parent / "okubo_rumi_data.json"
HEADERS = {
    "User-Agent": "VoiceActorStudyScraper/1.0 (educational use)",
}


def normalize_text(text: str) -> str:
    """全角空白や改行を整理し、単語間の空白を1つにする。"""
    return re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()


def extract_name(soup: BeautifulSoup) -> str:
    """プロフィール表から声優名を取得する。"""
    name_tag = soup.select_one(".actor_name strong")
    if name_tag is None:
        heading = soup.find("h2")
        if heading is None:
            raise ValueError("声優名が見つかりません。")
        return normalize_text(heading.get_text(" ", strip=True))
    return normalize_text(name_tag.get_text(" ", strip=True))


def format_appearance_entry(cells: list[str]) -> str:
    """81プロデュースの表形式を 作品（役名など） の表記へ寄せる。"""
    cells = [normalize_text(cell) for cell in cells if normalize_text(cell)]
    if not cells:
        return ""
    if len(cells) == 1:
        return cells[0]

    title = cells[0]
    detail = " / ".join(cells[1:])
    return f"{title}（{detail}）" if detail else title


def extract_appearances(soup: BeautifulSoup) -> dict[str, list[str]]:
    """主な出演作品をカテゴリごとに取得する。"""
    appearances: dict[str, list[str]] = {}

    for category_tag in soup.select("h4.subtitle04_01"):
        category = normalize_text(category_tag.get_text(" ", strip=True))
        table_block = category_tag.find_next_sibling("div", class_="tab_wrap")
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
        raise ValueError("出演作品を1件も取得できませんでした。")
    return appearances


def extract_voice_labels(soup: BeautifulSoup) -> list[str]:
    """ボイスサンプルの表示ラベルを再生ボタン順に取得する。"""
    labels = []
    voice_heading = soup.find(
        ["h3", "h4"],
        string=lambda value: value and normalize_text(value) == "Voice Sample",
    )
    if voice_heading is None:
        return labels

    audio_list = voice_heading.find_next_sibling("ul", class_="audio_list")
    if audio_list is None:
        return labels

    for label_tag in audio_list.select(".track-name p"):
        label = normalize_text(label_tag.get_text(" ", strip=True))
        if label and label not in labels:
            labels.append(label)
    return labels


def normalize_sample_url(sample_url: str) -> str:
    """プロトコル相対URLをhttpsへ寄せる。"""
    sample_url = normalize_text(sample_url)
    if sample_url.startswith("//"):
        return f"https:{sample_url}"
    return sample_url


def extract_voice_urls(html_text: str) -> list[str]:
    """jPlayer setMedia内のmp3 URLを再生ボタン順に取得する。"""
    urls = []
    for match in re.finditer(r"mp3\s*:\s*['\"](?P<url>[^'\"]*)['\"]", html_text):
        sample_url = normalize_sample_url(match.group("url"))
        if not sample_url or sample_url.endswith("/"):
            continue
        if sample_url not in urls:
            urls.append(sample_url)
    return urls


def classify_voice_sample(label: str) -> str:
    """ボイスサンプルの表示ラベルから分類名を決める。"""
    label = normalize_text(label)
    if "ナレーション" in label:
        return "ナレーション"
    if "セリフ" in label:
        return "セリフ"
    if label in {"名前", "氏名"}:
        return "クレジット"
    return "サンプル"


def extract_voice_sample_groups(soup: BeautifulSoup, html_text: str) -> dict[str, list[str]]:
    """ボイスサンプルURLを分類付きで取得する。"""
    labels = extract_voice_labels(soup)
    urls = extract_voice_urls(html_text)
    voice_sample_groups: dict[str, list[str]] = {}

    for index, sample_url in enumerate(urls):
        label = labels[index] if index < len(labels) else ""
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


def scrape_81produce_profile(url: str) -> dict:
    """81プロデュースの声優プロフィールを1回の通信で取得する。"""
    response = requests.get(url, headers=HEADERS, timeout=(5, 20))
    response.raise_for_status()
    response.encoding = response.apparent_encoding

    soup = BeautifulSoup(response.text, "html.parser")
    name = extract_name(soup)
    voice_sample_groups = extract_voice_sample_groups(soup, response.text)
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
        description="81プロデュース公式プロフィールから声優情報をスクレイピングします。"
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
        scraped_data = scrape_81produce_profile(args.url)
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
