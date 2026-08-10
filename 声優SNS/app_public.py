import json
import sys
from pathlib import Path

import streamlit as st


APP_DIR = Path(__file__).resolve().parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from agency_rules import get_default_voice_sample_group

NUMBER_LABELS = ["①", "②", "③", "④", "⑤", "⑥", "⑦", "⑧", "⑨", "⑩"]

VOICE_ACTORS = {
    "nanase_tsumugi": {
        "name": "七瀬 つむぎ",
        "roman_name": "Nanase Tsumugi",
        "sort_name": "ななせ つむぎ",
        "agency": "ホーリーピーク",
        "representative_works": ["代表作A", "代表作B", "代表作C"],
        "data_path": APP_DIR / "nanase_tsumugi_data.json",
        "analysis_path": APP_DIR / "nanase_tsumugi_voice_analyses.json",
        "nested_key": None,
    },
    "hasegawa_ikumi": {
        "name": "長谷川 育美",
        "roman_name": "Hasegawa Ikumi",
        "sort_name": "はせがわ いくみ",
        "agency": "ラクーンドッグ",
        "representative_works": ["代表作A", "代表作B", "代表作C"],
        "data_path": APP_DIR / "hasegawa_ikumi_data.json",
        "analysis_path": APP_DIR / "hasegawa_ikumi_voice_analyses.json",
        "nested_key": "長谷川 育美",
    },
}

st.set_page_config(
    page_title="声優出演情報",
    layout="wide",
)


def load_json(json_path: Path) -> dict:
    """UTF-8のJSONファイルを辞書として読み込む。"""
    with json_path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, dict):
        raise ValueError("JSONのルートが辞書形式ではありません。")
    return data


def load_voice_actor_data(actor: dict) -> dict:
    """事務所ごとに異なるJSON構造を共通形式へ変換する。"""
    raw_data = load_json(actor["data_path"])
    nested_key = actor["nested_key"]
    if nested_key is None:
        return raw_data

    actor_data = raw_data.get(nested_key)
    if not isinstance(actor_data, dict):
        raise ValueError(f"{nested_key} のデータが見つかりません。")
    return actor_data


def load_voice_analyses(analysis_path: Path | None) -> tuple[dict, dict]:
    """AI解析結果を読み込む。未作成の場合は空の辞書を返す。"""
    if analysis_path is None or not analysis_path.exists():
        return {}, {}

    analysis_data = load_json(analysis_path)
    analyses = analysis_data.get("voice_sample_analyses", {})
    failures = analysis_data.get("failed_samples", {})
    return analyses, failures


def get_voice_sample_groups(
    voice_actor_data: dict,
    default_group_name: str = "サンプル",
) -> dict[str, list[str]]:
    """分類付きボイスサンプルを返す。旧形式の voice_samples も扱う。"""
    voice_sample_groups = voice_actor_data.get("voice_sample_groups")
    if isinstance(voice_sample_groups, dict):
        groups = {
            group_name: [
                sample_url
                for sample_url in sample_urls
                if isinstance(sample_url, str) and sample_url.strip()
            ]
            for group_name, sample_urls in voice_sample_groups.items()
            if isinstance(group_name, str) and isinstance(sample_urls, list)
        }
        groups = {
            group_name: sample_urls
            for group_name, sample_urls in groups.items()
            if sample_urls
        }
        if groups:
            return groups

    voice_samples = voice_actor_data.get("voice_samples", [])
    if not isinstance(voice_samples, list):
        return {}

    sample_urls = [
        sample_url
        for sample_url in voice_samples
        if isinstance(sample_url, str) and sample_url.strip()
    ]
    return {default_group_name: sample_urls} if sample_urls else {}


def format_sample_number(index: int) -> str:
    """ボイス分類内の番号を表示用に整える。"""
    if index <= len(NUMBER_LABELS):
        return NUMBER_LABELS[index - 1]
    return f"{index}."


def show_actor_selection() -> None:
    """最初の声優選択画面を表示する。"""
    st.title("🎙️ 声優情報")
    st.write("出演歴やボイスサンプルを見たい声優を選択してください。")

    sorted_actor_ids = sorted(
        VOICE_ACTORS,
        key=lambda key: VOICE_ACTORS[key].get("sort_name", VOICE_ACTORS[key]["name"]),
    )

    for actor_id in sorted_actor_ids:
        actor = VOICE_ACTORS[actor_id]
        if st.button(
            actor["name"],
            key=f"select_{actor_id}",
            help=f"{actor['agency']} 所属",
            use_container_width=True,
        ):
            st.session_state.selected_voice_actor = actor_id
            st.rerun()


def show_actor_details(actor_id: str) -> None:
    """選択された声優の出演歴とボイスサンプルを表示する。"""
    actor = VOICE_ACTORS[actor_id]

    if st.button("← 声優選択に戻る"):
        st.session_state.selected_voice_actor = None
        st.rerun()

    st.title(f"{actor['name']}（{actor['roman_name']}）")
    st.subheader("声優情報")
    st.write(f"所属事務所：{actor['agency']}")
    st.write(f"代表作：{', '.join(actor['representative_works'])}")

    try:
        voice_actor_data = load_voice_actor_data(actor)
    except FileNotFoundError:
        st.error("声優データが見つかりません。")
        st.stop()
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as error:
        st.error(f"声優データの読み込みに失敗しました: {error}")
        st.stop()

    try:
        voice_analyses, failed_samples = load_voice_analyses(actor["analysis_path"])
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
        voice_analyses, failed_samples = {}, {}
        st.warning("ボイスサンプルのAI解析結果を表示できません。")

    st.subheader("📺 出演歴")
    appearances = voice_actor_data.get("appearances", {})
    if appearances:
        for category, works in appearances.items():
            with st.expander(f"{category}（{len(works)}件）"):
                for work in works:
                    st.write(f"- {work}")
    else:
        st.info("出演歴のデータはありません。")

    st.subheader("🎧 ボイスサンプル")
    voice_sample_groups = get_voice_sample_groups(
        voice_actor_data,
        get_default_voice_sample_group(actor["agency"]),
    )
    if voice_sample_groups:
        for group_name, sample_urls in voice_sample_groups.items():
            st.markdown(f"### {group_name}")
            for sample_index, sample_url in enumerate(sample_urls, start=1):
                description = voice_analyses.get(sample_url)
                failure_message = failed_samples.get(sample_url)
                sample_number = format_sample_number(sample_index)

                if description:
                    sample_title = f"{sample_number}{description}"
                elif failure_message:
                    sample_title = f"{sample_number}解析失敗"
                else:
                    sample_title = f"{sample_number}未解析"

                st.markdown(f"#### {sample_title}")
                st.audio(sample_url)

        if voice_analyses:
            st.caption(
                "※各ボイスサンプルの説明は、AIが音声から声質や"
                "キャラクターの雰囲気を分析した推定結果です。"
            )
        else:
            st.caption("※この声優のボイスサンプルはまだAI解析されていません。")
    else:
        st.info("ボイスサンプルのデータはありません。")


selected_actor = st.session_state.get("selected_voice_actor")
if selected_actor not in VOICE_ACTORS:
    show_actor_selection()
else:
    show_actor_details(selected_actor)
