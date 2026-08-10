from pathlib import Path


AGENCY_RULES = {
    "ホーリーピーク": {
        "default_voice_sample_group": "セリフ",
    },
    "ラクーンドッグ": {
        "default_voice_sample_group": "サンプル",
        "voice_filename_groups": {
            "_all": "まとめボイス",
            "_na": "ナレーション",
        },
        "fallback_voice_sample_group": "セリフ",
    },
}


def get_default_voice_sample_group(agency: str) -> str:
    """事務所ごとの旧形式ボイスサンプル分類名を返す。"""
    rule = AGENCY_RULES.get(agency, {})
    return rule.get("default_voice_sample_group", "サンプル")


def classify_voice_sample_by_agency(agency: str, sample_url: str) -> str:
    """事務所ごとの命名規則でボイスサンプルを分類する。"""
    rule = AGENCY_RULES.get(agency, {})
    filename = Path(sample_url).name.lower()

    for marker, group_name in rule.get("voice_filename_groups", {}).items():
        if marker in filename:
            return group_name

    return rule.get("fallback_voice_sample_group", get_default_voice_sample_group(agency))
