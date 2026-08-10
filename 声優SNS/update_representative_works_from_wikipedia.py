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

from compare_official_and_wikipedia_bold import (
    extract_official_entries,
    find_matching_candidate,
    normalize_wikipedia_title,
)
from fetch_wikipedia_bold_appearances import (
    WikipediaParseError,
    fetch_wikipedia_bold_appearances,
)


DEFAULT_DATA_PATH = SCRIPT_DIR / "hasegawa_ikumi_data.json"
DEFAULT_ANIME_CATEGORIES = ["TVアニメ", "劇場アニメ", "Webアニメ", "アニメ"]
DEFAULT_GAME_CATEGORIES = ["ゲーム"]
DEFAULT_LIMIT = 3


def load_json(json_path: Path) -> dict[str, Any]:
    """UTF-8のJSONを辞書として読み込む。"""
    with json_path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, dict):
        raise ValueError("JSONのルートが辞書形式ではありません。")
    return data


def resolve_actor_data(
    root_data: dict[str, Any],
    actor_name: str | None,
    json_path: Path,
) -> tuple[str, dict[str, Any]]:
    """平坦形式と声優名で入れ子になった形式の両方を扱う。"""
    if isinstance(root_data.get("appearances"), dict):
        resolved_name = actor_name or root_data.get("name")
        if not isinstance(resolved_name, str) or not resolved_name.strip():
            raise ValueError(
                "平坦形式のJSONでは声優名を自動特定できません。"
                "--actor-name を指定してください。"
            )
        return resolved_name, root_data

    if actor_name and isinstance(root_data.get(actor_name), dict):
        return actor_name, root_data[actor_name]

    if actor_name:
        normalized_actor_name = normalize_for_key(actor_name)
        for name, value in root_data.items():
            if normalize_for_key(name) == normalized_actor_name and isinstance(value, dict):
                return name, value

    candidates = [
        (name, value)
        for name, value in root_data.items()
        if isinstance(value, dict) and isinstance(value.get("appearances"), dict)
    ]
    if len(candidates) != 1:
        raise ValueError("声優データを1人に特定できません。--actor-name を指定してください。")
    return candidates[0]


def select_representative_works(
    actor_name: str,
    actor_data: dict[str, Any],
    wikipedia_title: str,
    anime_categories: list[str],
    game_categories: list[str],
    limit: int,
) -> list[dict[str, str]]:
    """Wikipedia太字候補と公式出演歴を照合し、代表作を最大limit件選ぶ。"""
    wikipedia_bold = fetch_wikipedia_bold_appearances(wikipedia_title)
    selected = []
    selected_keys = set()

    selected.extend(
        match_categories(
            actor_data,
            wikipedia_bold.get("アニメ", []),
            anime_categories,
            limit - len(selected),
            selected_keys,
        )
    )

    if len(selected) < limit:
        selected.extend(
            match_categories(
                actor_data,
                wikipedia_bold.get("ゲーム", []),
                game_categories,
                limit - len(selected),
                selected_keys,
            )
        )

    return selected[:limit]


def match_categories(
    actor_data: dict[str, Any],
    wikipedia_candidates: list[dict],
    categories: list[str],
    remaining_slots: int,
    selected_keys: set[tuple[str, str]],
) -> list[dict[str, str]]:
    """指定カテゴリの公式出演歴とWikipedia候補を照合する。"""
    if remaining_slots <= 0 or not wikipedia_candidates:
        return []

    matched_works = []
    official_entries = extract_official_entries(actor_data, categories)
    for category in categories:
        for official in official_entries.get(category, []):
            matched_candidate = find_matching_candidate(official, wikipedia_candidates)
            if matched_candidate is None:
                continue

            title = official["title"]
            character = official["character"]
            key = (normalize_for_key(title), normalize_for_key(character))
            if key in selected_keys:
                continue

            selected_keys.add(key)
            matched_works.append(
                {
                    "category": normalize_category(category),
                    "title": title,
                    "character": character,
                    "source": "official_site_and_wikipedia_bold",
                    "official": official["raw"],
                    "wikipedia_title": matched_candidate["title"],
                }
            )
            if len(matched_works) >= remaining_slots:
                return matched_works

    return matched_works


def normalize_category(category: str) -> str:
    """表示用カテゴリに寄せる。"""
    if category in {"TVアニメ", "劇場アニメ", "Webアニメ"}:
        return "アニメ"
    return category


def normalize_for_key(text: str) -> str:
    """重複判定用に表記を軽く正規化する。"""
    normalized = re.sub(r"\s+", "", text)
    normalized = normalized.replace("！", "!")
    normalized = re.sub(r"[「」『』（）()・,、/／]", "", normalized)
    return normalized.lower()


def save_json(data: dict[str, Any], output_path: Path) -> None:
    """JSONを日本語のまま読みやすく保存する。"""
    with output_path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=4)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "公式サイト出演歴とWikipedia太字出演候補を照合し、"
            "representative_works をJSONへ保存します。"
        )
    )
    parser.add_argument(
        "input_json",
        nargs="?",
        type=Path,
        default=DEFAULT_DATA_PATH,
        help="更新するスクレイピング結果JSON。省略時は hasegawa_ikumi_data.json。",
    )
    parser.add_argument(
        "--actor-name",
        help="声優名。JSONから特定できる場合は省略可能。",
    )
    parser.add_argument(
        "--wikipedia-title",
        help="Wikipediaページ名。省略時は声優名から空白を除去して使う。",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_LIMIT,
        help="保存する代表作数。省略時は3件。",
    )
    parser.add_argument(
        "--anime-categories",
        nargs="+",
        default=DEFAULT_ANIME_CATEGORIES,
        help="アニメ代表作として優先する公式カテゴリ。",
    )
    parser.add_argument(
        "--game-categories",
        nargs="+",
        default=DEFAULT_GAME_CATEGORIES,
        help="アニメで埋まらない場合に補完する公式カテゴリ。",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="JSONへ保存せず、選定結果だけ表示する。",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="保存先JSON。省略時は入力JSONへ上書き保存。",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_path = args.input_json
    if not input_path.exists() and not input_path.is_absolute():
        input_path = SCRIPT_DIR / input_path
    output_path = args.output or input_path
    if args.output and not output_path.is_absolute():
        output_path = SCRIPT_DIR / output_path

    try:
        root_data = load_json(input_path)
        actor_name, actor_data = resolve_actor_data(root_data, args.actor_name, input_path)
        wikipedia_title = args.wikipedia_title or normalize_wikipedia_title(actor_name)
        representative_works = select_representative_works(
            actor_name,
            actor_data,
            wikipedia_title,
            args.anime_categories,
            args.game_categories,
            args.limit,
        )
        actor_data["representative_works"] = representative_works
        if not args.dry_run:
            save_json(root_data, output_path)
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
    except OSError as error:
        print(f"エラー: JSONファイルへ保存できません: {error}")
        raise SystemExit(1) from error

    output = {
        actor_name: {
            "representative_works": representative_works,
            "saved": not args.dry_run,
            "output_path": str(output_path),
        }
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
