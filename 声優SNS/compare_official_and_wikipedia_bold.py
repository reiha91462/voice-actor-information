import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import requests

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from compare_official_and_wikidata import (
    is_title_match,
    parse_official_entry,
)
from fetch_wikipedia_bold_appearances import (
    WikipediaParseError,
    fetch_wikipedia_bold_appearances,
)


DEFAULT_DATA_PATH = SCRIPT_DIR / "hasegawa_ikumi_data.json"
DEFAULT_CATEGORIES = ["TVアニメ", "劇場アニメ"]


def load_json(json_path: Path) -> dict[str, Any]:
    """UTF-8のJSONを辞書として読み込む。"""
    with json_path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, dict):
        raise ValueError("JSONのルートが辞書形式ではありません。")
    return data


def load_actor_data(json_path: Path, actor_name: str | None) -> tuple[str, dict[str, Any]]:
    """平坦形式と声優名で入れ子になった形式の両方を扱う。"""
    data = load_json(json_path)
    if isinstance(data.get("appearances"), dict):
        resolved_name = actor_name or data.get("name")
        if not isinstance(resolved_name, str) or not resolved_name.strip():
            raise ValueError(
                "平坦形式のJSONでは声優名を自動特定できません。"
                "--actor-name を指定してください。"
            )
        return resolved_name, data

    if actor_name and isinstance(data.get(actor_name), dict):
        return actor_name, data[actor_name]

    if actor_name:
        normalized_actor_name = normalize_for_match(actor_name)
        for name, value in data.items():
            if normalize_for_match(name) == normalized_actor_name and isinstance(value, dict):
                return name, value

    candidates = [
        (name, value)
        for name, value in data.items()
        if isinstance(value, dict) and isinstance(value.get("appearances"), dict)
    ]
    if len(candidates) != 1:
        raise ValueError("声優データを1人に特定できません。--actor-name を指定してください。")
    return candidates[0]


def compare_official_and_wikipedia_bold(
    actor_name: str,
    actor_data: dict[str, Any],
    wikipedia_title: str,
    categories: list[str],
    limit: int,
) -> dict[str, Any]:
    """公式出演歴とWikipedia太字出演候補を照合する。"""
    official_entries = extract_official_entries(actor_data, categories)
    wikipedia_bold = fetch_wikipedia_bold_appearances(wikipedia_title)
    wikipedia_candidates = [
        candidate
        for candidates in wikipedia_bold.values()
        for candidate in candidates
    ]

    matches = []
    unmatched = []
    for category, entries in official_entries.items():
        for official in entries:
            matched_candidate = find_matching_candidate(official, wikipedia_candidates)
            if matched_candidate is None:
                unmatched.append(official["raw"])
                continue

            matches.append(
                {
                    "category": category,
                    "title": official["title"],
                    "character": official["character"],
                    "official": official["raw"],
                    "wikipedia_title": matched_candidate["title"],
                    "wikipedia_character": matched_candidate["character"],
                }
            )

    return {
        actor_name: {
            "representative_work_candidates": matches[:limit],
            "unmatched_official_works": unmatched,
            "wikipedia_bold_candidates_count": len(wikipedia_candidates),
        }
    }


def extract_official_entries(
    actor_data: dict[str, Any],
    categories: list[str],
) -> dict[str, list[dict[str, str]]]:
    """公式出演歴から対象カテゴリの作品を取り出す。"""
    appearances = actor_data.get("appearances", {})
    if not isinstance(appearances, dict):
        return {}

    extracted = {}
    for category, entries in appearances.items():
        if category not in categories or not isinstance(entries, list):
            continue
        extracted[category] = [
            parse_official_entry(entry)
            for entry in entries
            if isinstance(entry, str) and entry.strip()
        ]
    return extracted


def find_matching_candidate(
    official: dict[str, str],
    wikipedia_candidates: list[dict],
) -> dict | None:
    """タイトル一致を優先し、取れる場合はキャラ名も確認する。"""
    title_matches = [
        candidate
        for candidate in wikipedia_candidates
        if is_title_match(official["title"], candidate["title"])
    ]
    if not title_matches:
        return None

    official_character = normalize_for_match(official.get("character", ""))
    if official_character:
        for candidate in title_matches:
            wikipedia_character = normalize_for_match(candidate.get("character", ""))
            if wikipedia_character and (
                official_character in wikipedia_character
                or wikipedia_character in official_character
            ):
                return candidate

    return title_matches[0]


def normalize_for_match(text: str) -> str:
    """役名比較用の文字列を作る。"""
    normalized = re.sub(r"\s+", "", text)
    normalized = re.sub(r"[「」『』（）()・,、/／]", "", normalized)
    return normalized


def normalize_wikipedia_title(actor_name: str) -> str:
    """声優名からWikipediaページ名として使いやすい表記を作る。"""
    return re.sub(r"\s+", "", actor_name)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="公式サイト出演歴とWikipedia太字出演候補を照合します。"
    )
    parser.add_argument(
        "input_json",
        nargs="?",
        type=Path,
        default=DEFAULT_DATA_PATH,
        help="スクレイピング結果JSON。省略時は hasegawa_ikumi_data.json。",
    )
    parser.add_argument(
        "--actor-name",
        help="声優名。JSONから特定できる場合は省略可能。",
    )
    parser.add_argument(
        "--wikipedia-title",
        help="Wikipediaページ名。省略時は声優名を使う。",
    )
    parser.add_argument(
        "--categories",
        nargs="+",
        default=DEFAULT_CATEGORIES,
        help="照合する公式出演歴カテゴリ。省略時は TVアニメ 劇場アニメ。",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="出力する候補数。省略時は10件。",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_path = args.input_json
    if not input_path.exists() and not input_path.is_absolute():
        input_path = SCRIPT_DIR / input_path

    try:
        actor_name, actor_data = load_actor_data(input_path, args.actor_name)
        wikipedia_title = args.wikipedia_title or normalize_wikipedia_title(actor_name)
        result = compare_official_and_wikipedia_bold(
            actor_name,
            actor_data,
            wikipedia_title,
            args.categories,
            args.limit,
        )
    except FileNotFoundError as error:
        print(f"エラー: JSONファイルが見つかりません: {input_path}")
        raise SystemExit(1) from error
    except WikipediaParseError as error:
        print(f"エラー: Wikipediaページを解析できません: {error}")
        raise SystemExit(1) from error
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as error:
        print(f"エラー: 入力データを処理できません: {error}")
        raise SystemExit(1) from error
    except requests.exceptions.Timeout as error:
        print(f"エラー: Wikipediaへの接続がタイムアウトしました: {error}")
        raise SystemExit(1) from error
    except requests.exceptions.RequestException as error:
        print(f"エラー: Wikipediaへの通信に失敗しました: {error}")
        raise SystemExit(1) from error

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
