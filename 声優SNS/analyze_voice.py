import argparse
import json
import os
import tempfile
import time
from pathlib import Path
from urllib.parse import urlparse

import requests
from google import genai
from google.genai import errors


MODEL_NAME = "gemini-3.6-flash"
SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_INPUT_PATH = SCRIPT_DIR / "nanase_tsumugi_data.json"
SKIP_ANALYSIS_GROUPS = {"まとめ", "まとめボイス", "クレジット"}
PROMPT = """
あなたはプロの音響監督です。
添付したボイスサンプルを聞き、声質と想定されるキャラクターの雰囲気を分析してください。
「元気で明るい少女」「落ち着いた大人の女性」「クールな少年」のように、
20文字以内の日本語で表現してください。説明や記号を付けず、結果のテキストだけを出力してください。
""".strip()


def download_audio(audio_url: str, destination: Path) -> None:
    """音声ファイルを1回だけダウンロードする。"""
    headers = {"User-Agent": "VoiceActorStudyAnalyzer/1.0 (educational use)"}
    with requests.get(
        audio_url,
        headers=headers,
        timeout=(5, 30),
        stream=True,
    ) as response:
        response.raise_for_status()
        with destination.open("wb") as file:
            for chunk in response.iter_content(chunk_size=64 * 1024):
                if chunk:
                    file.write(chunk)


def analyze_voice_sample(audio_url: str, client: genai.Client) -> str:
    """指定されたボイスサンプルをGeminiで分析する。"""
    uploaded_file = None
    audio_suffix = Path(urlparse(audio_url).path).suffix.lower()
    if audio_suffix not in {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"}:
        audio_suffix = ".audio"

    with tempfile.TemporaryDirectory(prefix="voice_sample_") as temp_dir:
        temp_path = Path(temp_dir) / f"sample{audio_suffix}"

        try:
            print(f"対象URL: {audio_url}")
            print("1. 音声ファイルをダウンロード中...")
            download_audio(audio_url, temp_path)

            print("2. Geminiへ音声ファイルをアップロード中...")
            uploaded_file = client.files.upload(file=temp_path)

            print("3. 音声を解析中...")
            response = client.models.generate_content(
                model=MODEL_NAME,
                contents=[PROMPT, uploaded_file],
            )

            description = (response.text or "").strip()
            if not description:
                raise RuntimeError("Geminiから空の応答が返されました。")
            return description

        finally:
            # TemporaryDirectoryにより、ローカルの音声は常に削除される。
            if uploaded_file is not None:
                try:
                    client.files.delete(name=uploaded_file.name)
                except Exception as cleanup_error:
                    print(
                        "警告: Gemini上の一時ファイルを削除できませんでした: "
                        f"{cleanup_error}"
                    )


def load_voice_sample_urls(json_path: Path) -> tuple[str, list[str]]:
    """平坦形式と声優名で入れ子になったJSONの両方を読み込む。"""
    with json_path.open("r", encoding="utf-8") as file:
        scraped_data = json.load(file)

    if not isinstance(scraped_data, dict):
        raise ValueError("JSONのルートが辞書形式ではありません。")

    if has_voice_samples(scraped_data):
        actor_name = json_path.stem.removesuffix("_data").replace("_", " ")
        actor_data = scraped_data
    else:
        candidates = [
            (name, data)
            for name, data in scraped_data.items()
            if isinstance(data, dict) and has_voice_samples(data)
        ]
        if len(candidates) != 1:
            raise ValueError(
                "声優データを特定できません。"
                "voice_samples または voice_sample_groups を持つ声優を"
                "1人だけ格納してください。"
            )
        actor_name, actor_data = candidates[0]

    valid_urls = collect_voice_sample_urls(actor_data)
    if not valid_urls:
        raise ValueError("解析対象のボイスサンプルURLがありません。")
    return actor_name, valid_urls


def has_voice_samples(actor_data: dict) -> bool:
    """旧形式または分類付き形式のボイスサンプルを持つか判定する。"""
    return isinstance(actor_data.get("voice_samples"), list) or isinstance(
        actor_data.get("voice_sample_groups"),
        dict,
    )


def collect_voice_sample_urls(actor_data: dict) -> list[str]:
    """分類の有無に関係なく、解析対象URLを重複なしで取り出す。"""
    urls = []
    voice_sample_groups = actor_data.get("voice_sample_groups")

    if isinstance(voice_sample_groups, dict):
        for group_name, sample_urls in voice_sample_groups.items():
            if isinstance(group_name, str) and group_name.strip() in SKIP_ANALYSIS_GROUPS:
                continue
            if not isinstance(sample_urls, list):
                continue
            urls.extend(sample_urls)
    else:
        voice_samples = actor_data.get("voice_samples", [])
        if isinstance(voice_samples, list):
            urls.extend(voice_samples)

    valid_urls = []
    for url in urls:
        if isinstance(url, str) and url.strip() and url not in valid_urls:
            valid_urls.append(url)
    return valid_urls


def default_output_path(input_path: Path) -> Path:
    """入力名の `_data` を `_voice_analyses` に置き換える。"""
    stem = input_path.stem
    if stem.endswith("_data"):
        stem = stem.removesuffix("_data")
    return input_path.with_name(f"{stem}_voice_analyses.json")


def load_existing_analyses(output_path: Path) -> dict[str, str]:
    """過去の成功結果を読み、再実行時の重複解析を防ぐ。"""
    if not output_path.exists():
        return {}
    with output_path.open("r", encoding="utf-8") as file:
        output_data = json.load(file)
    analyses = output_data.get("voice_sample_analyses", {})
    return analyses if isinstance(analyses, dict) else {}


def save_analysis_results(
    actor_name: str,
    analyses: dict[str, str],
    failures: dict[str, str],
    output_path: Path,
) -> None:
    """解析結果を日本語のままJSONに保存する。"""
    output_data = {
        "actor_name": actor_name,
        "voice_sample_analyses": analyses,
        "failed_samples": failures,
    }
    with output_path.open("w", encoding="utf-8") as file:
        json.dump(output_data, file, ensure_ascii=False, indent=4)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="スクレイピングJSON内の全ボイスサンプルをGeminiで解析します。"
    )
    parser.add_argument(
        "input_json",
        nargs="?",
        type=Path,
        default=DEFAULT_INPUT_PATH,
        help="スクレイピング結果JSON（省略時: nanase_tsumugi_data.json）",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="解析結果の保存先（省略時は入力ファイル名から自動生成）",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="過去の解析結果があっても全件を再解析する",
    )
    return parser.parse_args()


def resolve_input_path(input_path: Path) -> Path:
    """相対パスが見つからない場合はスクリプトと同じフォルダも探す。"""
    if input_path.exists() or input_path.is_absolute():
        return input_path.resolve()
    return (SCRIPT_DIR / input_path).resolve()


def main() -> None:
    args = parse_args()
    input_path = resolve_input_path(args.input_json)
    output_path = (
        args.output.resolve() if args.output is not None else default_output_path(input_path)
    )

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("エラー: 環境変数 GEMINI_API_KEY が設定されていません。")
        print('export GEMINI_API_KEY="Google AI Studioで発行した実際のAPIキー"')
        raise SystemExit(1)

    try:
        actor_name, voice_sample_urls = load_voice_sample_urls(input_path)
    except FileNotFoundError as error:
        print(f"エラー: スクレイピング結果が見つかりません: {input_path}")
        raise SystemExit(1) from error
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as error:
        print(f"エラー: スクレイピング結果を読み込めません: {error}")
        raise SystemExit(1) from error

    try:
        analyses = {} if args.force else load_existing_analyses(output_path)
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as error:
        print(f"エラー: 過去の解析結果を読み込めません: {error}")
        raise SystemExit(1) from error

    client = genai.Client(api_key=api_key)
    failures: dict[str, str] = {}
    total = len(voice_sample_urls)

    print(f"--- {actor_name} ボイス解析開始（全{total}件）---")
    for index, audio_url in enumerate(voice_sample_urls, start=1):
        print(f"\n===== {index}/{total} =====")
        if audio_url in analyses:
            print(f"解析済みのためスキップ: {analyses[audio_url]}")
            continue

        try:
            description = analyze_voice_sample(audio_url, client)
        except requests.exceptions.Timeout as error:
            message = f"音声ファイルの取得がタイムアウトしました: {error}"
        except requests.exceptions.RequestException as error:
            message = f"音声ファイルの取得に失敗しました: {error}"
        except errors.APIError as error:
            message = f"Gemini APIの呼び出しに失敗しました: {error}"
        except (OSError, RuntimeError) as error:
            message = f"音声解析に失敗しました: {error}"
        else:
            analyses[audio_url] = description
            print(f"【解析結果】: {description}")
            message = ""

        if message:
            failures[audio_url] = message
            print(f"エラー: {message}")

        # 配信元サーバーとAPIに連続して負荷をかけないようにする。
        if index < total:
            time.sleep(1)

    try:
        save_analysis_results(actor_name, analyses, failures, output_path)
    except OSError as error:
        print(f"エラー: 解析結果を保存できませんでした: {error}")
        raise SystemExit(1) from error

    print("\n--- ボイス解析完了 ---")
    print(f"成功: {len(analyses)}件 / 失敗: {len(failures)}件")
    print(f"保存先: {output_path}")


if __name__ == "__main__":
    main()
