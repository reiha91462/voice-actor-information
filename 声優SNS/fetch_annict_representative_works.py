import argparse
import json
import math
import os
from typing import Any

import requests


ANNICT_API_BASE_URL = "https://api.annict.com"
PER_PAGE = 50
WORK_WEIGHT = 0.5
CHARACTER_WEIGHT = 0.2
CAST_ORDER_WEIGHT = 0.3


def get_rest(
    path: str,
    params: dict[str, Any],
    api_key: str,
) -> dict[str, Any]:
    """Annict REST APIへGETしてJSONレスポンスを返す。"""
    headers = {"Authorization": f"Bearer {api_key}"}
    response = requests.get(
        f"{ANNICT_API_BASE_URL}{path}",
        headers=headers,
        params=params,
        timeout=(5, 30),
    )
    response.raise_for_status()
    data = response.json()

    if "errors" in data:
        raise RuntimeError(json.dumps(data["errors"], ensure_ascii=False, indent=2))
    return data


def normalize_name(name: str) -> str:
    """姓名の空白差を吸収して比較する。"""
    return "".join(name.split())


def find_person(actor_name: str, api_key: str) -> dict[str, Any] | None:
    """人物APIから対象声優を探す。"""
    data = get_rest(
        "/v1/people",
        {
            "filter_name": actor_name,
            "per_page": PER_PAGE,
            "fields": "id,name,name_kana,name_en,casts_count",
        },
        api_key,
    )
    people = data.get("people", [])
    if not isinstance(people, list):
        return None

    normalized_actor_name = normalize_name(actor_name)
    exact_matches = [
        person
        for person in people
        if normalize_name(str(person.get("name", ""))) == normalized_actor_name
    ]
    if exact_matches:
        return exact_matches[0]
    return people[0] if people else None


def normalize_cast(cast: dict[str, Any]) -> dict[str, Any] | None:
    """RESTのcastデータを代表作候補の形式へ変換する。"""
    work = cast.get("work") or {}
    character = cast.get("character") or {}
    title = work.get("title")
    if not title:
        return None

    season_name = work.get("season_name")
    year = None
    if isinstance(season_name, str) and "-" in season_name:
        year_text = season_name.split("-", 1)[0]
        if year_text.isdigit():
            year = int(year_text)

    return {
        "title": title,
        "character": character.get("name") or "",
        "character_id": character.get("id"),
        "year": year,
        "season": season_name or "",
        "watchers": work.get("watchers_count") or 0,
        "character_favorites": character.get("favorite_characters_count") or 0,
        "sort_number": cast.get("sort_number"),
    }


def fetch_person_casts(
    person: dict[str, Any],
    api_key: str,
    max_pages: int,
) -> list[dict[str, Any]]:
    """キャスト一覧を走査して、対象人物の出演作だけを集める。"""
    direct_casts = fetch_person_casts_by_filter(person, api_key)
    if direct_casts is not None:
        return direct_casts

    person_id = person.get("id")
    person_name = normalize_name(str(person.get("name", "")))
    works = []
    seen_keys = set()

    for page in range(1, max_pages + 1):
        data = get_rest(
            "/v1/casts",
            {
                "page": page,
                "per_page": PER_PAGE,
                "sort_id": "desc",
            },
            api_key,
        )
        casts = data.get("casts", [])
        if not isinstance(casts, list) or not casts:
            break

        for cast in casts:
            cast_person = cast.get("person") or {}
            same_person_id = person_id is not None and cast_person.get("id") == person_id
            same_person_name = (
                person_name
                and normalize_name(str(cast_person.get("name", ""))) == person_name
            )
            if not same_person_id and not same_person_name:
                continue

            work = normalize_cast(cast)
            if work is None:
                continue

            dedupe_key = (work["title"], work["character"])
            if dedupe_key in seen_keys:
                continue
            seen_keys.add(dedupe_key)
            works.append(work)

        if data.get("next_page") is None:
            break

    return works


def fetch_person_casts_by_filter(
    person: dict[str, Any],
    api_key: str,
) -> list[dict[str, Any]] | None:
    """人物ID指定の絞り込みを試す。未対応ならNoneを返して走査に戻す。"""
    person_id = person.get("id")
    if person_id is None:
        return None

    works = []
    seen_keys = set()
    page = 1

    while True:
        try:
            data = get_rest(
                "/v1/casts",
                {
                    "filter_person_id": person_id,
                    "page": page,
                    "per_page": PER_PAGE,
                    "sort_id": "desc",
                },
                api_key,
            )
        except RuntimeError:
            return None

        casts = data.get("casts", [])
        if not isinstance(casts, list):
            return None
        if not casts:
            return works

        if any((cast.get("person") or {}).get("id") != person_id for cast in casts):
            return None

        for cast in casts:
            work = normalize_cast(cast)
            if work is None:
                continue

            dedupe_key = (work["title"], work["character"])
            if dedupe_key in seen_keys:
                continue
            seen_keys.add(dedupe_key)
            works.append(work)

        if data.get("next_page") is None:
            return works
        page += 1


def chunked(items: list[Any], size: int) -> list[list[Any]]:
    """リストをAPI上限に合わせて分割する。"""
    return [items[index : index + size] for index in range(0, len(items), size)]


def fetch_character_favorites(
    character_ids: list[int],
    api_key: str,
) -> dict[int, int]:
    """キャラクターIDごとのお気に入り数を取得する。"""
    favorites_by_id = {}
    unique_ids = []
    for character_id in character_ids:
        if isinstance(character_id, int) and character_id not in unique_ids:
            unique_ids.append(character_id)

    for ids in chunked(unique_ids, PER_PAGE):
        data = get_rest(
            "/v1/characters",
            {
                "filter_ids": ",".join(str(character_id) for character_id in ids),
                "per_page": PER_PAGE,
                "fields": "id,name,favorite_characters_count",
            },
            api_key,
        )
        characters = data.get("characters", [])
        if not isinstance(characters, list):
            continue

        for character in characters:
            character_id = character.get("id")
            if isinstance(character_id, int):
                favorites_by_id[character_id] = (
                    character.get("favorite_characters_count") or 0
                )

    return favorites_by_id


def add_representative_scores(
    works: list[dict[str, Any]],
    api_key: str,
) -> list[dict[str, Any]]:
    """作品知名度、キャラクター人気、キャスト順から代表作スコアを付与する。"""
    character_ids = [
        work["character_id"]
        for work in works
        if isinstance(work.get("character_id"), int)
        and not work.get("character_favorites")
    ]
    favorites_by_id = fetch_character_favorites(character_ids, api_key)

    scored_works = []
    for work in works:
        character_id = work.get("character_id")
        if isinstance(character_id, int):
            work["character_favorites"] = max(
                work.get("character_favorites") or 0,
                favorites_by_id.get(character_id, 0),
            )

        watchers_score = math.log1p(work.get("watchers") or 0)
        character_score = math.log1p(work.get("character_favorites") or 0)
        cast_order_score = calculate_cast_order_score(work.get("sort_number"))
        score = (
            watchers_score * WORK_WEIGHT
            + character_score * CHARACTER_WEIGHT
            + cast_order_score * CAST_ORDER_WEIGHT
        )
        work["cast_order_score"] = round(cast_order_score, 4)
        work["score"] = round(score, 4)
        scored_works.append(work)

    return scored_works


def calculate_cast_order_score(sort_number: Any) -> float:
    """キャスト順が上位の役を高く評価する。"""
    if not isinstance(sort_number, int) or sort_number < 0:
        return 0.0
    return 1 / math.log2(sort_number + 2)


def fetch_representative_works(
    actor_name: str,
    api_key: str,
    max_pages: int,
) -> dict[str, list[dict[str, Any]]]:
    """声優名からAnnict上の出演作候補を取得する。"""
    person = find_person(actor_name, api_key)
    if person is None:
        return {actor_name: []}

    person_name = person.get("name") or actor_name
    casts = fetch_person_casts(person, api_key, max_pages)
    return {person_name: add_representative_scores(casts, api_key)}


def sort_works(
    works: list[dict[str, Any]],
    sort_key: str,
    limit: int,
) -> list[dict[str, Any]]:
    """代表作候補を人気度または年で並び替え、上位件数に絞る。"""
    if sort_key == "year":
        sorted_works = sorted(
            works,
            key=lambda item: (
                item.get("year") or 0,
                item.get("score") or 0,
                item.get("watchers") or 0,
            ),
            reverse=True,
        )
    elif sort_key == "watchers":
        sorted_works = sorted(
            works,
            key=lambda item: (
                item.get("watchers") or 0,
                item.get("character_favorites") or 0,
                item.get("year") or 0,
            ),
            reverse=True,
        )
    else:
        sorted_works = sorted(
            works,
            key=lambda item: (
                item.get("score") or 0,
                item.get("cast_order_score") or 0,
                item.get("watchers") or 0,
                item.get("year") or 0,
            ),
            reverse=True,
        )
    return [format_output_work(work) for work in sorted_works[:limit]]


def format_output_work(work: dict[str, Any]) -> dict[str, Any]:
    """出力用に内部IDを取り除く。"""
    return {
        "title": work.get("title") or "",
        "character": work.get("character") or "",
        "year": work.get("year"),
        "season": work.get("season") or "",
        "watchers": work.get("watchers") or 0,
        "character_favorites": work.get("character_favorites") or 0,
        "sort_number": work.get("sort_number"),
        "cast_order_score": work.get("cast_order_score") or 0,
        "score": work.get("score") or 0,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Annict APIから声優の代表作候補を取得します。"
    )
    parser.add_argument("actor_name", help='声優名。例: "長谷川育美"')
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="出力件数。省略時は10件。",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=30,
        help="キャスト一覧を走査する最大ページ数。1ページ50件。",
    )
    parser.add_argument(
        "--sort",
        choices=["score", "watchers", "year"],
        default="score",
        help=(
            "並び順。score は代表作スコア順、watchers は作品人気順、"
            "year は放送年の新しい順。"
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    api_key = os.environ.get("ANNICT_API_KEY")
    if not api_key:
        print("エラー: 環境変数 ANNICT_API_KEY が設定されていません。")
        print('export ANNICT_API_KEY="Annictで発行した実際のアクセストークン"')
        raise SystemExit(1)

    try:
        result = fetch_representative_works(
            actor_name=args.actor_name,
            api_key=api_key,
            max_pages=args.max_pages,
        )
    except requests.exceptions.Timeout as error:
        print(f"エラー: Annict APIへの接続がタイムアウトしました: {error}")
        raise SystemExit(1) from error
    except requests.exceptions.RequestException as error:
        print(f"エラー: Annict APIへの通信に失敗しました: {error}")
        raise SystemExit(1) from error
    except (json.JSONDecodeError, RuntimeError) as error:
        print(f"エラー: Annict APIのレスポンスを処理できません: {error}")
        raise SystemExit(1) from error

    actor_name, works = next(iter(result.items()))
    output = {actor_name: sort_works(works, args.sort, args.limit)}
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
