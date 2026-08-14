import re
from collections.abc import Callable
from urllib.parse import urljoin

from bs4 import BeautifulSoup


def normalize_text(text: str) -> str:
    """全角空白や改行を整理し、単語間の空白を1つにする。"""
    return re.sub(r"\s+", " ", text).strip()


def classify_voice_sample_by_label(label: str, value: str = "") -> str:
    """ボイスサンプルの表示ラベル・ファイル名から汎用的に分類する。"""
    label = normalize_text(label)
    value = normalize_text(value).lower()

    if "クレジット" in label or "credit" in value:
        return "クレジット"
    if "まとめ" in label:
        return "まとめボイス"
    if "ナレーション" in label or "ナレ" in label:
        return "ナレーション"
    if "セリフ" in label or "台詞" in label:
        return "セリフ"
    if "まとめ" in label or "all" in value:
        return "まとめボイス"
    if "narration" in value or "_na" in value:
        return "ナレーション"
    if "serifu" in value:
        return "セリフ"
    return "サンプル"


def extract_audio_tag_urls(soup: BeautifulSoup, base_url: str) -> list[str]:
    """audio/sourceタグに直書きされた音声URLを取得する。"""
    voice_samples = []
    for media in soup.select("audio[src], audio source[src]"):
        source_url = media.get("src")
        if not source_url:
            continue

        absolute_url = urljoin(base_url, source_url)
        if absolute_url not in voice_samples:
            voice_samples.append(absolute_url)

    return voice_samples


def extract_select_value_voice_sample_groups(
    soup: BeautifulSoup,
    base_url: str,
    *,
    select_selector: str,
    url_template: str,
    classifier: Callable[[str, str], str] = classify_voice_sample_by_label,
    skip_values: set[str] | None = None,
) -> dict[str, list[str]]:
    """select > option のvalueから音声URLを組み立てるタイプのサイト用。

    url_templateには `{value}` を含める。
    例: "/wp-content/themes/intention/media/sounds/profile/{value}.mp3"
    """
    skip_values = skip_values or {"", "coming_soon"}
    voice_sample_groups: dict[str, list[str]] = {}

    for option in soup.select(f"{select_selector} option[value]"):
        option_value = normalize_text(option.get("value", ""))
        label = normalize_text(option.get_text(" ", strip=True))
        if option_value in skip_values:
            continue

        sample_path = url_template.format(value=option_value)
        sample_url = urljoin(base_url, sample_path)
        group_name = classifier(label, option_value)

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
