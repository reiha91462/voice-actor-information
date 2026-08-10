import argparse
import json
import re

import requests


WIKIPEDIA_API_URL = "https://ja.wikipedia.org/w/api.php"
HEADERS = {
    "User-Agent": (
        "VoiceActorStudyApp/1.0 "
        "(https://github.com/riku/voice-actor; educational use)"
    )
}
TARGET_HEADINGS = {
    "テレビアニメ": "アニメ",
    "TVアニメ": "アニメ",
    "劇場アニメ": "アニメ",
    "Webアニメ": "アニメ",
    "ゲーム": "ゲーム",
}


class WikipediaParseError(ValueError):
    """Wikipediaページの取得結果を解析できない場合のエラー。"""


def fetch_wikipedia_bold_appearances(page_title: str) -> dict[str, list[dict]]:
    """Wikipedia声優ページから太字出演候補を取得する。"""
    wikitext = fetch_wikipedia_wikitext(page_title)

    results: dict[str, list[dict]] = {}
    current_section = None
    for line in wikitext.splitlines():
        heading_match = re.match(r"^(?P<marks>={2,4})\s*(?P<title>.+?)\s*(?P=marks)$", line)
        if heading_match:
            heading = clean_wikitext(heading_match.group("title"))
            if heading in TARGET_HEADINGS:
                current_section = TARGET_HEADINGS[heading]
            elif len(heading_match.group("marks")) <= 3:
                current_section = None
            continue

        if current_section is None or not line.lstrip().startswith("*"):
            continue
        if "'''" not in line:
            continue

        parsed = parse_bold_wikitext_line(line)
        if parsed is None:
            continue
        results.setdefault(current_section, [])
        if parsed not in results[current_section]:
            results[current_section].append(parsed)

    return results


def fetch_wikipedia_wikitext(page_title: str) -> str:
    """Wikipediaページのウィキテキストを取得する。"""
    response = requests.get(
        WIKIPEDIA_API_URL,
        headers=HEADERS,
        params={
            "action": "parse",
            "page": page_title,
            "prop": "wikitext",
            "format": "json",
        },
        timeout=(5, 30),
    )
    response.raise_for_status()
    data = response.json()
    if "error" in data:
        raise WikipediaParseError(data["error"].get("info", "Wikipedia API error"))
    return data.get("parse", {}).get("wikitext", {}).get("*", "")


def parse_bold_wikitext_line(line: str) -> dict | None:
    """太字を含む出演行から作品名と役名候補を取り出す。"""
    text = clean_wikitext(line.lstrip("* "))
    if not text:
        return None

    title = strip_parenthesized_text(text)
    character = ""
    bold_texts = extract_bold_texts(line)

    paren_match = re.search(r"（(?P<inside>[^（）]+)）", text)
    if paren_match:
        inside = normalize_spaces(paren_match.group("inside"))
        parts = [part.strip() for part in re.split(r"[、,]", inside) if part.strip()]
        matched_parts = [
            part
            for part in parts
            if any(part in bold_text or bold_text in part for bold_text in bold_texts)
        ]
        character = "、".join(matched_parts or parts)

    title = clean_title(title)
    character = clean_character(character)
    if not title:
        return None

    return {
        "title": title,
        "character": character,
        "raw": text,
    }


def extract_bold_texts(line: str) -> list[str]:
    """ウィキテキスト内の太字部分を抽出する。"""
    return [
        clean_wikitext(match)
        for match in re.findall(r"'''(.+?)'''", line)
        if clean_wikitext(match)
    ]


def clean_wikitext(text: str) -> str:
    """リンク・脚注・太字記法を表示用テキストに寄せる。"""
    text = re.sub(r"<ref[^>/]*/>", "", text)
    text = re.sub(r"<ref[^>]*>.*?</ref>", "", text)
    text = re.sub(r"\{\{[^{}]*\}\}", "", text)
    text = text.replace("'''", "")
    text = re.sub(r"\[\[[^|\]]+\|([^\]]+)\]\]", r"\1", text)
    text = re.sub(r"\[\[([^\]]+)\]\]", r"\1", text)
    text = re.sub(r"\[https?://[^\s\]]+\s*([^\]]*)\]", r"\1", text)
    return normalize_spaces(text)


def normalize_spaces(text: str) -> str:
    """空白と改行を1つの半角スペースにそろえる。"""
    return re.sub(r"\s+", " ", text).strip()


def remove_references(text: str) -> str:
    """脚注番号を取り除く。"""
    return re.sub(r"\[\d+\]", "", text)


def strip_parenthesized_text(text: str) -> str:
    """作品名候補として括弧以降を落とす。"""
    return re.split(r"（", text, maxsplit=1)[0]


def clean_title(title: str) -> str:
    """作品名の装飾を整える。"""
    title = normalize_spaces(title).strip("「」『』")
    title = re.sub(r"^\d{4}年\s*", "", title)
    return normalize_spaces(title)


def clean_character(character: str) -> str:
    """役名候補の装飾を整える。"""
    character = normalize_spaces(character)
    character = re.sub(r"\s*-\s*.*$", "", character)
    return character


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Wikipedia声優ページから太字出演候補を取得します。"
    )
    parser.add_argument("page_title", help='Wikipediaページ名。例: "長谷川育美"')
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        result = fetch_wikipedia_bold_appearances(args.page_title)
    except requests.exceptions.Timeout as error:
        print(f"エラー: Wikipediaへの接続がタイムアウトしました: {error}")
        raise SystemExit(1) from error
    except requests.exceptions.RequestException as error:
        print(f"エラー: Wikipediaへの通信に失敗しました: {error}")
        raise SystemExit(1) from error
    except WikipediaParseError as error:
        print(f"エラー: Wikipediaページを解析できません: {error}")
        raise SystemExit(1) from error

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
