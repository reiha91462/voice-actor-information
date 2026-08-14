import json
import sys
from html import escape
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components


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
        "source_url": "https://holypeak.com/talent/voice-actor-women/%e4%b8%83%e7%80%ac-%e3%81%a4%e3%82%80%e3%81%8e/",
        "representative_works": [
            {
                "category": "ゲーム",
                "title": "学園アイドルマスター",
                "character": "有村麻央",
            }
        ],
        "social_links": {
            "twitter": {
                "username": "tsumugi_nanase",
                "profile_url": "https://x.com/tsumugi_nanase",
                "label": "本人X",
                "kind": "person",
                "featured_posts_embed_mode": "embed",
                "featured_posts": [
                    {
                        "title": "初投稿",
                        "url": "https://x.com/tsumugi_nanase/status/1780557242510766468?s=20",
                    },
                    {
                        "title": "セレクト投稿 1",
                        "url": "https://x.com/tsumugi_nanase/status/1885948979864842319?s=20",
                    },
                    {
                        "title": "セレクト投稿 2",
                        "url": "https://x.com/tsumugi_nanase/status/2063601199895716009?s=20",
                    },
                ],
            },
            "instagram": {
                "username": "nanase_tsumugi.61",
                "profile_url": "https://www.instagram.com/nanase_tsumugi.61/?hl=ja",
                "label": "本人Instagram",
                "kind": "person",
            },
        },
        "data_path": APP_DIR / "nanase_tsumugi_data.json",
        "analysis_path": APP_DIR / "nanase_tsumugi_voice_analyses.json",
        "nested_key": None,
    },
    "toyama_nao": {
        "name": "東山 奈央",
        "roman_name": "Toyama Nao",
        "sort_name": "とうやま なお",
        "agency": "インテンション",
        "source_url": "https://intention-k.com/profile/nao_toyama",
        "representative_works": [],
        "social_links": {},
        "data_path": APP_DIR / "toyama_nao_data.json",
        "analysis_path": APP_DIR / "toyama_nao_voice_analyses.json",
        "nested_key": "東山 奈央",
    },
    "hasegawa_ikumi": {
        "name": "長谷川 育美",
        "roman_name": "Hasegawa Ikumi",
        "sort_name": "はせがわ いくみ",
        "agency": "ラクーンドッグ",
        "source_url": "https://www.raccoon-dog.co.jp/talent/r11-hasegawa.html",
        "representative_works": [],
        "social_links": {
            "twitter": {
                "username": "Ikumi_Radio",
                "profile_url": "https://x.com/Ikumi_Radio",
                "label": "長谷川育美公式ラジオ（決）",
                "kind": "program",
                "featured_posts_embed_mode": "embed",
                "featured_posts": [
                    {
                        "title": "初投稿",
                        "url": "https://x.com/Ikumi_Radio/status/1818889443539140989?s=20",
                    },
                    {
                        "title": "セレクト投稿 1",
                        "url": "https://x.com/Ikumi_Radio/status/1879111718166831225?s=20",
                    },
                    {
                        "title": "セレクト投稿 2",
                        "url": "https://x.com/Ikumi_Radio/status/1924773343443448064?s=20",
                    },
                ],
            }
        },
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


def format_sample_title_prefix(sample_index: int, sample_count: int) -> str:
    """同じ分類に複数サンプルがある場合だけ番号を付ける。"""
    if sample_count <= 1:
        return ""
    return format_sample_number(sample_index)


def get_fixed_voice_sample_title(group_name: str) -> str | None:
    """AI解析せず固定表示にするボイス分類の説明を返す。"""
    normalized_group_name = group_name.strip()
    if normalized_group_name in {"まとめ", "まとめボイス"}:
        return "自己紹介+全て"
    if normalized_group_name == "クレジット":
        return "自己紹介"
    return None


def show_voice_sample_title(sample_title: str) -> None:
    """各ボイスサンプルの説明を、分類見出しより小さく表示する。"""
    safe_sample_title = escape(sample_title)
    st.markdown(
        f"""
<div style="
  font-size: 0.98rem;
  font-weight: 600;
  line-height: 1.5;
  margin: 0.35rem 0 0.25rem;
">
  {safe_sample_title}
</div>
""".strip(),
        unsafe_allow_html=True,
    )


def get_representative_works(actor: dict, voice_actor_data: dict) -> list[dict]:
    """JSONに保存された代表作を優先して返す。"""
    representative_works = voice_actor_data.get("representative_works")
    if isinstance(representative_works, list) and representative_works:
        return [
            work
            for work in representative_works[:3]
            if isinstance(work, dict) and work.get("title")
        ]

    fallback_works = actor.get("representative_works", [])
    return [
        work
        for work in fallback_works[:3]
        if isinstance(work, dict) and work.get("title")
    ]


def format_representative_work(work: dict) -> str:
    """代表作を表示用の1行に整える。"""
    title = work.get("title", "")
    character = work.get("character", "")
    category = work.get("category", "")

    label = f"{title}（{character}）" if character else title
    return f"{label} / {category}" if category else label


def get_social_links(actor: dict, voice_actor_data: dict) -> dict:
    """JSONに保存されたSNS情報を優先して返す。"""
    social_links = voice_actor_data.get("social_links")
    if isinstance(social_links, dict) and social_links:
        return social_links
    return actor.get("social_links", {})


def get_source_url(actor: dict, voice_actor_data: dict) -> str:
    """公式サイトの出典URLを返す。"""
    source_url = voice_actor_data.get("source_url") or actor.get("source_url", "")
    return str(source_url).strip()


def show_official_website(social_links: dict) -> None:
    """本人公式サイトへのリンクを表示する。"""
    if not isinstance(social_links, dict) or not social_links:
        return

    website = social_links.get("website") or social_links.get("homepage")
    website_html = build_generic_link_button_html(
        website,
        default_label="本人公式サイト",
        action_label="公式サイトを見る",
        background="#2563eb",
    )
    if not website_html:
        return

    st.markdown("#### 公式サイト")
    components.html(website_html, height=105)


def show_social_links(social_links: dict) -> None:
    """SNS、YouTube、ピックアップポストを表示する。"""
    if not isinstance(social_links, dict) or not social_links:
        return

    instagram = social_links.get("instagram")
    twitter = social_links.get("twitter") or social_links.get("x")
    youtube = social_links.get("youtube")
    if not instagram and not twitter and not youtube:
        return

    st.subheader("SNS")
    sns_buttons = [
        build_instagram_button_html(instagram),
        build_twitter_button_html(twitter),
    ]
    sns_buttons = [button for button in sns_buttons if button]
    if sns_buttons:
        columns = st.columns(len(sns_buttons))
        for column, button_html in zip(columns, sns_buttons):
            with column:
                components.html(button_html, height=110)

    youtube_html = build_generic_link_button_html(
        youtube,
        default_label="YouTube",
        action_label="YouTubeを見る",
        background="#ff0033",
    )
    if youtube_html:
        components.html(youtube_html, height=105)

    featured_posts = get_featured_twitter_posts(twitter)
    if featured_posts:
        embed_mode = str(twitter.get("featured_posts_embed_mode", "card")).strip()
        show_featured_twitter_posts(featured_posts, embed_mode)


def build_instagram_button_html(instagram: dict | None) -> str:
    """InstagramプロフィールへのリンクボタンHTMLを作る。"""
    if not isinstance(instagram, dict):
        return ""

    username = str(instagram.get("username", "")).strip().lstrip("@")
    label = str(instagram.get("label", "Instagram")).strip() or "Instagram"
    profile_url = str(instagram.get("profile_url", "")).strip()
    if not profile_url and username:
        profile_url = f"https://www.instagram.com/{username}/"
    if not profile_url:
        return ""

    safe_url = escape(profile_url, quote=True)
    safe_username = escape(username)
    safe_label = escape(label)
    account_label = f"@{safe_username}" if safe_username else "公式プロフィール"
    return f"""
<div style="font-family: sans-serif;">
  <a href="{safe_url}" target="_blank" rel="noopener noreferrer"
     style="
       display: block;
       padding: 18px 20px;
       border-radius: 8px;
       color: #fff;
       text-decoration: none;
       background: linear-gradient(135deg, #f58529, #dd2a7b, #8134af);
       box-shadow: 0 4px 14px rgba(0, 0, 0, 0.16);
     ">
    <div style="font-size: 14px; opacity: 0.9;">{safe_label}</div>
    <div style="font-size: 18px; font-weight: 700; margin-top: 4px;">
      Instagramを見る
    </div>
    <div style="font-size: 13px; margin-top: 6px; opacity: 0.9;">{account_label}</div>
  </a>
</div>
""".strip()


def build_generic_link_button_html(
    link_data: dict | None,
    default_label: str,
    action_label: str,
    background: str,
) -> str:
    """汎用外部リンクボタンHTMLを作る。"""
    if not isinstance(link_data, dict):
        return ""

    profile_url = str(link_data.get("profile_url") or link_data.get("url") or "").strip()
    if not profile_url:
        return ""

    label = str(link_data.get("label", default_label)).strip() or default_label
    username = str(link_data.get("username", "")).strip().lstrip("@")
    account_label = f"@{username}" if username else profile_url
    safe_url = escape(profile_url, quote=True)
    safe_label = escape(label)
    safe_action_label = escape(action_label)
    safe_account_label = escape(account_label)
    safe_background = escape(background, quote=True)
    return f"""
<div style="font-family: sans-serif;">
  <a href="{safe_url}" target="_blank" rel="noopener noreferrer"
     style="
       display: block;
       padding: 18px 20px;
       border-radius: 8px;
       color: #fff;
       text-decoration: none;
       background: {safe_background};
       box-shadow: 0 4px 14px rgba(0, 0, 0, 0.16);
     ">
    <div style="font-size: 14px; opacity: 0.9;">{safe_label}</div>
    <div style="font-size: 18px; font-weight: 700; margin-top: 4px;">
      {safe_action_label}
    </div>
    <div style="font-size: 13px; margin-top: 6px; opacity: 0.85;
                overflow-wrap: anywhere;">{safe_account_label}</div>
  </a>
</div>
""".strip()


def build_twitter_button_html(twitter: dict | None) -> str:
    """XプロフィールへのリンクボタンHTMLを作る。"""
    if not isinstance(twitter, dict):
        return ""

    username = str(twitter.get("username", "")).strip().lstrip("@")
    profile_url = str(twitter.get("profile_url", "")).strip()
    if not profile_url and username:
        profile_url = f"https://x.com/{username}"
    if not profile_url:
        return ""

    label = str(twitter.get("label", "X")).strip() or "X"
    safe_url = escape(profile_url, quote=True)
    safe_username = escape(username)
    safe_label = escape(label)
    account_label = f"@{safe_username}" if safe_username else "公式プロフィール"
    return f"""
<div style="font-family: sans-serif;">
  <a href="{safe_url}" target="_blank" rel="noopener noreferrer"
     style="
       display: block;
       padding: 18px 20px;
       border-radius: 8px;
       color: #fff;
       text-decoration: none;
       background: #111;
       box-shadow: 0 4px 14px rgba(0, 0, 0, 0.16);
     ">
    <div style="font-size: 14px; opacity: 0.85;">{safe_label}</div>
    <div style="font-size: 18px; font-weight: 700; margin-top: 4px;">
      Xを見る
    </div>
    <div style="font-size: 13px; margin-top: 6px; opacity: 0.85;">{account_label}</div>
  </a>
</div>
""".strip()


def get_featured_twitter_posts(twitter: dict | None) -> list[dict]:
    """Xのピックアップポスト表示用データを最大3件返す。"""
    if not isinstance(twitter, dict):
        return []

    posts = (
        twitter.get("featured_posts")
        or twitter.get("recent_posts")
        or twitter.get("recent_tweets")
        or []
    )
    if not isinstance(posts, list):
        return []

    return [
        post
        for post in posts[:3]
        if isinstance(post, dict)
        and (
            str(post.get("text", "")).strip()
            or str(post.get("title", "")).strip()
            or str(post.get("url", "")).strip()
        )
    ]


def show_featured_twitter_posts(posts: list[dict], embed_mode: str = "card") -> None:
    """Xのピックアップポストを横並びカードで表示する。"""
    st.markdown("#### ピックアップポスト")
    columns = st.columns(len(posts))
    for column, post in zip(columns, posts):
        with column:
            if embed_mode == "embed":
                components.html(build_twitter_embed_html(post), height=430)
            else:
                st.markdown(
                    build_twitter_post_card_html(post),
                    unsafe_allow_html=True,
                )


def build_twitter_embed_html(post: dict) -> str:
    """X公式の単体ポスト埋め込みHTMLを作る。"""
    post_url = normalize_x_post_url(str(post.get("url", "")).strip())
    if not post_url:
        return build_twitter_post_card_html(post)

    safe_url = escape(post_url, quote=True)
    return f"""
<blockquote class="twitter-tweet">
  <a href="{safe_url}"></a>
</blockquote>
<script async src="https://platform.twitter.com/widgets.js" charset="utf-8"></script>
""".strip()


def normalize_x_post_url(post_url: str) -> str:
    """Xの投稿URLを公式埋め込みで扱いやすい形に整える。"""
    if not post_url:
        return ""
    normalized = post_url.replace("https://x.com/", "https://twitter.com/")
    normalized = normalized.split("?", 1)[0]
    return normalized


def build_twitter_post_card_html(post: dict) -> str:
    """XポストカードHTMLを作る。"""
    text = escape(str(post.get("text", "")).strip())
    title = escape(str(post.get("title", "")).strip() or "ピックアップポスト")
    posted_at = escape(str(post.get("posted_at", "")).strip())
    post_url = str(post.get("url", "")).strip()
    safe_url = escape(post_url, quote=True)

    footer = posted_at if posted_at else "X"
    if safe_url:
        footer_html = (
            f'<a href="{safe_url}" target="_blank" rel="noopener noreferrer" '
            'style="color: #111; text-decoration: none; font-weight: 700;">'
            f"{footer} を開く</a>"
        )
    else:
        footer_html = footer

    return f"""
<div style="
  min-height: 132px;
  padding: 16px;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  background: #fff;
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.05);
">
  <div style="
    color: #111827;
    font-size: 15px;
    font-weight: 700;
    margin-bottom: 8px;
  ">{title}</div>
  <div style="
    color: #111827;
    font-size: 14px;
    line-height: 1.6;
    white-space: pre-wrap;
    overflow-wrap: anywhere;
  ">{text if text else "選んだポストをXで開く"}</div>
  <div style="
    margin-top: 14px;
    color: #6b7280;
    font-size: 12px;
  ">{footer_html}</div>
</div>
""".strip()


def show_actor_selection() -> None:
    """最初の声優選択画面を表示する。"""
    st.title("🎙️ 声優情報")
    st.write("好きな声優を選択してください。")

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

    try:
        voice_actor_data = load_voice_actor_data(actor)
    except FileNotFoundError:
        st.error("声優データが見つかりません。")
        st.stop()
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as error:
        st.error(f"声優データの読み込みに失敗しました: {error}")
        st.stop()

    representative_works = get_representative_works(actor, voice_actor_data)
    social_links = get_social_links(actor, voice_actor_data)
    source_url = get_source_url(actor, voice_actor_data)

    st.title(f"{actor['name']}（{actor['roman_name']}）")
    st.subheader("声優情報")
    st.write(f"所属事務所：{actor['agency']}")
    if representative_works:
        st.write("代表作：")
        for work in representative_works:
            st.write(f"- {format_representative_work(work)}")
    else:
        st.write("代表作：未設定")
    show_official_website(social_links)
    show_social_links(social_links)

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
            sample_count = len(sample_urls)
            for sample_index, sample_url in enumerate(sample_urls, start=1):
                fixed_sample_title = get_fixed_voice_sample_title(group_name)
                if fixed_sample_title is not None:
                    show_voice_sample_title(fixed_sample_title)
                    st.audio(sample_url)
                    continue

                description = voice_analyses.get(sample_url)
                failure_message = failed_samples.get(sample_url)
                sample_title_prefix = format_sample_title_prefix(sample_index, sample_count)

                if description:
                    sample_title = f"{sample_title_prefix}{description}"
                elif failure_message:
                    sample_title = f"{sample_title_prefix}解析失敗"
                else:
                    sample_title = f"{sample_title_prefix}未解析"

                show_voice_sample_title(sample_title)
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

    show_source_notice(source_url)


def show_source_notice(source_url: str) -> None:
    """公式サイトから情報を引用している旨を表示する。"""
    if not source_url:
        return
    st.divider()
    st.caption(
        "出演歴・ボイスサンプル等の基本情報は、所属事務所の公式サイトを"
        "参照しています。"
    )
    st.markdown(f"出典：[所属事務所公式プロフィール]({source_url})")


selected_actor = st.session_state.get("selected_voice_actor")
if selected_actor not in VOICE_ACTORS:
    show_actor_selection()
else:
    show_actor_details(selected_actor)
