import json

import streamlit as st


st.set_page_config(
    page_title="声優出演情報ダッシュボード",
    layout="wide",
)

st.title("🎙️ 声優情報ダッシュボード")
st.header("七瀬 つむぎ")

try:
    with open("nanase_tsumugi_data.json", "r", encoding="utf-8") as file:
        voice_actor_data = json.load(file)
except FileNotFoundError:
    st.error(
        "nanase_tsumugi_data.json が見つかりません。"
        "JSONファイルがカレントディレクトリにあるか確認してください。"
    )
    st.stop()
except (json.JSONDecodeError, UnicodeDecodeError) as error:
    st.error(f"JSONファイルの読み込みに失敗しました: {error}")
    st.stop()

# AI解析結果は未作成でもダッシュボードを表示できるようにする
voice_analyses = {}
failed_samples = {}
try:
    with open(
        "nanase_tsumugi_voice_analyses.json",
        "r",
        encoding="utf-8",
    ) as file:
        analysis_data = json.load(file)
        voice_analyses = analysis_data.get("voice_sample_analyses", {})
        failed_samples = analysis_data.get("failed_samples", {})
except FileNotFoundError:
    st.info(
        "AI解析結果はまだありません。"
        "analyze_voice.py を実行すると表示されます。"
    )
except (json.JSONDecodeError, UnicodeDecodeError) as error:
    st.warning(f"AI解析結果を読み込めませんでした: {error}")

st.subheader("📺 出演歴")
appearances = voice_actor_data.get("appearances", {})

if appearances:
    for category, works in appearances.items():
        with st.expander(category):
            for work in works:
                st.write(f"- {work}")
else:
    st.info("出演歴のデータはありません。")

st.subheader("🎧 ボイスサンプル")
voice_samples = voice_actor_data.get("voice_samples", [])

if voice_samples:
    for index, sample_url in enumerate(voice_samples, start=1):
        description = voice_analyses.get(sample_url)
        failure_message = failed_samples.get(sample_url)
        if description:
            sample_title = f"サンプル{index}：{description}"
        elif failure_message:
            sample_title = f"サンプル{index}：解析失敗"
        else:
            sample_title = f"サンプル{index}：未解析"

        st.markdown(f"#### {sample_title}")
        st.audio(sample_url)

    st.caption(
        "※各ボイスサンプルの説明は、AIが音声から声質や"
        "キャラクターの雰囲気を分析した推定結果です。"
    )
else:
    st.info("ボイスサンプルのデータはありません。")
