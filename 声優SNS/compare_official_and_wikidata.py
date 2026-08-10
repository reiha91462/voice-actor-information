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

from fetch_wikidata_game_candidates import fetch_works_by_voice_actor


DEFAULT_DATA_PATH = SCRIPT_DIR / "hasegawa_ikumi_data.json"
CATEGORY_MEDIA_TYPES = {
    "アニメ": "anime",
    "TVアニメ": "anime",
    "劇場アニメ": "anime",
    "ゲーム": "game",
}


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
        return actor_name or json_path.stem.removesuffix("_data"), data

    if actor_name and isinstance(data.get(actor_name), dict):
        return actor_name, data[actor_name]

    candidates = [
        (name, value)
        for name, value in data.items()
        if isinstance(value, dict) and isinstance(value.get("appearances"), dict)
    ]
    if len(candidates) != 1:
        raise ValueError("声優データを1人に特定できません。--actor-name を指定してください。")
    return candidates[0]


def parse_official_entry(entry: str) -> dict[str, str]:
    """公式出演歴の1行から作品名と役名を取り出す。"""
    text = normalize_spaces(entry)
    match = re.match(r"^(?P<title>.+?)（(?P<character>.+)）$", text)
    if match:
        return {
            "title": clean_title(match.group("title")),
            "character": normalize_spaces(match.group("character")),
            "raw": entry,
        }

    quoted_match = re.match(r"^「(?P<title>.+?)」(?P<character>.+)$", text)
    if quoted_match:
        return {
            "title": clean_title(quoted_match.group("title")),
            "character": normalize_spaces(quoted_match.group("character")),
            "raw": entry,
        }

    return {"title": clean_title(text), "character": "", "raw": entry}


def clean_title(title: str) -> str:
    """作品名比較に不要な装飾を軽く取り除く。"""
    title = normalize_spaces(title)
    title = title.strip("「」『』")
    title = re.sub(r"\s+Switch版$", "", title)
    return normalize_spaces(title)


def normalize_title_for_match(title: str) -> str:
    """表記揺れを吸収するための比較用タイトルを作る。"""
    normalized = title.lower()
    normalized = normalized.replace("！", "!")
    normalized = normalized.replace("：", ":")
    normalized = normalized.replace("〜", "～")
    normalized = normalized.replace("－", "-")
    normalized = normalized.replace("―", "-")
    normalized = normalized.replace("–", "-")
    normalized = re.sub(r"\s+", "", normalized)
    normalized = re.sub(r"[「」『』【】\[\]（）()・.,。]", "", normalized)
    return normalized


def normalize_spaces(text: str) -> str:
    """空白と改行を1つの半角スペースにそろえる。"""
    return re.sub(r"\s+", " ", text).strip()


def is_title_match(official_title: str, external_title: str) -> bool:
    """完全一致または包含一致で同一作品候補と判定する。"""
    official = normalize_title_for_match(official_title)
    external = normalize_title_for_match(external_title)
    if not official or not external:
        return False
    return official == external or official in external or external in official


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
        if categories and category not in categories:
            continue
        if not isinstance(entries, list):
            continue
        extracted[category] = [
            parse_official_entry(entry)
            for entry in entries
            if isinstance(entry, str) and entry.strip()
        ]
    return extracted


def compare_official_and_wikidata(
    actor_name: str,
    actor_data: dict[str, Any],
    categories: list[str],
) -> dict[str, Any]:
    """公式出演歴とWikidata候補を突き合わせる。"""
    official_entries = extract_official_entries(actor_data, categories)
    candidates_by_media_type = {}

    matched_by_category = {}
    unmatched_by_category = {}
    candidates_count_by_media_type = {}
    for category, entries in official_entries.items():
        media_type = CATEGORY_MEDIA_TYPES.get(category)
        if media_type is None:
            unmatched_by_category[category] = [entry["raw"] for entry in entries]
            matched_by_category[category] = []
            continue

        if media_type not in candidates_by_media_type:
            candidates_by_media_type[media_type] = fetch_works_by_voice_actor(
                actor_name,
                media_type,
            )
            candidates_count_by_media_type[media_type] = len(
                candidates_by_media_type[media_type]
            )

        wikidata_candidates = candidates_by_media_type[media_type]
        matches = []
        unmatched = []
        for official in entries:
            matched_candidates = [
                candidate
                for candidate in wikidata_candidates
                if is_title_match(official["title"], candidate["title"])
            ]
            if matched_candidates:
                for candidate in matched_candidates:
                    matches.append(
                        {
                            "official": official["raw"],
                            "official_title": official["title"],
                            "official_character": official["character"],
                            "wikidata_title": candidate["title"],
                            "wikidata_character": candidate["character"],
                        }
                    )
            else:
                unmatched.append(official["raw"])

        matched_by_category[category] = matches
        unmatched_by_category[category] = unmatched

    return {
        actor_name: {
            "matched_works": matched_by_category,
            "unmatched_official_works": unmatched_by_category,
            "wikidata_candidates_count": candidates_count_by_media_type,
        }
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="公式サイト出演歴とWikidata候補が一致する作品を抽出します。"
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
        "--categories",
        nargs="+",
        default=["ゲーム"],
        help="照合する公式出演歴カテゴリ。例: ゲーム TVアニメ 劇場アニメ。",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_path = args.input_json
    if not input_path.exists() and not input_path.is_absolute():
        input_path = SCRIPT_DIR / input_path

    try:
        actor_name, actor_data = load_actor_data(input_path, args.actor_name)
        result = compare_official_and_wikidata(
            actor_name,
            actor_data,
            args.categories,
        )
    except FileNotFoundError as error:
        print(f"エラー: JSONファイルが見つかりません: {input_path}")
        raise SystemExit(1) from error
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as error:
        print(f"エラー: JSONファイルを読み込めません: {error}")
        raise SystemExit(1) from error
    except requests.exceptions.Timeout as error:
        print(f"エラー: Wikidataへの接続がタイムアウトしました: {error}")
        raise SystemExit(1) from error
    except requests.exceptions.RequestException as error:
        print(f"エラー: Wikidataへの通信に失敗しました: {error}")
        raise SystemExit(1) from error

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
