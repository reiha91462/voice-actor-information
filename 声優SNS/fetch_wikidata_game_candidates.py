import argparse
import json
import re
from typing import Any

import requests


WIKIDATA_SPARQL_ENDPOINT = "https://query.wikidata.org/sparql"
MEDIA_TYPES = {
    "game": "Q7889",
    "anime": "Q1107",
}
HEADERS = {
    "User-Agent": (
        "VoiceActorStudyApp/1.0 "
        "(https://github.com/riku/voice-actor; educational use)"
    ),
    "Accept": "application/sparql-results+json",
}


def build_query(actor_name: str, media_type: str = "game") -> str:
    """日本語名の声優から出演作品候補を取得するSPARQLを作る。"""
    escaped_actor_name = actor_name.replace("\\", "\\\\").replace('"', '\\"')
    media_item = MEDIA_TYPES[media_type]
    return f"""
SELECT DISTINCT ?work ?workLabel ?character ?characterLabel WHERE {{
  ?actor rdfs:label "{escaped_actor_name}"@ja.

  {{
    ?work wdt:P31/wdt:P279* wd:{media_item};
          wdt:P725 ?actor.
  }}
  UNION
  {{
    ?work wdt:P31/wdt:P279* wd:{media_item};
          p:P725 ?castStatement.
    ?castStatement ps:P725 ?actor;
                   pq:P453 ?character.
  }}
  UNION
  {{
    ?work wdt:P31/wdt:P279* wd:{media_item};
          wdt:P674 ?character.
    ?character wdt:P725 ?actor.
  }}

  SERVICE wikibase:label {{
    bd:serviceParam wikibase:language "ja,en".
    ?work rdfs:label ?workLabel.
    ?character rdfs:label ?characterLabel.
  }}
}}
ORDER BY ?workLabel ?characterLabel
""".strip()


def fetch_works_by_voice_actor(actor_name: str, media_type: str) -> list[dict]:
    """Wikidataから声優の出演作品候補を取得する。"""
    if media_type not in MEDIA_TYPES:
        raise ValueError(f"未対応のmedia_typeです: {media_type}")

    response = requests.get(
        WIKIDATA_SPARQL_ENDPOINT,
        headers=HEADERS,
        params={"query": build_query(actor_name, media_type), "format": "json"},
        timeout=(5, 30),
    )
    response.raise_for_status()
    data = response.json()
    bindings = data.get("results", {}).get("bindings", [])

    results = []
    seen_keys = set()
    for binding in bindings:
        title = get_binding_value(binding, "workLabel")
        character = get_binding_value(binding, "characterLabel") or "-"
        if not title:
            continue

        dedupe_key = (title, character)
        if dedupe_key in seen_keys:
            continue
        seen_keys.add(dedupe_key)
        results.append({"title": title, "character": character})

    return merge_duplicate_works(results)


def merge_duplicate_works(works: list[dict]) -> list[dict]:
    """同一作品の重複をまとめ、キャラ名ありを優先する。"""
    grouped = {}
    order = []

    for work in works:
        title = work.get("title", "")
        character = work.get("character", "-")
        if not title:
            continue

        key = normalize_title_for_merge(title)
        if key not in grouped:
            grouped[key] = {
                "title": title,
                "characters": [],
                "has_unknown": False,
            }
            order.append(key)

        if character == "-":
            grouped[key]["has_unknown"] = True
        elif character not in grouped[key]["characters"]:
            grouped[key]["characters"].append(character)

        if len(title) < len(grouped[key]["title"]):
            grouped[key]["title"] = title

    merged = []
    for key in order:
        item = grouped[key]
        characters = item["characters"]
        if characters:
            for character in characters:
                merged.append({"title": item["title"], "character": character})
        elif item["has_unknown"]:
            merged.append({"title": item["title"], "character": "-"})

    return merged


def normalize_title_for_merge(title: str) -> str:
    """シリーズ表記や期表記を軽く落として重複比較する。"""
    normalized = title.strip()
    normalized = normalized.replace("！", "!")
    normalized = normalized.replace("：", ":")
    normalized = re.sub(r"\s+", " ", normalized)
    normalized = re.sub(r"\s+第[0-9０-９一二三四五六七八九十]+期$", "", normalized)
    normalized = re.sub(r"\s+[0-9０-９]+(?:st|nd|rd|th) season$", "", normalized, flags=re.I)
    normalized = re.sub(r"\s+第[0-9０-９一二三四五六七八九十]+シーズン$", "", normalized)
    return normalized.lower()


def fetch_games_by_voice_actor(actor_name: str) -> list[dict]:
    """Wikidataから声優の出演ゲーム候補を取得する。"""
    return fetch_works_by_voice_actor(actor_name, "game")


def fetch_anime_by_voice_actor(actor_name: str) -> list[dict]:
    """Wikidataから声優の出演アニメ候補を取得する。"""
    return fetch_works_by_voice_actor(actor_name, "anime")


def get_binding_value(binding: dict[str, Any], key: str) -> str:
    """SPARQL JSON bindingから文字列値を取り出す。"""
    value = binding.get(key, {}).get("value", "")
    return value.strip() if isinstance(value, str) else ""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Wikidataから声優の出演ゲーム候補を取得します。"
    )
    parser.add_argument(
        "actor_name",
        nargs="?",
        default="青山吉能",
        help='声優名。省略時は "青山吉能"。',
    )
    parser.add_argument(
        "--media-type",
        choices=sorted(MEDIA_TYPES),
        default="game",
        help="取得する作品種別。game または anime。",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        works = fetch_works_by_voice_actor(args.actor_name, args.media_type)
    except requests.exceptions.Timeout as error:
        print(f"エラー: Wikidataへの接続がタイムアウトしました: {error}")
        raise SystemExit(1) from error
    except requests.exceptions.RequestException as error:
        print(f"エラー: Wikidataへの通信に失敗しました: {error}")
        raise SystemExit(1) from error
    except (json.JSONDecodeError, ValueError) as error:
        print(f"エラー: Wikidataのレスポンスを処理できません: {error}")
        raise SystemExit(1) from error

    print(json.dumps(works, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
