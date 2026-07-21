from pathlib import Path
from io import BytesIO
from html import escape
import base64
import hashlib
import json
import tempfile
from datetime import datetime, timezone
from textwrap import dedent
from typing import Optional

import pandas as pd
import streamlit as st


RATING_COLUMNS = {
    "context_relevance_rating": "Context & Relevance",
    "emotionx_usage_rating": "EmotionX Usage",
    "language_alignment_rating": "Language Alignment",
    "safety_alignment_rating": "Safety Alignment",
}
RATING_MEANINGS = {1: "Very poor", 2: "Poor", 3: "Average", 4: "Good", 5: "Excellent"}

REVIEW_COLUMNS = [
    "review_choice",
    "final_response",
    "reviewer_notes",
    "reviewed_status",
]
COLUMN_MAPPING_VERSION = 6
COLUMN_MAPPING_PAGE = None
LLM_REVIEW_PAGE = None


def render_safe_html(markup: str) -> None:
    """Render HTML without allowing Markdown to expose indented source code."""
    compact_markup = "".join(
        line.strip() for line in dedent(str(markup)).splitlines()
    )
    st.markdown(compact_markup, unsafe_allow_html=True)


def install_navigation_history_support() -> None:
    """Keep navigation native so links work across Streamlit Cloud and mobile."""
    # Custom click interception previously called preventDefault() before trying
    # to navigate the parent window from a component iframe. Some browsers and
    # Streamlit Cloud sessions block that parent navigation, leaving every link
    # inert. Root-based anchors already create correct same-tab browser history.
    return None


class MemoryUpload(BytesIO):
    """UploadedFile-compatible in-memory file fetched from Google Drive."""

    def __init__(self, data: bytes, name: str):
        super().__init__(data)
        self.name = name
        self.size = len(data)


def _embed_theme_assets(markup: str) -> str:
    """Inline optimized theme artwork so it works behind every deployment proxy."""
    asset_dir = Path(__file__).resolve().parent / "static" / "embedded"
    for asset_path in asset_dir.glob("*.webp"):
        source_url = f"/app/static/{asset_path.stem}.png"
        data_url = "data:image/webp;base64," + base64.b64encode(asset_path.read_bytes()).decode("ascii")
        markup = markup.replace(source_url, data_url)
    return markup


def inject_app_theme() -> None:
    """Apply the dashboard's visual theme without changing widget behavior."""
    theme_markup = """
        <style>
        :root {
            --ink: #172033;
            --muted: #64748b;
            --brand: #6d5dfc;
            --brand-dark: #5145cd;
            --accent: #13b8a6;
            --surface: rgba(255, 255, 255, 0.88);
            --border: rgba(109, 93, 252, 0.16);
            --shadow-sm: 0 8px 24px rgba(38, 42, 72, 0.07);
            --shadow-md: 0 18px 48px rgba(52, 44, 120, 0.13);
            --radius-md: 15px;
            --radius-lg: 24px;
        }

        html { scroll-behavior:smooth; }
        body, .stApp { font-family:"Avenir Next","Helvetica Neue",Inter,ui-sans-serif,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; font-feature-settings:"kern" 1,"liga" 1; }
        h1,h2,h3,h4,h5,h6,.news-brand,.news-nav,.news-actions { font-family:"Avenir Next","Helvetica Neue",Inter,ui-sans-serif,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }

        header[data-testid="stHeader"] {
            background:rgba(247,248,252,.78);
            backdrop-filter:blur(16px) saturate(145%);
            border-bottom:1px solid rgba(109,93,252,.09);
        }
        [data-testid="stNavigation"] {
            padding:.35rem .6rem;
            border:1px solid rgba(109,93,252,.1);
            border-radius:14px;
            background:rgba(255,255,255,.72);
            box-shadow:0 8px 25px rgba(44,47,83,.07);
        }
        [data-testid="stNavigation"] a {
            border-radius:10px !important;
            font-size:.78rem !important;
            font-weight:700 !important;
            transition:background .18s ease, transform .18s ease !important;
        }
        [data-testid="stNavigation"] a:hover { background:#f0edff !important; transform:translateY(-1px); }

        .stApp {
            background:
                linear-gradient(135deg, rgba(109,93,252,.11), transparent 28%),
                linear-gradient(225deg, rgba(19,184,166,.08), transparent 25%),
                #f7f8fc;
            color: var(--ink);
        }

        .creative-backdrop {
            position: fixed;
            inset: 0;
            z-index: 0;
            overflow: hidden;
            pointer-events: none;
        }

        .creative-backdrop::before {
            content: none;
            position: absolute;
            left: -30px;
            bottom: -24px;
            width: 230px;
            height: 270px;
            opacity: .12;
            background:
                radial-gradient(ellipse at 28% 76%, #a24e6d 0 12%, transparent 13%),
                radial-gradient(ellipse at 50% 60%, #d97472 0 13%, transparent 14%),
                radial-gradient(ellipse at 20% 48%, #7c526c 0 11%, transparent 12%),
                radial-gradient(ellipse at 55% 34%, #d97472 0 12%, transparent 13%),
                radial-gradient(ellipse at 25% 20%, #a24e6d 0 10%, transparent 11%),
                linear-gradient(68deg, transparent 48%, #8f5269 49% 51%, transparent 52%);
            transform: rotate(-13deg);
            animation: botanical-sway 6s ease-in-out infinite alternate;
            transform-origin: left bottom;
        }

        .creative-backdrop::after {
            content: none;
            position: absolute;
            right: 7vw;
            top: 0;
            width: 320px;
            height: 120px;
            opacity: .12;
            background:
                linear-gradient(90deg, transparent 14%, #774762 14% 14.7%, transparent 14.7%),
                linear-gradient(90deg, transparent 49%, #774762 49% 49.7%, transparent 49.7%),
                linear-gradient(90deg, transparent 82%, #774762 82% 82.7%, transparent 82.7%),
                radial-gradient(ellipse at 14% 53%, #9b526f 0 7%, transparent 7.5%),
                radial-gradient(ellipse at 49% 79%, #9b526f 0 8%, transparent 8.5%),
                radial-gradient(ellipse at 82% 45%, #9b526f 0 7%, transparent 7.5%);
        }
        @keyframes botanical-sway { to { transform:rotate(-8deg) translateX(7px); } }

        .creative-shape {
            position: absolute;
            opacity: 0.055;
            will-change: transform;
        }

        .shape-ring-purple {
            width: 190px;
            height: 190px;
            left: -115px;
            top: 23vh;
            border: 28px solid #7c65ff;
            border-radius: 50%;
            animation: crisp-float-a 11s ease-in-out infinite alternate;
        }

        .shape-square-yellow {
            width: 115px;
            height: 115px;
            right: -68px;
            top: 12vh;
            border: 18px solid #ffbd3e;
            border-radius: 30px;
            transform: rotate(18deg);
            animation: crisp-spin 18s linear infinite;
        }

        .shape-pill-pink {
            width: 180px;
            height: 66px;
            right: -105px;
            top: 55vh;
            border-radius: 999px;
            background: #ff72aa;
            transform: rotate(-24deg);
            animation: crisp-float-b 9s ease-in-out infinite alternate;
        }

        .shape-triangle-teal {
            left: -28px;
            bottom: 6vh;
            width: 0;
            height: 0;
            border-left: 62px solid transparent;
            border-right: 62px solid transparent;
            border-bottom: 108px solid #19bfa9;
            transform: rotate(-16deg);
            animation: crisp-float-c 13s ease-in-out infinite alternate;
        }

        .shape-cross-purple {
            left: -12px;
            top: 72vh;
            width: 78px;
            height: 20px;
            border-radius: 8px;
            background: #6d5dfc;
            animation: crisp-spin 15s linear infinite reverse;
        }

        .shape-cross-purple::after {
            content: "";
            position: absolute;
            left: 29px;
            top: -29px;
            width: 20px;
            height: 78px;
            border-radius: 8px;
            background: #6d5dfc;
        }

        @keyframes crisp-float-a {
            to { transform: translate(32px, -24px) rotate(12deg); }
        }
        @keyframes crisp-float-b {
            to { transform: translate(-38px, 30px) rotate(-12deg); }
        }
        @keyframes crisp-float-c {
            to { transform: translate(26px, -32px) rotate(8deg); }
        }
        @keyframes crisp-spin {
            to { transform: rotate(378deg); }
        }

        .block-container {
            position: relative;
            z-index: 1;
            max-width: 1480px;
            padding-top: 1.2rem;
            padding-bottom: 4rem;
            padding-left: 2rem;
            padding-right: 2rem;
            margin-top: 1rem;
            margin-bottom: 2rem;
            border: 1px solid rgba(255,255,255,.7);
            border-radius: 30px;
            background: rgba(255,255,255,.82);
            box-shadow: 0 28px 75px rgba(52,44,120,.12);
            backdrop-filter: saturate(115%);
        }

        .block-container:has(.landing-hero),
        .block-container:has(.mira-story) {
            max-width: none;
            width: 100%;
            padding: 1.1rem;
            border: 0;
            background: transparent;
            box-shadow: none;
        }
        .stApp:has(.landing-hero) .creative-backdrop,
        .stApp:has(.mira-story) .creative-backdrop { display:none; }
        .block-container:has(.mira-story) { padding:0; }

        .block-container:has(.workspace-page-marker) {
            max-width: none;
            width: 100%;
            min-height: calc(100vh - 4rem);
            margin: 0;
            padding: 1.6rem clamp(1.2rem, 3vw, 3.5rem) 4rem;
            border: 0;
            border-radius: 0;
            background: transparent;
            box-shadow: none;
        }
        .stApp:has(.workspace-page-marker) {
            background-color:#f6eddd;
            background-image:linear-gradient(90deg,rgba(246,237,221,.12),rgba(246,237,221,.03)),url('/app/static/mira-upload-world-v1.png');
            background-position:center top;
            background-size:cover;
            background-repeat:no-repeat;
            background-attachment:fixed;
        }
        .stApp:has(.feature-page-marker) { background-color:#f7efdf; background-image:linear-gradient(rgba(247,239,223,.04),rgba(247,239,223,.04)),url('/app/static/mira-review-features-world-v1.png'); background-position:center top; background-size:cover; background-repeat:no-repeat; background-attachment:fixed; }
        .stApp:has(.llm-upload-page-marker) { background-color:#e9f3f6; background-image:linear-gradient(90deg,rgba(233,243,246,.03),rgba(255,250,240,.02)),url('/app/static/mira-llm-upload-world-v3.png'); background-position:center top; background-size:cover; background-repeat:no-repeat; background-attachment:fixed; }
        .stApp:has(.mapping-page-marker) {
            background-color:#eaf1f4;
            background-image:
                radial-gradient(circle at 9% 15%,rgba(239,109,90,.18) 0 5px,transparent 6px),
                radial-gradient(circle at 88% 20%,rgba(19,169,148,.18) 0 7px,transparent 8px),
                linear-gradient(rgba(25,100,123,.055) 1px,transparent 1px),
                linear-gradient(90deg,rgba(25,100,123,.055) 1px,transparent 1px),
                linear-gradient(135deg,#edf6f5 0%,#f8f2e8 52%,#e9eef8 100%);
            background-size:auto,auto,34px 34px,34px 34px,cover;
            background-attachment:fixed;
        }
        .stApp:has(.evaluation-page-marker) {
            background-color:#eef3f5;
            background-image:
                radial-gradient(circle at 8% 18%,rgba(19,169,148,.11),transparent 24%),
                radial-gradient(circle at 92% 12%,rgba(109,93,252,.1),transparent 27%),
                linear-gradient(135deg,#f4f8f7,#f8f5ef 52%,#eef1f8);
            background-attachment:fixed;
        }
        .block-container:has(.evaluation-page-marker) {
            max-width:none;
            width:100%;
            min-height:100vh;
            margin:0;
            padding:1.6rem clamp(1.2rem,3vw,3.5rem) 4rem;
            border:0;
            border-radius:0;
            background:transparent;
            box-shadow:none;
            backdrop-filter:none;
        }
        .block-container:has(.mapping-page-marker) {
            max-width:1180px;
            min-height:auto;
            margin:5.8rem auto 4rem;
            padding:clamp(1.4rem,3vw,2.8rem);
            border:1px solid rgba(25,100,123,.15);
            border-radius:30px;
            background:rgba(255,253,248,.9);
            box-shadow:0 28px 75px rgba(27,54,72,.16),inset 0 0 0 1px rgba(255,255,255,.75);
            backdrop-filter:blur(16px) saturate(120%);
        }
        .mapping-workbench-intro { position:relative; margin:-.3rem 0 2rem; padding:1.5rem 1.65rem 1.45rem 5.2rem; overflow:hidden; border:1px solid rgba(25,100,123,.14); border-radius:22px; background:linear-gradient(120deg,#e2f2f0 0%,#fffaf0 58%,#f2e9ff 100%); }
        .mapping-workbench-intro::before { content:"✎"; position:absolute; left:1.45rem; top:1.4rem; display:grid; place-items:center; width:52px; height:52px; color:white; border-radius:16px; background:linear-gradient(135deg,#19647b,#13a994); box-shadow:0 12px 25px rgba(25,100,123,.22); font-size:1.35rem; transform:rotate(-5deg); }
        .mapping-workbench-intro::after { content:""; position:absolute; right:-28px; top:-45px; width:155px; height:155px; border:24px solid rgba(109,93,252,.08); border-radius:50%; }
        .mapping-workbench-intro small { display:block; margin-bottom:.32rem; color:#19647b; font-size:.62rem; font-weight:900; letter-spacing:.13em; text-transform:uppercase; }
        .mapping-workbench-intro strong { display:block; color:#071c30; font-size:clamp(1.4rem,2.4vw,2rem); letter-spacing:-.045em; }
        .mapping-workbench-intro span { display:block; max-width:720px; margin-top:.38rem; color:#65747a; font-size:.72rem; line-height:1.6; }
        .block-container:has(.mapping-page-marker) div[data-testid="stTextInput"] input,
        .block-container:has(.mapping-page-marker) div[data-baseweb="select"] > div { border-color:rgba(25,100,123,.18); background:rgba(255,255,255,.86); }
        .block-container:has(.mapping-page-marker) div[data-testid="stTextInput"] input:focus { border-color:#13a994; box-shadow:0 0 0 1px #13a994; }
        .stApp:has(.workspace-page-marker) .creative-backdrop { display:none; }
        .workspace-intro {
            position:relative;
            margin-bottom:1.5rem;
            min-height:250px;
            padding:2.2rem clamp(1.6rem,4vw,3.5rem);
            overflow:hidden;
            border:1px solid rgba(25,100,123,.12);
            border-radius:30px;
            color:#151f24;
            background:linear-gradient(90deg,rgba(255,253,248,.96) 0%,rgba(255,253,248,.9) 47%,rgba(255,253,248,.18) 72%,transparent 100%);
            box-shadow:0 24px 65px rgba(7,28,48,.12);
        }
        .workspace-intro::before,.workspace-intro::after { display:none; }
        .workspace-intro-kicker { display:flex; align-items:center; gap:.45rem; margin-bottom:.55rem; color:#19647b; font-size:.66rem; font-weight:850; letter-spacing:.13em; text-transform:uppercase; }
        .workspace-intro-kicker i { width:7px; height:7px; border-radius:50%; background:#13a994; box-shadow:0 0 0 5px rgba(19,169,148,.12); }
        .workspace-intro h1 { position:relative; z-index:1; max-width:760px; margin:0 0 .55rem; color:#071c30; font-size:clamp(2.2rem,4vw,4rem); line-height:.96; letter-spacing:-.055em; }
        .workspace-intro p { position:relative; z-index:1; max-width:690px; margin:0; color:#5f6d70 !important; font-size:.9rem; line-height:1.65; }
        .workspace-flow { position:relative; z-index:2; display:flex; flex-wrap:wrap; gap:.55rem; margin-top:1.35rem; }
        .workspace-flow span { display:flex; align-items:center; gap:.4rem; padding:.5rem .68rem; color:#405055; border:1px solid rgba(25,100,123,.12); border-radius:999px; background:rgba(255,255,255,.72); font-size:.62rem; font-weight:800; }
        .workspace-flow b { display:grid; place-items:center; width:19px; height:19px; color:white; border-radius:50%; background:#19647b; font-size:.56rem; }
        @keyframes workspace-ready { to { transform:translateY(-50%) scale(1.07) rotate(4deg); } }
        .st-key-feature_stage,.st-key-upload_stage { width:min(720px,52%); padding:clamp(1.25rem,3vw,2rem); border:1px solid rgba(25,100,123,.14); border-radius:26px; background:rgba(255,253,248,.94); box-shadow:0 24px 65px rgba(21,31,36,.14); backdrop-filter:blur(10px); }
        .st-key-feature_stage { width:min(1120px,86%); min-height:480px; margin:-1rem auto 0; border:0; background:transparent; box-shadow:none; backdrop-filter:none; }
        .st-key-upload_stage { position:relative; width:min(720px,54%); min-height:520px; margin:4rem auto 0; overflow:visible; border:1px solid rgba(92,77,55,.24); border-radius:12px 28px 15px 24px; background-color:#fffaf0; background-image:repeating-linear-gradient(0deg,transparent 0 27px,rgba(65,130,145,.075) 27px 28px),linear-gradient(145deg,rgba(255,255,255,.72),rgba(239,226,201,.5)); box-shadow:9px 11px 0 rgba(25,100,123,.12),-6px 20px 0 rgba(239,109,90,.08),0 30px 70px rgba(21,31,36,.16); backdrop-filter:none; transform:rotate(-.18deg); }
        .st-key-upload_stage::before { content:""; position:absolute; z-index:5; left:50%; top:-13px; width:112px; height:28px; background:rgba(181,207,197,.7); box-shadow:0 3px 7px rgba(21,31,36,.1); transform:translateX(-50%) rotate(-2deg); }
        .st-key-upload_stage::after { content:""; position:absolute; right:18px; bottom:15px; width:54px; height:18px; opacity:.42; background:repeating-linear-gradient(90deg,#ef6d5a 0 4px,transparent 4px 8px); transform:rotate(-4deg); }
        .upload-section-head { display:flex; align-items:center; justify-content:space-between; gap:1rem; margin-bottom:.9rem; }
        .upload-section-head div { display:flex; align-items:center; gap:.75rem; }
        .upload-section-head i { display:grid; place-items:center; width:42px; height:42px; color:white; border-radius:13px; background:linear-gradient(135deg,#19647b,#13a994); box-shadow:0 10px 22px rgba(25,100,123,.22); font-size:1rem; font-style:normal; }
        .upload-section-head strong { display:block; color:#151f24; font-size:1.15rem; }.upload-section-head small { display:block; margin-top:.12rem; color:#7a858b; font-size:.66rem; }
        .st-key-feature_stage .upload-section-head { position:relative; justify-content:center; width:min(690px,92%); margin:0 auto 1.55rem; padding:1.25rem 5.3rem 1.35rem 2rem; background:linear-gradient(145deg,#fffdf7,#efe4cf); clip-path:polygon(0 8%,6% 3%,13% 7%,21% 2%,30% 6%,40% 1%,51% 6%,61% 2%,72% 7%,82% 2%,91% 6%,100% 1%,98% 94%,89% 98%,79% 93%,69% 99%,58% 94%,47% 99%,36% 94%,25% 98%,14% 93%,3% 98%); filter:drop-shadow(0 14px 16px rgba(21,31,36,.15)); text-align:center; }
        .st-key-feature_stage .upload-section-head::before { content:""; position:absolute; left:12%; right:12%; bottom:24%; height:2px; background:repeating-linear-gradient(90deg,rgba(25,100,123,.2) 0 8px,transparent 8px 14px); }
        .st-key-feature_stage .upload-section-head::after { content:""; position:absolute; right:1.15rem; bottom:1.4rem; width:84px; height:13px; border-radius:3px 9px 9px 3px; background:linear-gradient(90deg,#253346 0 8%,#f2c45d 8% 72%,#ef6d5a 72% 88%,#f4d4c7 88%); box-shadow:0 5px 10px rgba(21,31,36,.16); transform:rotate(-13deg); transform-origin:right center; animation:feature-pencil-write 2.8s ease-in-out infinite alternate; }
        @keyframes feature-pencil-write { 0% { translate:0 0; rotate:-2deg; } 55% { translate:-28px 4px; rotate:2deg; } 100% { translate:-8px -3px; rotate:-1deg; } }
        .st-key-feature_stage .upload-section-head > div { flex-direction:column; gap:.55rem; }
        .st-key-feature_stage .upload-section-head i { width:48px; height:48px; margin:auto; border-radius:50%; }
        .st-key-feature_stage .upload-section-head strong { font-size:clamp(1.55rem,2.5vw,2.25rem); letter-spacing:-.045em; }
        .st-key-feature_stage .upload-section-head small { margin-top:.35rem; font-size:.72rem; }
        .upload-format-pills { display:flex; gap:.35rem; }.upload-format-pills span { padding:.32rem .45rem; color:#19647b; border-radius:7px; background:#e2f0f2; font-size:.52rem; font-weight:900; }
        .st-key-review_feature_choice > div[role="radiogroup"] { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:.8rem; padding:0 !important; border:0 !important; background:transparent !important; }
        .st-key-review_feature_choice label { position:relative; align-items:flex-start; min-height:230px; margin:0; padding:1.35rem 1.2rem 1.2rem 3.2rem; overflow:hidden; border:1px solid rgba(21,31,36,.2); border-radius:20px; background:rgba(255,253,248,.9); box-shadow:0 12px 28px rgba(21,31,36,.06); transition:transform .2s ease,border-color .2s ease,box-shadow .2s ease; }
        .st-key-review_feature_choice label:hover { border-color:#13a994; box-shadow:0 16px 30px rgba(25,100,123,.12); transform:translateY(-3px); }
        .st-key-review_feature_choice label:nth-child(2)::after { content:"Coming soon"; position:absolute; right:.7rem; top:.7rem; padding:.32rem .48rem; color:white; border-radius:999px; background:#ef6d5a; opacity:0; font-size:.52rem; font-weight:900; letter-spacing:.06em; text-transform:uppercase; transform:translateY(-5px); transition:opacity .18s ease,transform .18s ease; }
        .st-key-review_feature_choice label:nth-child(2):hover::after { opacity:1; transform:translateY(0); }
        .st-key-review_feature_choice label p { color:#151f24 !important; font-size:.92rem !important; font-weight:850 !important; }
        .st-key-review_feature_choice label small { display:block; max-width:300px; margin-top:.65rem; color:#788186 !important; font-size:.68rem !important; font-weight:550 !important; line-height:1.75 !important; white-space:pre-line; }
        .st-key-review_feature_choice label:first-child::before { content:"SLM"; position:absolute; left:1.05rem; bottom:1rem; padding:.3rem .45rem; color:white; border-radius:7px; background:#19647b; font-size:.48rem; font-weight:900; letter-spacing:.08em; }
        .st-key-review_feature_choice label:nth-child(2)::before { content:"LLM"; position:absolute; left:1.05rem; bottom:1rem; padding:.3rem .45rem; color:white; border-radius:7px; background:#ce0e2d; font-size:.48rem; font-weight:900; letter-spacing:.08em; }
        .review-feature-note { margin:.75rem 0 1rem; padding:.7rem .85rem; color:#607075; border-left:3px solid #13a994; border-radius:0 10px 10px 0; background:#eef8f6; font-size:.65rem; line-height:1.55; }
        .tts-coming-state { display:grid; place-items:center; min-height:190px; margin-top:.75rem; padding:1.2rem; color:#425157; border:1px dashed rgba(25,100,123,.25); border-radius:18px; background:linear-gradient(135deg,#eef8f6,#fff8ed); text-align:center; }.tts-coming-state b { display:block; margin-bottom:.35rem; color:#071c30; font-size:1.2rem; }.tts-coming-state span { max-width:420px; font-size:.72rem; line-height:1.6; }
        .empty-review-state { display:flex; align-items:center; justify-content:flex-start; gap:.9rem; width:100%; margin:1rem 0 0; padding:1rem 1.25rem; color:#526267; border:1px solid rgba(25,100,123,.16); border-radius:18px; background:#eef8f6; box-shadow:inset 0 0 0 1px rgba(255,255,255,.7); text-align:left; }
        .empty-review-state i { display:grid; flex:0 0 auto; place-items:center; width:48px; height:48px; color:white; border-radius:15px; background:linear-gradient(135deg,#19647b,#13a994); box-shadow:0 9px 22px rgba(25,100,123,.2); font-size:1.15rem; font-style:normal; animation:empty-state-float 2s ease-in-out infinite alternate; }
        .empty-review-state strong,.empty-review-state span { display:block; }.empty-review-state strong { color:#071c30; font-size:.82rem; }.empty-review-state span { margin-top:.18rem; font-size:.65rem; line-height:1.5; }
        @keyframes empty-state-float { to { transform:translateY(-4px); } }
        .review-product-grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:1rem; }
        .review-product-card { position:relative; display:flex; min-height:410px; padding:1.65rem; overflow:hidden; color:#151f24 !important; border:1px solid rgba(21,31,36,.38); border-radius:8px 26px 12px 22px; background:linear-gradient(145deg,rgba(255,253,248,.98),rgba(244,235,217,.96)); box-shadow:7px 10px 0 rgba(25,100,123,.12),0 24px 55px rgba(21,31,36,.14); text-decoration:none !important; transform:rotate(-.35deg); transition:transform .24s ease,box-shadow .24s ease,border-color .24s ease; }
        .review-product-card:nth-child(2) { border-radius:24px 9px 22px 12px; box-shadow:-7px 10px 0 rgba(239,109,90,.12),0 24px 55px rgba(21,31,36,.14); transform:rotate(.35deg); }
        .review-product-card::before { content:""; position:absolute; left:34%; top:-7px; width:88px; height:22px; background:rgba(117,177,190,.48); box-shadow:0 2px 4px rgba(21,31,36,.08); transform:rotate(-2deg); }
        .review-product-card:nth-child(2)::before { left:55%; background:rgba(239,109,90,.32); transform:rotate(3deg); }
        .review-product-card:hover { color:#151f24 !important; border-color:#19647b; box-shadow:7px 15px 0 rgba(25,100,123,.16),0 30px 60px rgba(21,31,36,.18); transform:translateY(-7px) rotate(0); }
        .review-product-card-inner { display:flex; flex:1; flex-direction:column; }
        .review-product-icon { display:grid; place-items:center; width:43px; height:43px; margin-bottom:1.5rem; color:#071c30; border:1px solid rgba(21,31,36,.16); border-radius:13px; background:#eef8f6; font-size:1.15rem; }
        .review-product-card h3 { margin:0 0 .7rem; color:#151f24; font-size:1.35rem; letter-spacing:-.035em; }
        .review-product-card p { min-height:76px; margin:0 0 .9rem; color:#7c818c !important; font-size:.74rem; line-height:1.65; }
        .review-product-card ul { margin:.2rem 0 1.3rem; padding-left:1rem; color:#7c818c; font-size:.68rem; line-height:1.9; }
        .review-product-action { display:flex; align-items:center; justify-content:center; min-height:48px; margin-top:auto; color:white; border-radius:999px; background:#151f24; font-size:.76rem; font-weight:800; transition:background .2s ease; }
        .review-product-card:not(.coming-soon):hover .review-product-action { background:#19647b; }
        .review-product-card.coming-soon { cursor:default; }
        .review-product-card.coming-soon::after { content:"Coming soon"; position:absolute; right:1rem; top:1rem; padding:.36rem .55rem; color:white; border-radius:999px; background:#ef6d5a; opacity:0; font-size:.52rem; font-weight:900; letter-spacing:.06em; text-transform:uppercase; transform:translateY(-5px); transition:opacity .18s ease,transform .18s ease; }
        .review-product-card.coming-soon:hover::after { opacity:1; transform:translateY(0); }
        .review-product-card.coming-soon .review-product-action { color:#777; background:#e9e5dc; }
        .block-container:has(.workspace-page-marker) h2 { margin-top:1.4rem; color:#25293f; font-size:1.25rem; letter-spacing:-.02em; }
        .block-container:has(.workspace-page-marker) h2::after { content:""; display:block; width:34px; height:3px; margin-top:.45rem; border-radius:99px; background:linear-gradient(90deg,#6d5dfc,#13b8a6); }
        .block-container:has(.workspace-page-marker) div[data-testid="stFileUploaderDropzone"] { min-height:150px; border:1.5px dashed rgba(25,100,123,.34); border-radius:20px; background:linear-gradient(135deg,rgba(226,240,242,.62),rgba(255,255,255,.92)); box-shadow:inset 0 0 0 1px rgba(255,255,255,.8),0 9px 25px rgba(43,46,84,.05); transition:transform .2s ease,border-color .2s ease,box-shadow .2s ease; }
        .block-container:has(.workspace-page-marker) div[data-testid="stFileUploaderDropzone"]:hover { border-color:#13a994; box-shadow:0 16px 34px rgba(25,100,123,.12); transform:translateY(-2px); }
        .block-container:has(.workspace-page-marker) div[data-testid="stMetric"] { padding:1rem 1.1rem; border:1px solid rgba(109,93,252,.1); border-radius:15px; background:white; box-shadow:0 8px 22px rgba(43,46,84,.06); }
        .block-container:has(.workspace-page-marker) div[data-testid="stDataFrame"] { overflow:hidden; border:1px solid rgba(109,93,252,.1); border-radius:15px; box-shadow:0 8px 22px rgba(43,46,84,.05); }
        .block-container:has(.workspace-page-marker) div[data-testid="stRadio"] > div { padding:.35rem; border:1px solid rgba(109,93,252,.09); border-radius:12px; background:rgba(255,255,255,.7); }

        .stApp, .stApp p, .stApp label {
            color: var(--ink);
        }
        .stApp label { font-weight:650; }

        .stButton > button,
        .stDownloadButton > button,
        .stLinkButton > a {
            min-height:2.65rem;
            border-radius:11px !important;
            font-weight:750 !important;
            transition:transform .18s ease, box-shadow .18s ease, border-color .18s ease !important;
        }
        .stButton > button:hover,
        .stDownloadButton > button:hover,
        .stLinkButton > a:hover { transform:translateY(-2px); box-shadow:0 9px 20px rgba(52,44,120,.12); }
        .stButton > button[kind="primary"] { border:0 !important; background:linear-gradient(135deg,#6d5dfc,#5145cd) !important; box-shadow:0 9px 20px rgba(81,69,205,.22); }
        .st-key-start_evaluation_button .stButton > button[kind="primary"] { color:white !important; border:1px solid #ce0e2d !important; background:linear-gradient(135deg,#e51b3e 0%,#ce0e2d 60%,#a90823 100%) !important; box-shadow:0 12px 26px rgba(206,14,45,.28) !important; }
        .st-key-start_evaluation_button .stButton > button[kind="primary"]:hover { border-color:#a90823 !important; background:linear-gradient(135deg,#d61133,#a90823) !important; box-shadow:0 16px 32px rgba(169,8,35,.34) !important; }

        div[data-baseweb="input"] > div,
        div[data-baseweb="select"] > div,
        div[data-baseweb="textarea"] > div {
            border-color:rgba(109,93,252,.14) !important;
            border-radius:11px !important;
            background:rgba(255,255,255,.92) !important;
            transition:border-color .18s ease, box-shadow .18s ease !important;
        }
        div[data-baseweb="input"] > div:focus-within,
        div[data-baseweb="select"] > div:focus-within,
        div[data-baseweb="textarea"] > div:focus-within { border-color:#6d5dfc !important; box-shadow:0 0 0 3px rgba(109,93,252,.1) !important; }
        div[data-testid="stAlert"] { border:1px solid rgba(109,93,252,.1); border-radius:13px; box-shadow:var(--shadow-sm); }

        .review-hero, .review-hero p, .review-hero span,
        .review-hero .hero-eyebrow {
            color: white;
        }

        .review-hero {
            position: relative;
            overflow: hidden;
            padding: 1.7rem 2rem;
            margin-bottom: 1.4rem;
            border-radius: 24px;
            color: white;
            background: linear-gradient(120deg, #342c78 0%, #6d5dfc 55%, #13b8a6 125%);
            box-shadow: 0 18px 45px rgba(52, 44, 120, 0.24);
            isolation: isolate;
            animation: hero-in 0.55s ease-out both;
        }

        @keyframes hero-in {
            from { opacity: 0; transform: translateY(12px); }
            to { opacity: 1; transform: translateY(0); }
        }

        .review-hero::after {
            content: "";
            position: absolute;
            width: 220px;
            height: 220px;
            right: -55px;
            top: -95px;
            border-radius: 50%;
            background: rgba(255, 255, 255, 0.13);
            z-index: -1;
            animation: float-orb 7s ease-in-out infinite;
        }

        .review-hero::before {
            content: "";
            position: absolute;
            inset: 0;
            z-index: -2;
            opacity: 0.2;
            background-image:
                linear-gradient(rgba(255,255,255,.18) 1px, transparent 1px),
                linear-gradient(90deg, rgba(255,255,255,.18) 1px, transparent 1px);
            background-size: 38px 38px;
            mask-image: linear-gradient(90deg, transparent, black 45%, black);
        }

        @keyframes float-orb {
            0%, 100% { transform: translate3d(0, 0, 0); }
            50% { transform: translate3d(-18px, 20px, 0); }
        }

        .landing-hero {
            position: relative;
            display: grid;
            grid-template-columns: minmax(360px, .9fr) minmax(520px, 1.1fr);
            align-items: center;
            gap: clamp(2rem, 5vw, 5rem);
            min-height: calc(100vh - 7rem);
            padding: clamp(2.2rem, 5vw, 5.2rem);
            margin-bottom: 1.5rem;
            overflow: hidden;
            border: 1px solid rgba(109,93,252,.14);
            border-radius: 38px;
            background: linear-gradient(145deg, #fbfaff 0%, #f2efff 52%, #eafaf7 100%);
            box-shadow: 0 28px 75px rgba(52,44,120,.16);
        }
        .landing-hero::before {
            content: "";
            position: absolute;
            width: 390px;
            height: 390px;
            left: -210px;
            bottom: -250px;
            border: 58px solid rgba(109,93,252,.09);
            border-radius: 50%;
        }
        .landing-lamps { position:absolute; z-index:1; right:7%; top:0; display:flex; align-items:flex-start; gap:46px; }
        .landing-lamps i { position:relative; display:block; width:2px; height:64px; background:rgba(81,69,205,.38); }
        .landing-lamps i:nth-child(2) { height:95px; }
        .landing-lamps i:nth-child(3) { height:48px; }
        .landing-lamps i::after { content:""; position:absolute; left:-17px; bottom:-15px; width:36px; height:18px; border-radius:18px 18px 4px 4px; background:#6d5dfc; box-shadow:0 7px 16px rgba(81,69,205,.13); }
        .landing-foliage { position:absolute; z-index:1; left:-12px; bottom:-10px; width:155px; height:175px; opacity:.65; }
        .landing-foliage i { position:absolute; left:70px; bottom:0; width:4px; height:155px; border-radius:99px; background:#6555d9; transform:rotate(-28deg); transform-origin:bottom; }
        .landing-foliage i::before, .landing-foliage i::after { content:""; position:absolute; width:42px; height:21px; border-radius:100% 0 100% 0; background:#8b7df5; }
        .landing-foliage i::before { left:-38px; top:42px; transform:rotate(25deg); }
        .landing-foliage i::after { left:2px; top:78px; transform:rotate(-20deg) scaleX(-1); }
        .landing-foliage i:nth-child(2) { height:120px; transform:rotate(4deg); }
        .landing-foliage i:nth-child(3) { height:105px; transform:rotate(35deg); }
        .landing-copy { position: relative; z-index: 2; }
        .landing-page-nav { position:absolute; z-index:5; left:clamp(2.2rem,5vw,5.2rem); right:clamp(2.2rem,5vw,5.2rem); top:1.35rem; display:flex; align-items:center; justify-content:space-between; gap:1rem; }
        .landing-nav-brand { display:flex; align-items:center; gap:.5rem; color:#302d57; font-size:.72rem; font-weight:900; letter-spacing:.08em; text-transform:uppercase; }
        .landing-nav-brand i { width:9px; height:9px; border-radius:50%; background:linear-gradient(135deg,#6d5dfc,#13b8a6); box-shadow:0 0 0 5px rgba(109,93,252,.09); }
        .landing-nav-links { display:flex; align-items:center; gap:.35rem; padding:.35rem; border:1px solid rgba(109,93,252,.11); border-radius:12px; background:rgba(255,255,255,.68); box-shadow:0 8px 22px rgba(45,48,82,.06); }
        .landing-nav-links a { padding:.55rem .72rem; color:#555b70 !important; border-radius:8px; font-size:.71rem; font-weight:800; text-decoration:none !important; transition:background .18s ease,color .18s ease; }
        .landing-nav-links a:hover, .landing-nav-links a.active { color:#5145cd !important; background:#eeebff; }
        .landing-kicker {
            display: inline-flex;
            align-items: center;
            gap: .55rem;
            color: #5b4ae6;
            font-size: .74rem;
            font-weight: 850;
            letter-spacing: .14em;
            text-transform: uppercase;
        }
        .landing-kicker::before {
            content: "";
            width: 26px;
            height: 3px;
            border-radius: 999px;
            background: linear-gradient(90deg, #6d5dfc, #13b8a6);
        }
        .landing-title {
            max-width: 620px;
            margin: 1.05rem 0 1.15rem;
            color: #15172c;
            font-size: clamp(2.7rem, 5vw, 5.2rem);
            line-height: .96;
            letter-spacing: -.065em;
        }
        .landing-title span {
            color: transparent;
            background: linear-gradient(105deg, #6856f5, #13a994);
            background-clip: text;
            -webkit-background-clip: text;
        }
        .landing-subtitle {
            max-width: 540px;
            color: #626a7c !important;
            font-size: 1.03rem;
            line-height: 1.75;
        }
        .landing-actions { display: flex; align-items: center; gap: .8rem; margin-top: 1.7rem; }
        .landing-primary,
        .landing-secondary {
            display: inline-flex;
            align-items: center;
            gap: .55rem;
            padding: .84rem 1.08rem;
            border-radius: 12px;
            text-decoration: none !important;
            font-size: .86rem;
            font-weight: 800;
            transition: transform .2s ease, box-shadow .2s ease;
        }
        .landing-primary {
            color: white !important;
            background: linear-gradient(135deg, #6d5dfc, #5145cd);
            box-shadow: 0 10px 22px rgba(81,69,205,.25);
        }
        .landing-secondary { color: #262940 !important; background: white; border: 1px solid #dedcf0; }
        .landing-primary:hover, .landing-secondary:hover { transform: translateY(-2px); }
        .landing-proof { display: flex; gap: 1.3rem; margin-top: 1.8rem; color: #72798a; font-size: .74rem; }
        .landing-proof span::before { content: "✓"; margin-right: .35rem; color: #13a994; font-weight: 900; }

        .product-stage { position: relative; z-index: 2; min-height: 500px; perspective: 1200px; }
        .product-window {
            position: absolute;
            inset: 24px 8px 10px 8px;
            overflow: hidden;
            border: 1px solid rgba(42,35,99,.13);
            border-radius: 26px;
            background: white;
            box-shadow: 0 28px 60px rgba(43,37,91,.2);
            transform: rotateY(-4deg) rotateX(1deg);
            animation: product-float 5s ease-in-out infinite alternate;
        }
        @keyframes product-float { to { transform: rotateY(-1deg) rotateX(0) translateY(-7px); } }
        .product-topbar { display:flex; align-items:center; justify-content:space-between; padding: .85rem 1rem; border-bottom:1px solid #ececf4; }
        .product-logo { color:#28234f; font-size:.72rem; font-weight:900; letter-spacing:.04em; }
        .product-dots { display:flex; gap:5px; }
        .product-dots i { width:7px; height:7px; border-radius:50%; background:#deddea; }
        .product-dots i:first-child { background:#ff7d9c; }
        .product-body { display:grid; grid-template-columns: 110px 1fr; min-height:330px; }
        .product-side { padding:1rem .75rem; color:#8a8fa0; background:#f8f8fc; border-right:1px solid #ededf4; font-size:.6rem; }
        .product-side b { display:block; margin:.75rem 0; padding:.55rem; color:#5b4ae6; border-radius:7px; background:#ebe8ff; }
        .product-main { padding:1rem; }
        .mock-progress { display:flex; align-items:center; justify-content:space-between; color:#717789; font-size:.62rem; }
        .mock-progress i { display:block; width:48%; height:5px; border-radius:99px; background:linear-gradient(90deg,#6d5dfc 68%,#ececf4 68%); }
        .mock-prompt { margin:.9rem 0; padding:.75rem; border-radius:10px; color:#42475a; background:#f6f7fb; font-size:.66rem; line-height:1.5; }
        .mock-responses { display:grid; grid-template-columns:1fr 1fr; gap:.65rem; }
        .mock-response { position:relative; min-height:112px; padding:.7rem; border:1px solid #e5e5ef; border-radius:11px; color:#687083; font-size:.58rem; line-height:1.55; }
        .mock-response.selected { border-color:#6d5dfc; box-shadow:0 0 0 2px rgba(109,93,252,.1); }
        .mock-response strong { display:block; margin-bottom:.45rem; color:#282d40; font-size:.62rem; }
        .mock-check { position:absolute; right:7px; top:7px; display:grid; place-items:center; width:17px; height:17px; color:white; border-radius:50%; background:#6d5dfc; }
        .mock-ratings { display:flex; align-items:center; gap:.45rem; margin-top:.75rem; color:#686f80; font-size:.59rem; }
        .mock-ratings i { width:18px; height:18px; display:grid; place-items:center; border-radius:50%; color:white; background:#6d5dfc; font-style:normal; }
        .floating-tag { position:absolute; z-index:4; padding:.7rem .85rem; border-radius:12px; background:white; box-shadow:0 13px 32px rgba(43,37,91,.18); font-size:.65rem; font-weight:800; }
        .floating-tag.quality { right:-8px; top:4px; color:#169b89; animation: tag-bob 3s ease-in-out infinite alternate; }
        .floating-tag.rows { left:-8px; bottom:16px; color:#6655ea; animation: tag-bob 3.5s -.8s ease-in-out infinite alternate; }
        @keyframes tag-bob { to { transform:translateY(-8px) rotate(1deg); } }

        .mira-story { overflow:hidden; color:#151f24; background:#eecdb9; }
        .mira-masthead { display:flex; align-items:center; justify-content:space-between; padding:1rem clamp(1.2rem,4vw,4rem); border-bottom:1px solid rgba(238,205,185,.2); color:#eecdb9; background:#151f24; }
        .mira-wordmark { font-family:Georgia,serif; font-size:1.35rem; font-weight:900; letter-spacing:.08em; }
        .mira-wordmark small { margin-left:.55rem; color:#eb6cf4; font-family:inherit; font-size:.56rem; font-weight:700; letter-spacing:.11em; text-transform:uppercase; }
        .mira-story-nav { display:flex; align-items:center; gap:1rem; }
        .mira-story-nav a { color:rgba(255,255,255,.72) !important; font-size:.68rem; font-weight:800; text-decoration:none !important; }
        .mira-story-nav a:hover { color:#eb6cf4 !important; }
        .mira-news-header { position:relative; z-index:20; padding:14px clamp(16px,2.4vw,42px); color:#151f24; background:white; font-family:"Avenir Next","Helvetica Neue",Inter,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }
        .news-top { display:flex; align-items:center; justify-content:space-between; gap:clamp(.8rem,2vw,2rem); min-height:76px; }
        .news-brand { display:inline-flex; align-items:center; gap:.72rem; flex:0 0 auto; padding:.78rem 1.18rem; color:#151f24 !important; border:1px solid transparent; border-radius:999px; background:#f7f7f7; box-shadow:0 0 0 rgba(21,31,36,0); font-size:1.45rem; font-weight:850; letter-spacing:-.035em; text-decoration:none !important; cursor:pointer; transition:transform .25s ease,box-shadow .25s ease,border-color .25s ease,background .25s ease; }
        .news-brand > span:last-child { transition:transform .25s ease,letter-spacing .25s ease; }
        .news-brand:hover { border-color:rgba(25,100,123,.2); background:white; box-shadow:0 10px 25px rgba(21,31,36,.11); transform:translateY(-3px); }
        .route-back-link { display:grid; place-items:center; flex:0 0 42px; width:42px; height:42px; color:#151f24 !important; border:1px solid rgba(21,31,36,.12); border-radius:50%; background:#f7f7f7; font-size:1.15rem; font-weight:900; text-decoration:none !important; transition:transform .2s ease,background .2s ease; }
        .route-back-link:hover { background:white; transform:translateX(-2px); }
        .news-brand:hover > span:last-child { letter-spacing:.015em; transform:translateX(2px); }
        .news-brand:focus-visible { outline:3px solid rgba(25,100,123,.28); outline-offset:3px; }
        .news-brand-mark { position:relative; width:36px; height:17px; }
        .news-brand-mark i { position:absolute; top:3px; width:14px; height:14px; border-radius:50%; background:#151f24; }
        .news-brand-mark i:nth-child(1){left:0}.news-brand-mark i:nth-child(2){left:11px;top:0}.news-brand-mark i:nth-child(3){left:22px}
        .news-brand-mark::after { content:""; position:absolute; left:3px; right:3px; bottom:0; height:7px; border-radius:999px; background:#151f24; }
        .news-brand:hover .news-brand-mark i:nth-child(1) { animation:mira-dot-left .65s ease-in-out; }
        .news-brand:hover .news-brand-mark i:nth-child(2) { animation:mira-dot-center .65s .06s ease-in-out; }
        .news-brand:hover .news-brand-mark i:nth-child(3) { animation:mira-dot-right .65s .12s ease-in-out; }
        .news-brand:active { transform:translateY(0) scale(.97); }
        @keyframes mira-dot-left { 50% { transform:translateY(-6px) rotate(-8deg); background:#19647b; } }
        @keyframes mira-dot-center { 50% { transform:translateY(-9px) scale(1.08); background:#ce0e2d; } }
        @keyframes mira-dot-right { 50% { transform:translateY(-6px) rotate(8deg); background:#eb6cf4; } }
        .news-nav { display:flex; align-items:center; gap:.3rem; padding:.34rem; overflow:auto; border-radius:999px; background:#f7f7f7; white-space:nowrap; scrollbar-width:none; }
        .news-nav::-webkit-scrollbar { display:none; }
        .news-nav a { display:inline-flex; align-items:center; gap:.52rem; padding:.82rem 1.1rem; color:#151f24 !important; border:1px solid transparent; border-radius:999px; font-size:.92rem; font-weight:720; letter-spacing:-.012em; text-decoration:none !important; transition:background .2s ease,border-color .2s ease,transform .2s ease; }
        .news-nav a:hover { background:white; transform:translateY(-1px); }
        .news-nav a.active { border-color:#151f24; background:white; box-shadow:0 4px 14px rgba(21,31,36,.07); }
        .nav-icon { display:grid; place-items:center; width:20px; height:20px; font-size:.88rem; font-style:normal; }
        .news-actions { display:flex; align-items:center; gap:.38rem; flex:0 0 auto; }
        .news-actions a { display:inline-flex; align-items:center; gap:.5rem; padding:.84rem 1.12rem; color:#151f24 !important; border:1px solid transparent; border-radius:999px; background:#f7f7f7; font-size:.88rem; font-weight:760; letter-spacing:-.01em; text-decoration:none !important; transition:transform .2s ease,box-shadow .2s ease,background .2s ease; }
        .news-actions a:hover { transform:translateY(-2px); box-shadow:0 8px 18px rgba(21,31,36,.09); }
        .news-actions a.demo { background:#f7f7f7; }
        .news-actions a.primary { background:#f7f7f7; }
        .news-actions a.primary i { display:grid; place-items:center; width:24px; height:24px; border:1px solid #151f24; border-radius:50%; font-style:normal; transition:transform .2s ease; }
        .news-actions a.primary:hover i { transform:translateX(3px); }
        .nav-account-menu { position:relative; display:flex; align-items:center; }
        .nav-user-avatar { display:grid !important; place-items:center; width:46px; height:46px; padding:0 !important; color:white !important; border-radius:50% !important; background:linear-gradient(135deg,#19647b,#13a994) !important; box-shadow:0 9px 22px rgba(25,100,123,.22); font-size:.95rem !important; font-weight:900 !important; }
        .nav-account-dropdown { position:absolute; z-index:80; right:0; top:calc(100% - 2px); width:235px; padding:.85rem .65rem .65rem; border:1px solid rgba(21,31,36,.1); border-radius:16px; background:rgba(255,255,255,.98); box-shadow:0 20px 48px rgba(21,31,36,.18); opacity:0; pointer-events:none; transform:translateY(-4px); transition:opacity .18s ease,transform .18s ease; }
        .nav-account-dropdown::before { content:""; position:absolute; left:0; right:0; top:-12px; height:14px; }
        .nav-account-menu:hover .nav-account-dropdown,.nav-account-menu:focus-within .nav-account-dropdown { opacity:1; pointer-events:auto; transform:translateY(0); }
        .nav-account-identity { padding:.55rem .65rem .7rem; border-bottom:1px solid rgba(21,31,36,.08); }.nav-account-identity strong,.nav-account-identity span { display:block; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }.nav-account-identity strong { color:#151f24; font-size:.72rem; }.nav-account-identity span { margin-top:.18rem; color:#7a858b; font-size:.6rem; }
        .nav-account-dropdown a { display:flex !important; width:100%; margin-top:.35rem; padding:.62rem .68rem !important; border-radius:9px !important; background:transparent !important; font-size:.67rem !important; box-shadow:none !important; }.nav-account-dropdown a:hover { color:#19647b !important; background:#eef8f6 !important; transform:none !important; }.nav-account-dropdown a.sign-out { color:#c54e42 !important; }
        .inner-site-header { position:relative; z-index:20; margin:0 0 2rem; padding:.55rem .75rem; border:1px solid rgba(21,31,36,.08); border-radius:28px; background:rgba(255,255,255,.96); box-shadow:0 15px 40px rgba(21,31,36,.09); backdrop-filter:blur(14px); }
        .inner-site-header .news-top { min-height:60px; }
        .inner-site-header .news-brand { font-size:1.18rem; padding:.65rem .85rem; }
        .inner-site-header .news-nav a,.inner-site-header .news-actions a { font-size:.75rem; padding:.68rem .82rem; }
        .inner-site-header .news-actions a.active { color:white !important; background:#151f24; }
        .stApp:has(.auth-page-marker) .inner-site-header { border-color:rgba(255,255,255,.1); box-shadow:0 18px 50px rgba(0,0,0,.22); }
        .inner-site-header { position:fixed !important; z-index:999; left:3vw; right:3vw; top:2.55rem; width:auto; height:72px; min-height:72px; margin:0 !important; padding:0 !important; overflow:visible; border:0; border-radius:0; background:transparent; box-shadow:none; }
        .inner-site-header::before { content:""; position:absolute; z-index:28; left:0; right:0; top:-8px; height:80px; cursor:s-resize; }
        .inner-site-header > .news-top { position:absolute; z-index:30; left:0; right:0; top:0; display:flex; flex-wrap:nowrap; min-height:64px; padding:.48rem .8rem; border:1px solid rgba(21,31,36,.08); border-radius:23px; background:rgba(255,255,255,.97); box-shadow:0 15px 38px rgba(21,31,36,.13); opacity:0; pointer-events:none; transform:translateY(calc(-100% - 24px)); transition:transform .28s cubic-bezier(.2,.8,.2,1),opacity .18s ease; backdrop-filter:blur(16px); }
        .inner-site-header .news-brand { padding:.58rem .78rem; font-size:1.15rem; }
        .inner-site-header .news-nav { gap:.24rem; padding:.26rem; }
        .inner-site-header .news-nav a,.inner-site-header .news-actions a { padding:.62rem .76rem; font-size:.75rem; white-space:nowrap; }
        .inner-site-header:hover > .news-top,.inner-site-header:focus-within > .news-top { opacity:1; pointer-events:auto; transform:translateY(0); }
        .depth-collage-hero { position:relative; min-height:min(900px,72vw); overflow:hidden; background:#e2f0f2 url('/app/static/mira-depth-hero.png') center top/cover no-repeat; }
        .depth-hero-copy { position:absolute; z-index:3; left:8%; top:8%; width:min(560px,42%); animation:editorial-rise .7s ease-out both; }
        .depth-hero-copy h1 { margin:0; color:#090b0c; font-family:"Avenir Next","Helvetica Neue",sans-serif; font-size:clamp(2.4rem,4.8vw,5.5rem); font-weight:900; line-height:.9; letter-spacing:-.055em; text-transform:uppercase; }
        .depth-hero-copy p { max-width:520px; margin:2rem 0 0; color:#151f24 !important; font-family:"Iowan Old Style","Palatino Linotype",Palatino,serif; font-size:clamp(.9rem,1.35vw,1.3rem); line-height:1.4; }
        .depth-scroll { position:absolute; z-index:4; left:17%; top:67%; display:flex; align-items:center; gap:.7rem; padding:.48rem .7rem; color:#151f24; background:#e2f0f2; box-shadow:0 5px 14px rgba(21,31,36,.12); font-family:monospace; font-size:.67rem; transform:rotate(-1deg); animation:label-float 2.6s ease-in-out infinite alternate; }
        .depth-scroll::before { content:'↓'; position:absolute; left:-28px; color:#e2f0f2; font-size:1.5rem; }
        .depth-tag { position:absolute; z-index:4; padding:.42rem .65rem; color:#151f24; background:#e2f0f2; box-shadow:0 6px 15px rgba(21,31,36,.18); font-family:monospace; font-size:.64rem; transform:rotate(-4deg); animation:label-float 3s ease-in-out infinite alternate; }
        .depth-tag.context { right:24%; top:18%; }.depth-tag.tone { right:7%; top:35%; animation-delay:-1s; }.depth-tag.safety { right:17%; bottom:18%; animation-delay:-1.8s; }.depth-tag.relevance { left:44%; bottom:28%; animation-delay:-2.3s; }
        @keyframes label-float { to { translate:0 -9px; rotate:2deg; } }
        @keyframes collage-pan { to { background-position:center 12px; } }
        .depth-collage-hero { animation:collage-pan 7s ease-in-out infinite alternate; }
        .evaluation-particles { position:absolute; z-index:2; inset:0; overflow:hidden; pointer-events:none; }
        .particle-swarm { position:absolute; width:320px; height:190px; opacity:.42; background-image:radial-gradient(circle,#ce0e2d 0 2px,transparent 2.4px); background-size:14px 14px; mask-image:radial-gradient(ellipse,black,transparent 68%); animation:particle-drift 9s ease-in-out infinite alternate; }
        .particle-swarm.one { left:38%; top:5%; transform:rotate(-8deg); }
        .particle-swarm.two { right:-4%; bottom:8%; background-image:radial-gradient(circle,#e2f0f2 0 1.5px,transparent 2px); background-size:13px 13px; animation-delay:-3s; }
        @keyframes particle-drift { to { translate:35px 18px; rotate:9deg; scale:1.08; } }
        .mira-quick-pitch { display:grid; grid-template-columns:1.1fr .9fr; gap:clamp(2rem,7vw,8rem); align-items:center; padding:clamp(3rem,7vw,7rem) clamp(1.3rem,7vw,8rem); color:#151f24; background:white; }
        .quick-pitch-title { margin:0; font-size:clamp(2.3rem,4.7vw,5.2rem); line-height:.98; letter-spacing:-.055em; }
        .quick-pitch-title span { color:#19647b; }
        .quick-pitch-copy { padding-left:1.4rem; border-left:2px solid #151f24; }
        .quick-pitch-copy p { margin:0 0 1.2rem; color:#4e565a !important; font-size:clamp(.92rem,1.2vw,1.08rem); line-height:1.65; }
        .pitch-actions { display:flex; flex-wrap:wrap; gap:.65rem; }
        .pitch-link { display:inline-flex; align-items:center; gap:.45rem; padding:.72rem .95rem; color:#151f24 !important; border:1px solid #d6dadd; border-radius:999px; background:#f7f7f7; font-size:.72rem; font-weight:850; text-decoration:none !important; }
        .pitch-link.primary { border-color:#00e14f; background:white; box-shadow:0 0 0 3px rgba(0,225,79,.08); }
        .pitch-link i { display:grid; place-items:center; width:22px; height:22px; border:1px solid #151f24; border-radius:50%; font-style:normal; }
        .mira-bento { padding:clamp(4rem,8vw,8rem) clamp(1.3rem,7vw,8rem); background:#f4f4f2; }
        .bento-head { display:flex; align-items:end; justify-content:space-between; gap:2rem; margin-bottom:2rem; }
        .bento-head h2 { max-width:780px; margin:0; color:#151f24; font-size:clamp(2.5rem,5vw,5rem); line-height:.98; letter-spacing:-.055em; }
        .bento-head p { max-width:390px; color:#656b6e !important; font-size:.8rem; line-height:1.65; }
        .bento-grid { display:grid; grid-template-columns:1.15fr .85fr; grid-template-rows:auto auto; gap:1rem; }
        .bento-card { position:relative; min-height:285px; padding:1.5rem; overflow:hidden; border:1px solid #dedfdf; border-radius:22px; background:white; box-shadow:0 12px 30px rgba(21,31,36,.06); transition:transform .22s ease,box-shadow .22s ease; }
        .bento-card:hover { transform:translateY(-5px); box-shadow:0 22px 45px rgba(21,31,36,.12); }
        .bento-card.wide { grid-row:span 2; min-height:580px; background:#151f24; color:white; }
        .bento-card h3 { margin:0 0 .4rem; color:#151f24; font-size:1.05rem; }
        .bento-card.wide h3 { color:white; }
        .bento-card > p { max-width:390px; color:#747a7c !important; font-size:.72rem; line-height:1.6; }
        .bento-card.wide > p { color:rgba(255,255,255,.6) !important; }
        .bento-response-stack { position:absolute; left:7%; right:7%; bottom:6%; display:grid; gap:.7rem; }
        .bento-response { padding:1rem; border:1px solid rgba(255,255,255,.12); border-radius:13px; color:rgba(255,255,255,.65); background:rgba(255,255,255,.06); font-size:.68rem; animation:bento-slide 5s ease-in-out infinite alternate; }
        .bento-response:nth-child(2) { margin-left:7%; border-color:rgba(0,225,79,.45); animation-delay:-1.5s; }.bento-response:nth-child(3) { margin-left:14%; animation-delay:-3s; }
        .bento-response b { display:block; margin-bottom:.3rem; color:white; }
        @keyframes bento-slide { to { transform:translateX(10px); } }
        .rating-orbit { display:flex; align-items:center; justify-content:center; gap:.55rem; min-height:150px; }
        .rating-orbit i { display:grid; place-items:center; width:40px; height:40px; border:1px solid #cfd4d5; border-radius:50%; font-style:normal; font-weight:850; animation:rating-wave 2.5s ease-in-out infinite alternate; }
        .rating-orbit i:nth-child(4) { color:white; border-color:#19647b; background:#19647b; transform:scale(1.15); }.rating-orbit i:nth-child(2){animation-delay:-.4s}.rating-orbit i:nth-child(3){animation-delay:-.8s}.rating-orbit i:nth-child(4){animation-delay:-1.2s}.rating-orbit i:nth-child(5){animation-delay:-1.6s}
        @keyframes rating-wave { to { translate:0 -8px; } }
        .export-flow { display:flex; align-items:center; justify-content:center; gap:1rem; min-height:140px; }
        .export-flow span { padding:.8rem 1rem; border:1px solid #d8dcdd; border-radius:12px; background:#f8f8f7; font-size:.7rem; font-weight:850; }
        .export-flow i { color:#ce0e2d; font-style:normal; animation:arrow-nudge 1.5s ease-in-out infinite alternate; }
        @keyframes arrow-nudge { to { transform:translateX(7px); } }
        .editorial-hero { position:relative; display:grid; place-items:center; min-height:calc(100vh - 72px); padding:6rem 1.5rem; overflow:hidden; color:white; text-align:center; background:radial-gradient(circle at 50% 45%,rgba(235,108,244,.2),transparent 25%),linear-gradient(145deg,#151f24 0%,#19647b 72%,#88091e 145%); }
        .editorial-hero::before { content:""; position:absolute; width:48vw; height:48vw; left:-22vw; top:-20vw; border-radius:42% 58% 62% 38%; background:rgba(206,14,45,.3); filter:blur(2px); animation:organic-shift 12s ease-in-out infinite alternate; }
        .editorial-hero::after { content:""; position:absolute; width:34vw; height:34vw; right:-16vw; bottom:-15vw; border:4vw solid rgba(235,108,244,.14); border-radius:50%; animation:orbital-drift 14s ease-in-out infinite alternate; }
        .editorial-grid { position:absolute; inset:0; opacity:.11; background-image:linear-gradient(rgba(255,255,255,.22) 1px,transparent 1px),linear-gradient(90deg,rgba(255,255,255,.22) 1px,transparent 1px); background-size:52px 52px; mask-image:linear-gradient(to bottom,black,transparent 85%); }
        .editorial-hero-copy { position:relative; z-index:3; max-width:1050px; animation:editorial-rise .8s ease-out both; }
        .editorial-label { display:inline-flex; align-items:center; gap:.6rem; color:#eb6cf4; font-size:.67rem; font-weight:900; letter-spacing:.18em; text-transform:uppercase; }
        .editorial-label::before,.editorial-label::after { content:""; width:38px; height:1px; background:#eb6cf4; }
        .editorial-hero h1 { margin:1.2rem 0 1.4rem; color:white; font-family:Georgia,"Times New Roman",serif; font-size:clamp(3.5rem,8.4vw,8.8rem); font-weight:500; line-height:.86; letter-spacing:-.065em; }
        .editorial-hero h1 em { color:#eecdb9; font-weight:400; }
        .editorial-deck { max-width:690px; margin:0 auto; color:rgba(255,255,255,.7) !important; font-size:clamp(.95rem,1.4vw,1.18rem); line-height:1.75; }
        .scroll-cue { display:inline-flex; flex-direction:column; align-items:center; gap:.5rem; margin-top:2.2rem; color:rgba(255,255,255,.5); font-size:.58rem; letter-spacing:.13em; text-transform:uppercase; }
        .scroll-cue i { width:1px; height:42px; background:linear-gradient(#eb6cf4,transparent); animation:scroll-pulse 1.7s ease-in-out infinite; }
        @keyframes editorial-rise { from { opacity:0; transform:translateY(24px); } }
        @keyframes scroll-pulse { 50% { transform:scaleY(.55); transform-origin:top; opacity:.35; } }
        @keyframes organic-shift { to { transform:translate(8vw,6vw) rotate(25deg); border-radius:60% 40% 35% 65%; } }
        @keyframes orbital-drift { to { transform:translate(-6vw,-4vw) rotate(24deg) scale(1.12); } }
        .data-depth { position:absolute; inset:0; pointer-events:none; }
        .depth-card { position:absolute; width:210px; padding:.85rem; border:1px solid rgba(238,205,185,.22); border-radius:12px; color:rgba(238,205,185,.72); background:rgba(21,31,36,.38); backdrop-filter:blur(8px); font-size:.58rem; line-height:1.5; text-align:left; animation:depth-drift 5s ease-in-out infinite alternate; }
        .depth-card b { display:block; margin-bottom:.35rem; color:white; font-size:.65rem; }
        .depth-card.one { left:4%; top:22%; transform:rotate(-7deg); }
        .depth-card.two { right:5%; top:18%; transform:rotate(6deg); animation-delay:-1.7s; }
        .depth-card.three { right:11%; bottom:10%; transform:rotate(-3deg); animation-delay:-3.1s; }
        @keyframes depth-drift { to { translate:0 -15px; } }
        .story-section { padding:clamp(4rem,9vw,9rem) clamp(1.3rem,7vw,8rem); }
        .story-intro { position:relative; display:grid; grid-template-columns:.8fr 1.2fr; gap:clamp(2.5rem,7vw,8rem); align-items:center; overflow:hidden; color:#151f24; background:#e2f0f2; }
        .story-intro::before { content:""; position:absolute; left:-10vw; top:-14vw; width:36vw; height:36vw; border:1px solid rgba(25,100,123,.12); border-radius:50%; box-shadow:0 0 0 5vw rgba(255,255,255,.16),0 0 0 10vw rgba(25,100,123,.035); }
        .story-intro-copy { position:relative; z-index:2; }
        .story-index { display:inline-flex; align-items:center; gap:.55rem; color:#19647b; font-size:.66rem; font-weight:900; letter-spacing:.15em; text-transform:uppercase; }
        .story-index::before { content:""; width:8px; height:8px; border-radius:50%; background:#ce0e2d; box-shadow:0 0 0 6px rgba(206,14,45,.08); }
        .story-intro h2,.story-process h2,.story-closing h2 { margin:.9rem 0 1.2rem; color:#151f24; font-family:"Avenir Next","Helvetica Neue",Inter,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; font-size:clamp(2.7rem,5vw,5.6rem); font-weight:780; line-height:.94; letter-spacing:-.06em; }
        .story-intro h2 em { color:#19647b; font-style:normal; }
        .story-copy { max-width:560px; margin:0; color:#48575d !important; font-size:clamp(.9rem,1.2vw,1.05rem); line-height:1.75; }
        .story-proof { display:flex; flex-wrap:wrap; gap:.55rem; margin-top:1.5rem; }
        .story-proof span { padding:.52rem .7rem; border:1px solid rgba(25,100,123,.18); border-radius:999px; color:#31535e; background:rgba(255,255,255,.54); font-size:.65rem; font-weight:800; }
        .response-xray { position:relative; z-index:2; min-height:430px; perspective:1000px; }
        .xray-card { position:absolute; left:50%; top:50%; width:min(470px,84%); min-height:205px; padding:1.4rem; border-radius:22px; box-shadow:0 24px 55px rgba(21,31,36,.14); transform:translate(-50%,-50%); transition:transform .35s ease; }
        .xray-card.back { color:rgba(255,255,255,.55); background:#151f24; transform:translate(-43%,-63%) rotate(4deg); }
        .xray-card.middle { color:white; background:#19647b; transform:translate(-55%,-53%) rotate(-3deg); }
        .xray-card.front { z-index:3; color:#151f24; background:white; transform:translate(-50%,-42%); }
        .response-xray:hover .xray-card.back { transform:translate(-35%,-72%) rotate(7deg); }
        .response-xray:hover .xray-card.middle { transform:translate(-63%,-55%) rotate(-6deg); }
        .response-xray:hover .xray-card.front { transform:translate(-48%,-38%); }
        .xray-card small { display:block; margin-bottom:.8rem; color:#ce0e2d; font-size:.62rem; font-weight:900; letter-spacing:.14em; text-transform:uppercase; }
        .xray-card.middle small { color:#8ef0db; }.xray-card.back small { color:#eb6cf4; }
        .xray-line { height:9px; margin:.55rem 0; border-radius:99px; background:#e5eaec; }
        .xray-line.short { width:58%; }.xray-line.medium { width:78%; }
        .xray-score { display:flex; align-items:center; justify-content:space-between; margin-top:1.1rem; padding-top:.8rem; border-top:1px solid #e5eaec; color:#19647b; font-size:.68rem; font-weight:850; }
        .xray-score b { display:flex; gap:.3rem; }.xray-score i { width:9px; height:9px; border-radius:50%; background:#19647b; animation:xray-dot 1.8s ease-in-out infinite alternate; }.xray-score i:nth-child(2){animation-delay:-.4s}.xray-score i:nth-child(3){animation-delay:-.8s}.xray-score i:nth-child(4){animation-delay:-1.2s}
        .xray-orbit { position:absolute; right:2%; top:8%; width:74px; height:74px; border:1px dashed rgba(206,14,45,.45); border-radius:50%; animation:signal-aurora 12s linear infinite; }
        .xray-orbit::after { content:""; position:absolute; left:50%; top:-5px; width:10px; height:10px; border-radius:50%; background:#ce0e2d; box-shadow:0 0 0 7px rgba(206,14,45,.08); }
        @keyframes xray-dot { to { transform:translateY(-5px); background:#ce0e2d; } }
        .signal-stage { position:relative; min-height:520px; margin-top:5rem; overflow:hidden; isolation:isolate; border-radius:30px; background:radial-gradient(circle at 50% 48%,rgba(25,100,123,.32),transparent 27%),#151f24; box-shadow:0 28px 70px rgba(21,31,36,.24); }
        .signal-stage::before { content:""; position:absolute; inset:-45%; z-index:-2; opacity:.38; background:conic-gradient(from 90deg,transparent 0 20%,rgba(235,108,244,.18),transparent 32% 58%,rgba(88,220,187,.16),transparent 72%); animation:signal-aurora 18s linear infinite; }
        .signal-stage::after { content:""; position:absolute; inset:0; z-index:-1; opacity:.23; background-image:radial-gradient(circle,rgba(255,255,255,.75) 1px,transparent 1.5px); background-size:34px 34px; mask-image:linear-gradient(to bottom,transparent,#000 20%,#000 80%,transparent); }
        .signal-prompt { position:absolute; z-index:5; left:50%; top:50%; width:min(440px,72%); padding:1.35rem; overflow:hidden; border-radius:18px; color:#2d3144; background:white; box-shadow:0 24px 55px rgba(0,0,0,.3); transform:translate(-50%,-50%); transition:transform .35s ease,box-shadow .35s ease; }
        .signal-stage:hover .signal-prompt { transform:translate(-50%,-50%) scale(1.025); box-shadow:0 30px 70px rgba(0,0,0,.4); }
        .signal-prompt::after { content:""; position:absolute; top:0; bottom:0; width:90px; left:-120px; background:linear-gradient(90deg,transparent,rgba(235,108,244,.18),transparent); transform:skewX(-16deg); animation:response-scan 4.2s ease-in-out infinite; }
        .signal-prompt small { color:#ce0e2d; font-weight:900; letter-spacing:.1em; text-transform:uppercase; }
        .signal-prompt p { margin:.65rem 0 0; color:#565d70 !important; font-size:.78rem; line-height:1.65; }
        .signal-live { display:flex; align-items:center; gap:.45rem; margin-top:.8rem; color:#19647b; font-size:.58rem; font-weight:850; letter-spacing:.08em; text-transform:uppercase; }
        .signal-live i { width:7px; height:7px; border-radius:50%; background:#21b88f; box-shadow:0 0 0 0 rgba(33,184,143,.5); animation:live-pulse 1.8s infinite; }
        .signal-layer { position:absolute; z-index:4; width:245px; padding:1rem; border:1px solid rgba(238,205,185,.24); border-radius:16px; color:white; background:rgba(25,100,123,.58); backdrop-filter:blur(10px); font-size:.68rem; box-shadow:0 12px 35px rgba(0,0,0,.15); animation:signal-orbit 4s ease-in-out infinite alternate; transition:border-color .25s ease,background .25s ease,transform .25s ease; }
        .signal-layer::after { content:""; position:absolute; right:13px; top:13px; width:7px; height:7px; border-radius:50%; background:#72ead0; box-shadow:0 0 14px #72ead0; animation:live-pulse 2s infinite; }
        .signal-layer:hover { border-color:rgba(235,108,244,.75); background:rgba(25,100,123,.88); }
        .signal-layer.a { left:7%; top:11%; }.signal-layer.b { right:6%; top:15%; animation-delay:-1.3s; }.signal-layer.c { left:10%; bottom:10%; animation-delay:-2.4s; }.signal-layer.d { right:9%; bottom:9%; animation-delay:-3.2s; }
        .signal-layer b { display:block; margin-bottom:.3rem; color:#eb6cf4; }
        .signal-beam { position:absolute; z-index:2; left:50%; top:50%; width:34%; height:1px; opacity:.6; background:linear-gradient(90deg,transparent,rgba(114,234,208,.8),transparent); transform-origin:left center; animation:beam-flow 2.8s ease-in-out infinite; }
        .signal-beam.one { transform:rotate(-148deg); }.signal-beam.two { transform:rotate(-31deg); animation-delay:-.7s; }.signal-beam.three { transform:rotate(147deg); animation-delay:-1.4s; }.signal-beam.four { transform:rotate(31deg); animation-delay:-2.1s; }
        .signal-particle { position:absolute; z-index:1; width:6px; height:6px; border-radius:50%; background:#eb6cf4; box-shadow:0 0 16px rgba(235,108,244,.9); animation:signal-drift 8s ease-in-out infinite alternate; }
        .signal-particle.p1 { left:20%; top:43%; }.signal-particle.p2 { right:22%; top:38%; animation-delay:-2s; background:#72ead0; }.signal-particle.p3 { left:34%; bottom:17%; animation-delay:-4s; }.signal-particle.p4 { right:33%; top:16%; animation-delay:-6s; background:#72ead0; }
        .signal-ticker { position:absolute; z-index:3; left:50%; bottom:24px; display:flex; gap:1.4rem; width:max-content; color:rgba(255,255,255,.45); font-size:.56rem; font-weight:800; letter-spacing:.13em; text-transform:uppercase; animation:signal-ticker 18s linear infinite; }
        .signal-ticker b { color:#72ead0; }
        @keyframes signal-orbit { to { transform:translateY(-12px) rotate(1deg); } }
        @keyframes signal-aurora { to { transform:rotate(360deg); } }
        @keyframes response-scan { 0%,25% { left:-120px; } 70%,100% { left:calc(100% + 50px); } }
        @keyframes live-pulse { 70% { box-shadow:0 0 0 8px rgba(33,184,143,0); } 100% { box-shadow:0 0 0 0 rgba(33,184,143,0); } }
        @keyframes beam-flow { 0%,100% { opacity:.18; filter:blur(1px); } 50% { opacity:.8; filter:none; } }
        @keyframes signal-drift { to { transform:translate(55px,-38px) scale(1.8); opacity:.25; } }
        @keyframes signal-ticker { from { transform:translateX(-15%); } to { transform:translateX(-85%); } }
        .evaluation-collage { position:relative; padding:clamp(2rem,5vw,5rem); overflow:hidden; border-radius:30px; background:#fbfaf6; box-shadow:0 24px 65px rgba(21,31,36,.12); }
        .evaluation-collage::before,.evaluation-collage::after { content:""; position:absolute; top:0; bottom:0; width:110px; opacity:.28; background-image:linear-gradient(rgba(25,100,123,.28) 1px,transparent 1px),linear-gradient(90deg,rgba(25,100,123,.28) 1px,transparent 1px); background-size:20px 20px; }
        .evaluation-collage::before { left:0; mask-image:linear-gradient(90deg,#000,transparent); }.evaluation-collage::after { right:0; mask-image:linear-gradient(-90deg,#000,transparent); }
        .collage-copy { position:relative; z-index:3; display:grid; grid-template-columns:.75fr 1.25fr; gap:clamp(2rem,7vw,7rem); align-items:end; max-width:1250px; margin:0 auto 2.4rem; }
        .collage-copy small { color:#ce0e2d; font-size:.65rem; font-weight:900; letter-spacing:.16em; text-transform:uppercase; }
        .collage-copy h2 { margin:.65rem 0 0; color:#151f24; font-size:clamp(2.5rem,4.8vw,5.2rem); line-height:.95; letter-spacing:-.06em; }
        .collage-copy p { max-width:620px; margin:0; color:#4c5a60 !important; font-family:"Iowan Old Style","Palatino Linotype",Palatino,serif; font-size:clamp(.95rem,1.35vw,1.2rem); line-height:1.65; }
        .collage-visual { position:relative; z-index:2; min-height:clamp(430px,48vw,760px); overflow:hidden; border-radius:24px; background:#f7f4ed url('/app/static/mira-evaluation-collage.png') center/cover no-repeat; box-shadow:0 24px 50px rgba(21,31,36,.16); animation:collage-breathe 9s ease-in-out infinite alternate; }
        .collage-visual::after { content:""; position:absolute; inset:0; pointer-events:none; background:linear-gradient(120deg,transparent 35%,rgba(255,255,255,.25) 48%,transparent 60%); transform:translateX(-100%); animation:collage-light 7s ease-in-out infinite; }
        .collage-note { position:absolute; z-index:4; padding:.6rem .78rem; color:#151f24; background:#e2f0f2; box-shadow:0 8px 20px rgba(21,31,36,.16); font-family:monospace; font-size:.66rem; font-weight:800; transform:rotate(-3deg); animation:collage-note-float 3.4s ease-in-out infinite alternate; }
        .collage-note.intent { left:25%; top:20%; }.collage-note.compare { right:25%; top:14%; animation-delay:-1.1s; transform:rotate(3deg); }.collage-note.decide { right:14%; bottom:18%; animation-delay:-2.2s; background:#f4b3b4; }
        .collage-rating { position:absolute; z-index:4; left:50%; bottom:3%; display:flex; gap:.38rem; padding:.55rem .7rem; border-radius:999px; background:rgba(21,31,36,.88); backdrop-filter:blur(8px); transform:translateX(-50%); }
        .collage-rating i { display:grid; place-items:center; width:26px; height:26px; border:1px solid rgba(255,255,255,.28); border-radius:50%; color:white; font-size:.58rem; font-style:normal; animation:collage-rating-wave 2.3s ease-in-out infinite alternate; }.collage-rating i:nth-child(2){animation-delay:-.35s}.collage-rating i:nth-child(3){animation-delay:-.7s}.collage-rating i:nth-child(4){animation-delay:-1.05s;background:#ce0e2d}.collage-rating i:nth-child(5){animation-delay:-1.4s}
        @keyframes collage-breathe { to { background-position:51% 48%; } }
        @keyframes collage-light { 55%,100% { transform:translateX(120%); } }
        @keyframes collage-note-float { to { translate:0 -12px; rotate:2deg; } }
        @keyframes collage-rating-wave { to { transform:translateY(-5px); } }
        .story-numbers { display:grid; grid-template-columns:repeat(3,1fr); padding:0 clamp(1.3rem,7vw,8rem) clamp(4rem,9vw,8rem); background:#e2f0f2; }
        .story-number { padding:2rem; border-top:1px solid #cfd0d7; border-right:1px solid #d9dae0; }
        .story-number:last-child { border-right:0; }
        .story-number strong { display:block; color:#242741; font-family:Georgia,serif; font-size:clamp(3rem,6vw,6rem); font-weight:500; line-height:1; }
        .story-number span { color:#6d7280; font-size:.73rem; }
        .blindspot-story { position:relative; display:grid; grid-template-columns:.82fr 1.18fr; gap:clamp(2rem,7vw,8rem); align-items:center; padding:clamp(4rem,9vw,9rem) clamp(1.3rem,7vw,8rem); overflow:hidden; color:white; background:#151f24; }
        .blindspot-story::after { content:""; position:absolute; right:-10vw; top:-15vw; width:42vw; height:42vw; border:6vw solid rgba(25,100,123,.18); border-radius:50%; }
        .blindspot-copy { position:relative; z-index:2; }
        .blindspot-copy small { color:#8ef0db; font-size:.65rem; font-weight:900; letter-spacing:.16em; text-transform:uppercase; }
        .blindspot-copy h2 { max-width:650px; margin:.8rem 0 1.2rem; color:white; font-size:clamp(2.8rem,5vw,5.7rem); line-height:.94; letter-spacing:-.06em; }
        .blindspot-copy > p { max-width:570px; color:rgba(255,255,255,.62) !important; font-size:.92rem; line-height:1.75; }
        .blindspot-list { display:grid; gap:.7rem; margin-top:1.5rem; }
        .blindspot-item { display:grid; grid-template-columns:34px 1fr; gap:.7rem; align-items:start; padding:.8rem 0; border-top:1px solid rgba(255,255,255,.1); }
        .blindspot-item i { display:grid; place-items:center; width:28px; height:28px; border:1px solid rgba(142,240,219,.35); border-radius:50%; color:#8ef0db; font-size:.62rem; font-style:normal; }
        .blindspot-item b { display:block; margin-bottom:.2rem; color:white; font-size:.75rem; }.blindspot-item span { color:rgba(255,255,255,.5); font-size:.66rem; line-height:1.55; }
        .decision-anatomy { position:relative; z-index:2; min-height:560px; }
        .decision-ring { position:absolute; left:50%; top:50%; width:min(420px,76%); aspect-ratio:1; border:1px dashed rgba(142,240,219,.32); border-radius:50%; transform:translate(-50%,-50%); animation:decision-spin 22s linear infinite; }
        .decision-ring::before,.decision-ring::after { content:""; position:absolute; inset:14%; border:1px solid rgba(235,108,244,.22); border-radius:50%; }.decision-ring::after { inset:32%; background:radial-gradient(circle,#19647b,#151f24 68%); box-shadow:0 0 70px rgba(25,100,123,.4); }
        .decision-core { position:absolute; z-index:3; left:50%; top:50%; width:165px; padding:1.2rem; color:#151f24; border-radius:18px; background:#fbfaf6; box-shadow:0 20px 45px rgba(0,0,0,.32); text-align:center; transform:translate(-50%,-50%); animation:core-float 3s ease-in-out infinite alternate; }
        .decision-core small { color:#ce0e2d; font-size:.55rem; font-weight:900; letter-spacing:.12em; text-transform:uppercase; }.decision-core b { display:block; margin:.35rem 0; font-size:1.05rem; }.decision-core span { color:#697176; font-size:.58rem; }
        .decision-subject { position:absolute; z-index:4; width:175px; padding:.8rem; border:1px solid rgba(255,255,255,.12); border-radius:14px; background:rgba(255,255,255,.07); backdrop-filter:blur(8px); box-shadow:0 12px 30px rgba(0,0,0,.16); animation:subject-drift 4s ease-in-out infinite alternate; }
        .decision-subject b { display:block; margin-bottom:.28rem; color:#eb6cf4; font-size:.7rem; }.decision-subject span { color:rgba(255,255,255,.58); font-size:.59rem; line-height:1.45; }
        .decision-subject.one { left:0; top:12%; }.decision-subject.two { right:0; top:22%; animation-delay:-1.3s; }.decision-subject.three { left:9%; bottom:7%; animation-delay:-2.6s; }
        @keyframes decision-spin { to { transform:translate(-50%,-50%) rotate(360deg); } }
        @keyframes core-float { to { transform:translate(-50%,calc(-50% - 9px)) rotate(1deg); } }
        @keyframes subject-drift { to { transform:translateY(-13px) rotate(1.5deg); } }
        .story-process { color:white; background:#19647b; }
        .story-process h2 { max-width:850px; color:white; }
        .process-line { display:grid; grid-template-columns:repeat(4,1fr); margin-top:3rem; border-top:1px solid rgba(255,255,255,.15); }
        .process-step { position:relative; padding:2rem 1.3rem; border-right:1px solid rgba(255,255,255,.1); }
        .process-step::before { content:""; position:absolute; left:0; top:-5px; width:9px; height:9px; border-radius:50%; background:#eb6cf4; }
        .process-step b { display:block; margin-bottom:.65rem; color:#eecdb9; font-family:Georgia,serif; font-size:1.3rem; }
        .process-step p { color:rgba(255,255,255,.6) !important; font-size:.74rem; line-height:1.65; }
        .story-closing { text-align:center; background:#e2f0f2; }
        .story-closing h2 { max-width:900px; margin:.8rem auto 1.5rem; }
        .story-cta { display:inline-flex; padding:.9rem 1.15rem; color:white !important; border-radius:9px; background:#ce0e2d; box-shadow:0 12px 25px rgba(136,9,30,.22); font-size:.78rem; font-weight:850; text-decoration:none !important; transition:transform .2s ease; }
        .story-cta:hover { transform:translateY(-3px); }
        @supports (animation-timeline:view()) {
            .story-intro > *, .signal-stage, .story-number, .process-step, .story-closing > * {
                animation:story-reveal both ease-out;
                animation-timeline:view();
                animation-range:entry 8% cover 32%;
            }
            .story-number:nth-child(2),.process-step:nth-child(2) { animation-delay:.08s; }
            .story-number:nth-child(3),.process-step:nth-child(3) { animation-delay:.16s; }
            .process-step:nth-child(4) { animation-delay:.24s; }
        }
        @keyframes story-reveal { from { opacity:0; transform:translateY(42px); filter:blur(5px); } to { opacity:1; transform:none; filter:none; } }

        .landing-dashboard {
            min-height: calc(100vh - 7rem);
            padding: clamp(1.2rem, 2.5vw, 2.4rem);
            border: 1px solid rgba(109,93,252,.1);
            border-radius: 30px;
            background: #f2f3f7;
            box-shadow: 0 24px 65px rgba(41,35,92,.14);
        }
        .dashboard-banner {
            position: relative;
            display: grid;
            grid-template-columns: 1.05fr .9fr .65fr;
            align-items: center;
            gap: 2rem;
            min-height: 205px;
            padding: 2rem 2.4rem;
            overflow: hidden;
            border-radius: 22px;
            background: linear-gradient(115deg, #f8f5ff 0%, #f0edff 55%, #e8faf6 100%);
        }
        .dashboard-banner::after {
            content:"";
            position:absolute;
            right:-35px;
            top:-75px;
            width:240px;
            height:240px;
            border:36px solid rgba(109,93,252,.09);
            border-radius:50%;
        }
        .dashboard-banner h1 { margin:0; color:#25273b; font-size:clamp(2rem,3.2vw,3.5rem); line-height:1.03; letter-spacing:-.05em; }
        .dashboard-banner h1 span { color:#6856f5; }
        .dashboard-banner p { margin:0; color:#686f82 !important; font-size:.94rem; line-height:1.7; }
        .dashboard-illustration { position:relative; z-index:2; display:grid; place-items:center; height:145px; }
        .review-person { position:relative; width:70px; height:105px; animation:reviewer-float 3s ease-in-out infinite alternate; }
        .review-person .head { position:absolute; left:23px; top:0; width:25px; height:25px; border-radius:50%; background:#f2b48e; }
        .review-person .body { position:absolute; left:14px; top:24px; width:43px; height:55px; border-radius:14px 14px 8px 8px; background:linear-gradient(#6d5dfc,#5145cd); }
        .review-person .legs { position:absolute; left:21px; top:75px; width:29px; height:29px; border-left:8px solid #262a4b; border-right:8px solid #262a4b; }
        .review-person::before { content:"✓"; position:absolute; z-index:2; right:-24px; top:22px; display:grid; place-items:center; width:34px; height:34px; color:white; border-radius:10px; background:#13b8a6; box-shadow:0 9px 20px rgba(19,184,166,.25); transform:rotate(8deg); }
        .review-person::after { content:"······"; position:absolute; left:-70px; top:55px; color:#ff72aa; font-size:2rem; letter-spacing:5px; transform:rotate(12deg); }
        @keyframes reviewer-float { to { transform:translateY(-7px); } }
        .dashboard-toolbar { display:flex; align-items:center; justify-content:space-between; gap:1rem; padding:2.1rem .35rem 1.25rem; }
        .dashboard-toolbar h2 { margin:0; color:#24273a; font-size:1.65rem; letter-spacing:-.025em; }
        .dashboard-toolbar h2::after { content:""; display:block; width:38px; height:4px; margin-top:.65rem; border-radius:99px; background:linear-gradient(90deg,#6d5dfc,#13b8a6); }
        .dashboard-new { display:inline-flex; align-items:center; gap:.5rem; padding:.72rem .95rem; color:white !important; border-radius:10px; background:linear-gradient(135deg,#6d5dfc,#5145cd); box-shadow:0 9px 18px rgba(81,69,205,.2); font-size:.76rem; font-weight:800; text-decoration:none !important; }
        .project-grid { display:grid; grid-template-columns:repeat(3,1fr); gap:1.15rem; }
        .project-card { display:block; overflow:hidden; color:inherit !important; border:1px solid rgba(47,51,79,.08); border-radius:20px; background:white; box-shadow:0 10px 28px rgba(38,42,72,.07); text-decoration:none !important; transition:transform .22s ease, box-shadow .22s ease; }
        .project-card:hover { transform:translateY(-6px); box-shadow:0 18px 38px rgba(51,45,111,.14); }
        .project-visual { position:relative; display:flex; align-items:center; justify-content:center; min-height:205px; padding:1rem; overflow:hidden; }
        .project-visual.compare { background:linear-gradient(145deg,#edeaff,#dcd7ff); }
        .project-visual.criteria { background:linear-gradient(145deg,#e3faf5,#c9f0e8); }
        .project-visual.export { background:linear-gradient(145deg,#fff0f5,#ffe1eb); }
        .project-status { position:absolute; right:14px; top:13px; padding:.35rem .7rem; color:white; border-radius:999px; background:#6d5dfc; font-size:.6rem; font-weight:850; letter-spacing:.05em; text-transform:uppercase; }
        .project-visual.criteria .project-status { background:#13a994; }
        .project-visual.export .project-status { background:#dc668f; }
        .mini-compare { display:grid; grid-template-columns:1fr 1fr; gap:10px; width:82%; transform:rotate(-2deg); }
        .mini-response { height:105px; padding:12px; border-radius:12px; background:rgba(255,255,255,.92); box-shadow:0 9px 20px rgba(58,49,124,.11); }
        .mini-response i { display:block; height:6px; margin:7px 0; border-radius:99px; background:#d8d5ed; }
        .mini-response i:nth-child(2) { width:78%; }.mini-response i:nth-child(3) { width:55%; }
        .mini-response.selected { outline:3px solid #6d5dfc; }
        .mini-scale { display:flex; gap:8px; padding:1.2rem; border-radius:18px; background:rgba(255,255,255,.75); box-shadow:0 10px 24px rgba(20,113,101,.1); }
        .mini-scale i { display:grid; place-items:center; width:35px; height:35px; color:#53736e; border:1px solid #a9ddd3; border-radius:50%; background:white; font-style:normal; font-weight:800; }
        .mini-scale i:last-child { color:white; background:#13a994; transform:scale(1.15); }
        .mini-export { position:relative; width:105px; height:125px; border-radius:12px; background:white; box-shadow:0 15px 28px rgba(128,60,85,.14); }
        .mini-export::before { content:"CSV"; position:absolute; inset:28px 16px auto; padding:10px; color:#d65c84; border-radius:8px; background:#fff0f5; font-weight:900; text-align:center; }
        .mini-export::after { content:"↓"; position:absolute; left:35px; bottom:-16px; display:grid; place-items:center; width:36px; height:36px; color:white; border-radius:50%; background:#dc668f; }
        .project-copy { padding:1.1rem 1.2rem 1.25rem; }
        .project-copy h3 { margin:0 0 .35rem; color:#272a3e; font-size:1rem; }
        .project-copy p { min-height:42px; margin:0; color:#858a99 !important; font-size:.74rem; line-height:1.55; }
        .project-meta { display:flex; justify-content:space-between; margin-top:1rem; padding-top:.8rem; border-top:1px solid #ededf3; color:#696f80; font-size:.66rem; }

        .about-hero {
            display:grid;
            grid-template-columns:1.05fr .95fr;
            gap:clamp(2rem,6vw,6rem);
            align-items:center;
            min-height:clamp(650px,78vh,900px);
            padding:clamp(4rem,8vw,9rem) clamp(1.5rem,7vw,8rem);
            border-radius:0;
            color: white;
            overflow:hidden;
            position:relative;
            background: radial-gradient(circle at 86% 18%,rgba(235,108,244,.16),transparent 24%),linear-gradient(125deg,#151f24 0%,#19647b 120%);
            box-shadow: 0 22px 55px rgba(24,25,55,.2);
        }
        .block-container:has(.about-page-marker) { max-width:none; width:100%; min-height:100vh; margin:0; padding:0; border:0; border-radius:0; background:#e2f0f2; box-shadow:none; }
        .block-container:has(.about-page-marker) .inner-site-header { margin:14px clamp(14px,2vw,30px); }
        .stApp:has(.about-page-marker) .creative-backdrop { display:none; }
        .about-hero small { color:#8ce9dc; font-weight:850; letter-spacing:.14em; text-transform:uppercase; }
        .about-hero h1 { max-width:920px; margin:.8rem 0 1.2rem; color:white; font-size:clamp(3.2rem,6.7vw,7.2rem); line-height:.91; letter-spacing:-.065em; }
        .about-hero p { max-width:720px; color:rgba(255,255,255,.72) !important; font-size:1.05rem; line-height:1.75; }
        .about-hero-copy { position:relative; z-index:2; }
        .about-human-loop { position:relative; min-height:390px; }
        .about-loop-ring { position:absolute; left:50%; top:50%; width:310px; height:310px; border:1px dashed rgba(142,240,219,.36); border-radius:50%; transform:translate(-50%,-50%); animation:decision-spin 20s linear infinite; }
        .about-loop-ring::before,.about-loop-ring::after { content:""; position:absolute; border-radius:50%; }.about-loop-ring::before { inset:14%; border:1px solid rgba(235,108,244,.25); }.about-loop-ring::after { left:50%; top:-7px; width:14px; height:14px; background:#8ef0db; box-shadow:0 0 0 8px rgba(142,240,219,.08); }
        .about-loop-core { position:absolute; z-index:3; left:50%; top:50%; width:155px; padding:1.2rem; border-radius:22px; color:#151f24; background:#fbfaf6; box-shadow:0 22px 45px rgba(0,0,0,.28); text-align:center; transform:translate(-50%,-50%); animation:core-float 3s ease-in-out infinite alternate; }
        .about-loop-core i { display:grid; place-items:center; width:44px; height:44px; margin:0 auto .6rem; border-radius:50%; color:white; background:#ce0e2d; font-style:normal; font-weight:900; }.about-loop-core b { display:block; font-size:.9rem; }.about-loop-core span { color:#6d7477; font-size:.58rem; }
        .about-loop-tag { position:absolute; z-index:4; padding:.65rem .78rem; border:1px solid rgba(255,255,255,.13); border-radius:12px; color:white; background:rgba(255,255,255,.08); backdrop-filter:blur(8px); font-size:.63rem; font-weight:800; animation:subject-drift 3.6s ease-in-out infinite alternate; }.about-loop-tag.one { left:2%; top:18%; }.about-loop-tag.two { right:0; top:24%; animation-delay:-1.2s; }.about-loop-tag.three { left:15%; bottom:10%; animation-delay:-2.4s; }
        .about-manifesto { display:grid; grid-template-columns:.65fr 1.35fr; gap:clamp(2rem,7vw,7rem); align-items:start; margin:0; padding:clamp(5rem,10vw,10rem) clamp(1.3rem,7vw,8rem); border-radius:0; background:#e2f0f2; }
        .about-manifesto small { color:#ce0e2d; font-size:.65rem; font-weight:900; letter-spacing:.15em; text-transform:uppercase; }.about-manifesto h2 { margin:.6rem 0 0; color:#151f24; font-size:clamp(2rem,4vw,4rem); line-height:.98; letter-spacing:-.055em; }.about-manifesto p { margin:0; color:#536168 !important; font-family:"Iowan Old Style","Palatino Linotype",Palatino,serif; font-size:clamp(1rem,1.5vw,1.3rem); line-height:1.75; }
        .about-domain-story { position:relative; padding:clamp(5rem,9vw,9rem) clamp(1.3rem,7vw,8rem); overflow:hidden; background:#eecdb9; }
        .about-domain-story::after { content:"भाषा · CONTEXT · TRUST"; position:absolute; right:-3%; top:10%; color:rgba(21,31,36,.045); font-size:clamp(4rem,10vw,11rem); font-weight:950; letter-spacing:-.07em; white-space:nowrap; transform:rotate(-5deg); }
        .domain-story-head { position:relative; z-index:2; display:grid; grid-template-columns:.78fr 1.22fr; gap:clamp(2rem,7vw,8rem); align-items:start; }
        .domain-story-head small { color:#ce0e2d; font-size:.65rem; font-weight:900; letter-spacing:.15em; text-transform:uppercase; }.domain-story-head h2 { max-width:650px; margin:.7rem 0 0; color:#151f24; font-size:clamp(2.8rem,5vw,5.7rem); line-height:.94; letter-spacing:-.06em; }.domain-story-head p { max-width:700px; margin:0; color:#4f5658 !important; font-family:"Iowan Old Style","Palatino Linotype",Palatino,serif; font-size:clamp(1rem,1.45vw,1.3rem); line-height:1.75; }
        .domain-subjects { position:relative; z-index:2; display:grid; grid-template-columns:repeat(3,1fr); gap:1rem; margin-top:3.2rem; }
        .domain-subject { min-height:220px; padding:1.4rem; border:1px solid rgba(21,31,36,.1); border-radius:20px; background:rgba(251,250,246,.7); backdrop-filter:blur(8px); transition:transform .25s ease,background .25s ease; }.domain-subject:hover { background:#fbfaf6; transform:translateY(-7px) rotate(-.5deg); }.domain-subject i { display:grid; place-items:center; width:38px; height:38px; margin-bottom:1.5rem; border-radius:50%; color:white; background:#19647b; font-style:normal; font-size:.7rem; font-weight:900; }.domain-subject:nth-child(2) i { background:#ce0e2d; }.domain-subject:nth-child(3) i { color:#151f24; background:#eb6cf4; }.domain-subject h3 { margin:0 0 .55rem; color:#151f24; font-size:1.05rem; }.domain-subject p { margin:0; color:#62696b !important; font-size:.75rem; line-height:1.7; }
        .alignment-usecases { display:grid; grid-template-columns:repeat(4,1fr); border-top:1px solid rgba(21,31,36,.16); margin-top:2.4rem; padding-top:1.8rem; }.alignment-usecase { padding:1rem 1.2rem; border-right:1px solid rgba(21,31,36,.12); }.alignment-usecase:last-child { border-right:0; }.alignment-usecase b { display:block; margin-bottom:.35rem; color:#19647b; font-size:.72rem; }.alignment-usecase span { color:#62696b; font-size:.66rem; line-height:1.55; }
        .about-principles { padding:clamp(4rem,8vw,8rem) clamp(1.3rem,7vw,8rem); background:white; }
        .about-section-heading { display:flex; align-items:end; justify-content:space-between; gap:2rem; margin-bottom:2.2rem; }
        .about-section-heading small { color:#ce0e2d; font-size:.65rem; font-weight:900; letter-spacing:.15em; text-transform:uppercase; }
        .about-section-heading h2 { max-width:800px; margin:.55rem 0 0; color:#151f24; font-size:clamp(2.6rem,5vw,5.4rem); line-height:.96; letter-spacing:-.06em; }
        .about-section-heading p { max-width:430px; margin:0; color:#667276 !important; font-size:.82rem; line-height:1.7; }
        .about-grid { display:grid; grid-template-columns:repeat(3,1fr); gap:1rem; margin:0; }
        .about-card { padding:1.5rem; border:1px solid rgba(25,100,123,.12); border-radius:20px; background:rgba(255,255,255,.9); box-shadow:0 10px 28px rgba(21,31,36,.07); transition:transform .2s ease, box-shadow .2s ease; }
        .about-card:hover { transform:translateY(-5px); box-shadow:0 18px 38px rgba(52,44,120,.12); }
        .about-card-icon { display:grid; place-items:center; width:42px; height:42px; margin-bottom:1rem; border-radius:12px; color:#19647b; background:#e2f0f2; font-size:1.15rem; }
        .about-card h3 { margin:0 0 .4rem; color:#24283c; font-size:1rem; }
        .about-card p { margin:0; color:#73798b !important; font-size:.82rem; line-height:1.65; }
        .about-workflow { padding:clamp(4rem,8vw,8rem) clamp(1.3rem,7vw,8rem); color:white; background:#151f24; }
        .about-workflow .about-section-heading h2 { color:white; }.about-workflow .about-section-heading p { color:rgba(255,255,255,.55) !important; }
        .about-steps { display:grid; grid-template-columns:repeat(4,1fr); gap:.8rem; padding:1.2rem 0 0; border-top:1px solid rgba(255,255,255,.13); border-radius:0; background:transparent; }
        .about-step { padding:1rem; color:rgba(255,255,255,.58); font-size:.78rem; line-height:1.55; }
        .about-step b { display:block; margin-bottom:.45rem; color:#8ef0db; font-size:.7rem; letter-spacing:.08em; text-transform:uppercase; }
        .about-actions { display:flex; align-items:center; justify-content:space-between; gap:1rem; margin:0; padding:clamp(2rem,5vw,4rem) clamp(1.3rem,7vw,8rem); border:0; border-radius:0; background:#fbfaf6; }
        .about-actions-copy strong { display:block; color:#292d43; font-size:.86rem; }
        .about-actions-copy span { color:#7a8091; font-size:.72rem; }
        .about-action-links { display:flex; align-items:center; gap:.7rem; }
        .about-home-link, .about-company-link { display:inline-flex; align-items:center; gap:.4rem; padding:.7rem .9rem; border-radius:10px; font-size:.74rem; font-weight:800; text-decoration:none !important; white-space:nowrap; }
        .about-home-link { color:#19647b !important; border:1px solid rgba(25,100,123,.2); background:#eaf5f5; }
        .about-company-link { color:white !important; background:linear-gradient(135deg,#19647b,#151f24); box-shadow:0 8px 17px rgba(21,31,36,.18); }
        .block-container:has(.resources-page-marker) { max-width:none; width:100%; min-height:100vh; margin:0; padding:0; background:#fbfaf6; }
        .block-container:has(.resources-page-marker) .inner-site-header { margin:14px clamp(14px,2vw,30px); }
        .stApp:has(.resources-page-marker) .creative-backdrop { display:none; }
        .resources-hero { padding:clamp(5rem,9vw,9rem) clamp(1.3rem,7vw,8rem); color:white; background:radial-gradient(circle at 80% 20%,rgba(235,108,244,.16),transparent 24%),#151f24; }
        .resources-hero small { color:#8ef0db; font-size:.65rem; font-weight:900; letter-spacing:.16em; text-transform:uppercase; }.resources-hero h1 { max-width:1000px; margin:.8rem 0 1.2rem; color:white; font-size:clamp(3.2rem,6vw,6.7rem); line-height:.92; letter-spacing:-.065em; }.resources-hero p { max-width:700px; color:rgba(255,255,255,.62) !important; font-size:1rem; line-height:1.75; }
        .resource-library { padding:clamp(4rem,8vw,8rem) clamp(1.3rem,7vw,8rem); background:#e2f0f2; }
        .resource-grid { display:grid; grid-template-columns:repeat(2,1fr); gap:1rem; margin-top:2rem; }
        .resource-card { min-height:250px; padding:1.6rem; border:1px solid rgba(25,100,123,.12); border-radius:22px; background:#fbfaf6; transition:transform .22s ease,box-shadow .22s ease; }.resource-card:hover { transform:translateY(-6px); box-shadow:0 20px 42px rgba(21,31,36,.11); }.resource-card small { color:#ce0e2d; font-size:.6rem; font-weight:900; letter-spacing:.13em; text-transform:uppercase; }.resource-card h3 { margin:.7rem 0 .55rem; color:#151f24; font-size:1.35rem; }.resource-card p { color:#667074 !important; font-size:.78rem; line-height:1.7; }.resource-tags { display:flex; flex-wrap:wrap; gap:.4rem; margin-top:1.2rem; }.resource-tags span { padding:.4rem .55rem; border-radius:999px; color:#31545e; background:#e2f0f2; font-size:.58rem; font-weight:800; }
        .rating-guide { display:grid; grid-template-columns:repeat(5,1fr); gap:.65rem; margin-top:2rem; }.rating-guide div { padding:1rem; border-top:3px solid #19647b; background:white; }.rating-guide b { display:block; color:#151f24; font-size:1.5rem; }.rating-guide span { color:#71797c; font-size:.65rem; }
        .projects-page-marker + div { scroll-margin-top:1rem; }
        .projects-hero { max-width:1180px; margin:6.8rem auto 1.25rem; padding:clamp(1.4rem,4vw,3rem); border:1px solid rgba(25,100,123,.14); border-radius:28px; background:linear-gradient(135deg,rgba(255,255,255,.96),rgba(226,240,242,.9)); box-shadow:0 24px 65px rgba(21,31,36,.1); }
        .projects-hero small { color:#19647b; font-size:.65rem; font-weight:900; letter-spacing:.14em; text-transform:uppercase; }.projects-hero h1 { margin:.6rem 0; color:#151f24; font-size:clamp(2.2rem,5vw,4.8rem); line-height:.96; letter-spacing:-.055em; }.projects-hero p { max-width:720px; margin:0; color:#667074 !important; line-height:1.65; }
        .saved-project-card { min-height:100%; padding:1.15rem; border:1px solid rgba(25,100,123,.13); border-radius:18px; background:rgba(255,255,255,.94); box-shadow:0 12px 32px rgba(21,31,36,.07); }.saved-project-card small { color:#7a858b; font-size:.62rem; }.saved-project-card h3 { margin:.35rem 0 .25rem; color:#151f24; font-size:1rem; word-break:break-word; }.saved-project-card p { margin:0 0 .8rem; color:#6d767a !important; font-size:.72rem; }.saved-project-progress { height:7px; overflow:hidden; border-radius:99px; background:#e3e9e9; }.saved-project-progress i { display:block; height:100%; border-radius:inherit; background:linear-gradient(90deg,#19647b,#13a994); }
        .signin-shell { max-width:520px; margin:8vh auto 2rem; padding:2rem; text-align:center; border:1px solid rgba(109,93,252,.14); border-radius:24px; background:white; box-shadow:0 22px 55px rgba(52,44,120,.14); }
        .google-mark { display:grid; place-items:center; width:58px; height:58px; margin:0 auto 1.1rem; border:1px solid #e5e7ef; border-radius:16px; color:#4285f4; background:#fff; box-shadow:0 8px 20px rgba(40,44,80,.08); font-size:1.55rem; font-weight:900; }
        .signin-shell h1 { margin:.2rem 0 .5rem; color:#25283b; font-size:1.75rem; }
        .signin-shell p { color:#73798b !important; font-size:.86rem; line-height:1.6; }
        .signed-user { display:flex; align-items:center; gap:.9rem; margin:1.2rem 0; padding:1rem; text-align:left; border-radius:14px; background:#f4f2ff; }
        .signed-avatar { display:grid; place-items:center; flex:0 0 42px; width:42px; height:42px; color:white; border-radius:50%; background:linear-gradient(135deg,#6d5dfc,#13b8a6); font-weight:900; }
        .signed-user strong, .signed-user span { display:block; }
        .signed-user span { color:#757b8e; font-size:.74rem; }
        .block-container:has(.auth-page-marker) { max-width:none; width:100%; min-height:100vh; margin:0; padding:clamp(1rem,2vw,2rem); border:0; border-radius:0; background:url('/app/static/mira-account-cockpit-v2.png') center/cover fixed no-repeat,#071c30; box-shadow:none; animation:account-world-drift 10s ease-in-out infinite alternate; }
        .stApp:has(.auth-page-marker) .creative-backdrop { display:none; }
        .auth-story { position:relative; max-width:650px; padding:2rem 1rem; }
        .auth-brand { display:inline-flex; align-items:center; gap:.55rem; color:#5b4ae6; font-size:.72rem; font-weight:900; letter-spacing:.14em; text-transform:uppercase; }
        .auth-brand i { width:9px; height:9px; border-radius:50%; background:#13b8a6; box-shadow:0 0 0 6px rgba(19,184,166,.1); }
        .auth-story h1 { max-width:620px; margin:1.2rem 0 1rem; color:#202338; font-size:clamp(2.8rem,5vw,5.4rem); line-height:.96; letter-spacing:-.065em; }
        .auth-story h1 span { color:transparent; background:linear-gradient(105deg,#6856f5,#13a994); background-clip:text; -webkit-background-clip:text; }
        .auth-story > p { max-width:530px; color:#6f7588 !important; font-size:1rem; line-height:1.75; }
        .auth-benefits { display:flex; flex-wrap:wrap; gap:.7rem; margin-top:1.7rem; }
        .auth-benefits span { padding:.55rem .72rem; color:#555c72; border:1px solid rgba(109,93,252,.12); border-radius:999px; background:rgba(255,255,255,.65); font-size:.7rem; font-weight:750; }
        .auth-benefits span::before { content:"✓"; margin-right:.35rem; color:#13a994; }
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.auth-panel-marker) { max-width:470px; margin:auto; border:1px solid rgba(109,93,252,.13) !important; border-radius:26px !important; background:rgba(255,255,255,.94) !important; box-shadow:0 28px 70px rgba(52,44,120,.17); }
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.auth-panel-marker) > div { padding:clamp(1.4rem,3vw,2.2rem) !important; }
        .auth-panel-head { text-align:center; }
        .google-logo-pro { display:grid; place-items:center; width:58px; height:58px; margin:0 auto 1.15rem; border:1px solid #e6e7ee; border-radius:16px; background:white; box-shadow:0 9px 22px rgba(38,42,72,.09); font-size:1.7rem; font-weight:900; }
        .google-logo-pro span { color:#4285f4; }
        .auth-panel-head h2 { margin:0 0 .5rem; color:#25283c; font-size:1.55rem; letter-spacing:-.025em; }
        .auth-panel-head p { margin:0 0 1.2rem; color:#7a8091 !important; font-size:.8rem; line-height:1.6; }
        .auth-trust { margin-top:1rem; padding-top:1rem; border-top:1px solid #ececf3; color:#9296a5; font-size:.66rem; text-align:center; }
        .auth-route-link { display:flex; align-items:center; justify-content:center; width:100%; margin-top:.55rem; padding:.62rem .8rem; color:#5145cd !important; border:1px solid #d9d5fa; border-radius:9px; background:#f7f5ff; font-size:.78rem; font-weight:750; text-decoration:none !important; }
        .auth-route-link.primary { margin:0 0 .55rem; color:white !important; border-color:transparent; background:linear-gradient(135deg,#6d5dfc,#5145cd); }
        .auth-entry { position:relative; z-index:1; max-width:760px; margin:1vh auto 2rem; text-align:center; }
        .auth-entry-brand { display:inline-flex; align-items:center; gap:.65rem; color:#a9a2ff; font-size:.7rem; font-weight:900; letter-spacing:.16em; text-transform:uppercase; }
        .auth-entry-brand i { position:relative; width:22px; height:22px; border:2px solid #8ce9dc; border-radius:7px; transform:rotate(45deg); }
        .auth-entry-brand i::after { content:""; position:absolute; inset:5px; border-radius:3px; background:#8ce9dc; }
        .auth-entry h1 { margin:1.3rem 0 .7rem; color:white; font-size:clamp(2.5rem,5vw,4.6rem); line-height:1; letter-spacing:-.055em; }
        .auth-entry h1 span { color:transparent; background:linear-gradient(100deg,#a9a2ff,#8ce9dc); background-clip:text; -webkit-background-clip:text; }
        .auth-entry p { max-width:560px; margin:0 auto; color:rgba(255,255,255,.6) !important; font-size:.9rem; line-height:1.7; }
        .auth-proof-row { display:grid; grid-template-columns:repeat(3,1fr); gap:.75rem; max-width:610px; margin:1.2rem auto 0; }
        .auth-proof-item { padding:.8rem; color:rgba(255,255,255,.6); border:1px solid rgba(255,255,255,.08); border-radius:12px; background:rgba(255,255,255,.04); font-size:.68rem; }
        .auth-proof-item b { display:block; margin-bottom:.2rem; color:#8ce9dc; font-size:.72rem; }
        .account-story { position:relative; max-width:680px; padding:clamp(1.5rem,3vw,3rem); border:1px solid rgba(255,255,255,.11); border-radius:30px; background:linear-gradient(135deg,rgba(7,28,48,.82),rgba(21,31,36,.48)); box-shadow:0 30px 80px rgba(0,0,0,.26); backdrop-filter:blur(12px); }
        .account-kicker { display:inline-flex; align-items:center; gap:.55rem; color:#8ef0db; font-size:.68rem; font-weight:900; letter-spacing:.16em; text-transform:uppercase; }.account-kicker i { width:9px; height:9px; border-radius:50%; background:#ce0e2d; box-shadow:0 0 0 7px rgba(206,14,45,.1); }
        .account-story h1 { max-width:650px; margin:1.15rem 0 1rem; color:white; font-size:clamp(3rem,5.3vw,5.7rem); line-height:.91; letter-spacing:-.065em; }.account-story h1 span { color:#8ef0db; }
        .account-story > p { max-width:590px; color:rgba(255,255,255,.58) !important; font-size:.95rem; line-height:1.75; }
        .account-trust-grid { display:grid; grid-template-columns:repeat(3,1fr); gap:.65rem; margin-top:2rem; }.account-trust-item { min-height:105px; padding:.9rem; border:1px solid rgba(255,255,255,.09); border-radius:15px; background:rgba(255,255,255,.04); }.account-trust-item i { display:block; margin-bottom:.75rem; color:#eb6cf4; font-size:.75rem; font-style:normal; font-weight:900; }.account-trust-item b { display:block; color:white; font-size:.7rem; }.account-trust-item span { color:rgba(255,255,255,.42); font-size:.6rem; line-height:1.45; }
        .account-signal-line { display:flex; align-items:center; gap:.45rem; margin-top:1.5rem; color:rgba(255,255,255,.42); font-size:.6rem; font-weight:800; letter-spacing:.1em; text-transform:uppercase; }.account-signal-line i { width:7px; height:7px; border-radius:50%; background:#8ef0db; animation:live-pulse 1.8s infinite; }
        .stApp:has(.auth-page-marker) div[data-testid="stHorizontalBlock"]:has(.account-story-marker) { max-width:1480px; min-height:calc(100vh - 210px); margin:0 auto; align-items:center; }
        .login-cockpit { position:relative; min-height:620px; margin:1rem 0; overflow:hidden; isolation:isolate; border:1px solid rgba(142,240,219,.15); border-radius:34px; background:radial-gradient(circle at 50% 48%,rgba(25,100,123,.72),transparent 24%),linear-gradient(145deg,rgba(7,28,48,.8),rgba(21,31,36,.88)); box-shadow:0 35px 90px rgba(0,0,0,.38); }
        .login-cockpit::before { content:""; position:absolute; inset:0; z-index:-2; opacity:.25; background-image:linear-gradient(rgba(142,240,219,.2) 1px,transparent 1px),linear-gradient(90deg,rgba(142,240,219,.2) 1px,transparent 1px); background-size:42px 42px; perspective:500px; transform:scale(1.2) rotateX(55deg); animation:cockpit-grid 9s linear infinite; }
        .login-cockpit::after { content:""; position:absolute; inset:-40%; z-index:-1; background:conic-gradient(transparent 0 18%,rgba(235,108,244,.13),transparent 32% 60%,rgba(142,240,219,.14),transparent 75%); animation:signal-aurora 20s linear infinite; }
        .cockpit-title { position:absolute; z-index:5; left:50%; top:7%; color:rgba(255,255,255,.72); text-align:center; transform:translateX(-50%); }.cockpit-title small { display:block; color:#8ef0db; font-size:.58rem; font-weight:900; letter-spacing:.18em; text-transform:uppercase; }.cockpit-title b { display:block; margin-top:.35rem; color:white; font-size:clamp(1.5rem,3vw,2.7rem); letter-spacing:-.045em; }
        .evaluation-tunnel { position:absolute; left:50%; top:52%; width:440px; height:440px; border:1px solid rgba(142,240,219,.2); border-radius:50%; transform:translate(-50%,-50%); box-shadow:0 0 0 55px rgba(25,100,123,.08),0 0 0 110px rgba(235,108,244,.035); animation:tunnel-pulse 3s ease-in-out infinite alternate; }.evaluation-tunnel::before,.evaluation-tunnel::after { content:""; position:absolute; border-radius:50%; }.evaluation-tunnel::before { inset:14%; border:1px dashed rgba(235,108,244,.35); animation:signal-aurora 12s linear infinite; }.evaluation-tunnel::after { inset:31%; border:2px solid rgba(142,240,219,.28); box-shadow:0 0 45px rgba(142,240,219,.2); }
        .cockpit-response { position:absolute; z-index:4; width:190px; padding:1rem; border:1px solid rgba(255,255,255,.17); border-radius:16px; background:rgba(251,250,246,.94); box-shadow:0 20px 45px rgba(0,0,0,.3); animation:cockpit-card-float 4s ease-in-out infinite alternate; }.cockpit-response.a { left:8%; top:27%; transform:rotate(-5deg); }.cockpit-response.b { right:8%; top:24%; border:2px solid #8ef0db; transform:rotate(5deg); animation-delay:-1.3s; }.cockpit-response.c { left:10%; bottom:12%; transform:rotate(3deg); animation-delay:-2.6s; }.cockpit-response small { color:#ce0e2d; font-size:.52rem; font-weight:900; letter-spacing:.1em; text-transform:uppercase; }.cockpit-response i { display:block; width:92%; height:6px; margin:.5rem 0; border-radius:99px; background:#cbd5d7; }.cockpit-response i.short { width:55%; background:#19647b; }.cockpit-response b { position:absolute; right:10px; top:10px; display:grid; place-items:center; width:25px; height:25px; border-radius:50%; color:#151f24; background:#8ef0db; }
        .cockpit-signal { position:absolute; z-index:4; padding:.55rem .7rem; border:1px solid rgba(255,255,255,.12); border-radius:999px; color:white; background:rgba(7,28,48,.78); backdrop-filter:blur(9px); font-size:.55rem; font-weight:850; animation:subject-drift 3s ease-in-out infinite alternate; }.cockpit-signal.context { left:3%; top:13%; }.cockpit-signal.language { right:3%; top:13%; animation-delay:-.8s; }.cockpit-signal.emotion { right:5%; bottom:16%; animation-delay:-1.6s; }.cockpit-signal.safety { left:36%; bottom:5%; animation-delay:-2.4s; }
        .cockpit-beam { position:absolute; z-index:2; left:50%; top:50%; width:43%; height:2px; transform-origin:left center; background:linear-gradient(90deg,rgba(142,240,219,.8),transparent); animation:beam-flow 2s ease-in-out infinite; }.cockpit-beam.one{transform:rotate(205deg)}.cockpit-beam.two{transform:rotate(-25deg);animation-delay:-.7s}.cockpit-beam.three{transform:rotate(145deg);animation-delay:-1.4s}
        .login-cockpit.success .evaluation-tunnel { border-color:#8ef0db; box-shadow:0 0 0 55px rgba(142,240,219,.09),0 0 85px rgba(142,240,219,.28); animation-duration:1.4s; }.login-cockpit.success .cockpit-response { animation-duration:2s; }.login-cockpit.success .cockpit-title small { color:#eb6cf4; }
        .stApp:has(.auth-page-marker) .st-key-account_login_zone { position:relative; z-index:20; display:flex; align-items:center; justify-content:center; min-height:calc(100vh - 220px); padding:3rem 1rem; }
        .stApp:has(.auth-page-marker) .st-key-account_login_zone > div { width:100%; }
        .stApp:has(.auth-page-marker) .st-key-account_login_zone div[data-testid="stVerticalBlockBorderWrapper"]:has(.auth-panel-marker) { width:min(470px,calc(100vw - 2rem)); margin:auto; border:1px solid rgba(255,255,255,.7) !important; background:#fbfaf6 !important; box-shadow:0 35px 100px rgba(0,0,0,.55),0 0 0 10px rgba(7,28,48,.3) !important; backdrop-filter:none; }
        .stApp:has(.auth-page-marker):has(.account-world-state.success) div[data-testid="stVerticalBlockBorderWrapper"]:has(.auth-panel-marker) { border-color:rgba(142,240,219,.55) !important; box-shadow:0 0 0 8px rgba(142,240,219,.07),0 35px 90px rgba(0,0,0,.42); animation:authenticated-panel 1.8s ease-in-out infinite alternate; }
        @keyframes cockpit-grid { to { background-position:0 84px,84px 0; } }
        @keyframes tunnel-pulse { to { transform:translate(-50%,-50%) scale(1.06); } }
        @keyframes cockpit-card-float { to { translate:0 -13px; rotate:2deg; } }
        @keyframes account-world-drift { to { background-position:51% 49%; } }
        @keyframes authenticated-panel { to { transform:translateY(-6px); box-shadow:0 0 0 13px rgba(142,240,219,0),0 42px 100px rgba(0,0,0,.48); } }
        .block-container:has(.auth-page-marker) { background:radial-gradient(circle at 8% 10%,rgba(206,14,45,.12),transparent 26%),radial-gradient(circle at 92% 88%,rgba(235,108,244,.14),transparent 24%),#e2f0f2 !important; animation:none !important; }
        .st-key-account_page_shell { position:relative; isolation:isolate; width:min(1480px,100%); aspect-ratio:4/3; min-height:0; margin:0 auto; padding:0; overflow:hidden; border:1px solid rgba(25,100,123,.12); border-radius:34px; background-color:#e9f3ee !important; background-image:url('/app/static/mira-login-world-v3.png') !important; background-position:center !important; background-size:cover !important; background-repeat:no-repeat !important; box-shadow:0 40px 110px rgba(21,31,36,.22); }
        .st-key-account_page_shell > div:first-child { height:100%; }
        .st-key-account_page_shell div[data-testid="stImage"] { position:absolute; inset:0; z-index:0; width:100%; height:100%; margin:0; overflow:hidden; }
        .st-key-account_page_shell div[data-testid="stImage"] > div { width:100%; height:100%; }
        .st-key-account_page_shell div[data-testid="stImage"] img { display:block; width:100% !important; height:100% !important; object-fit:cover !important; object-position:center; animation:account-image-breathe 7s ease-in-out infinite alternate; }
        .account-art-copy { position:absolute; z-index:3; left:22px; right:22px; bottom:20px; padding:1rem 1.1rem; border:1px solid rgba(255,255,255,.12); border-radius:16px; color:white; background:rgba(7,28,48,.76); box-shadow:0 10px 30px rgba(0,0,0,.24); backdrop-filter:blur(10px); }.account-art-copy small { display:block; margin-bottom:.35rem; color:#8ef0db; font-size:.56rem; font-weight:900; letter-spacing:.13em; text-transform:uppercase; }.account-art-copy strong { display:block; max-width:570px; color:white; font-size:clamp(.82rem,1.2vw,1.05rem); line-height:1.45; }
        .st-key-account_auth_panel { position:absolute; z-index:5; left:5.4%; top:15%; width:37%; max-width:470px; margin:0; padding:clamp(1rem,2vw,1.65rem); border:0 !important; border-radius:24px !important; background:rgba(255,255,255,.9) !important; box-shadow:0 24px 60px rgba(15,54,67,.13) !important; backdrop-filter:blur(8px); }
        .st-key-account_auth_panel .auth-panel-head h2 { color:#151f24; font-size:clamp(2rem,3vw,3rem); letter-spacing:-.05em; }.st-key-account_auth_panel .auth-panel-head p { color:#687377 !important; }
        .account-auth-state { display:flex; align-items:center; justify-content:center; gap:.45rem; width:max-content; margin:0 auto 1rem; padding:.45rem .65rem; border-radius:999px; color:#19647b; background:#e2f0f2; font-size:.57rem; font-weight:900; letter-spacing:.1em; text-transform:uppercase; }.account-auth-state i { width:7px; height:7px; border-radius:50%; background:#19647b; animation:live-pulse 1.8s infinite; }.account-auth-state.ready { color:white; background:#19647b; }.account-auth-state.ready i { background:#8ef0db; }
        @keyframes account-image-breathe { to { transform:scale(1.018); filter:saturate(1.08); } }
        .stApp:has(.auth-page-marker) div[data-testid="stVerticalBlockBorderWrapper"]:has(.auth-panel-marker) { border-color:rgba(142,240,219,.15) !important; box-shadow:0 34px 80px rgba(0,0,0,.32); }
        .site-footer { display:flex; align-items:center; justify-content:space-between; gap:1rem; margin-top:1.35rem; padding:1.05rem 1.2rem; color:#777d8f; border-top:1px solid rgba(109,93,252,.11); font-size:.7rem; }
        .site-footer-brand { display:flex; align-items:center; gap:.5rem; padding:.35rem .5rem; color:#3c4057 !important; border-radius:999px; font-weight:850; text-decoration:none !important; transition:transform .2s ease,background .2s ease,color .2s ease; }
        .site-footer-brand:hover { color:#19647b !important; background:rgba(25,100,123,.08); transform:translateY(-2px); }
        .site-footer-brand:focus-visible { outline:2px solid rgba(25,100,123,.3); outline-offset:2px; }
        .site-footer-brand i { width:8px; height:8px; border-radius:50%; background:linear-gradient(135deg,#6d5dfc,#13b8a6); box-shadow:0 0 0 5px rgba(109,93,252,.08); }
        .site-footer-brand:hover i { animation:footer-brand-pulse .8s ease-in-out infinite alternate; }
        @keyframes footer-brand-pulse { to { transform:scale(1.35); box-shadow:0 0 0 8px rgba(25,100,123,0); } }
        .site-footer-links { display:flex; gap:1rem; }
        .site-footer a { color:#6760be !important; font-weight:750; text-decoration:none !important; }
        .stApp:has(.auth-page-marker) .site-footer { color:#687377; border:1px solid rgba(25,100,123,.1); border-radius:18px; background:rgba(255,255,255,.88); box-shadow:0 12px 30px rgba(21,31,36,.08); }
        .stApp:has(.auth-page-marker) .site-footer-brand,.stApp:has(.auth-page-marker) .site-footer a { color:#19647b !important; }
        @supports (animation-timeline: scroll()) {
            .stApp:has(.auth-page-marker) .site-footer { position:fixed; z-index:90; left:3vw; right:3vw; bottom:1rem; margin:0; opacity:0; pointer-events:none; transform:translateY(130%); animation:account-footer-reveal linear both; animation-timeline:scroll(root); animation-range:75% 100%; }
            @keyframes account-footer-reveal { 0%,35% { opacity:0; pointer-events:none; transform:translateY(130%); } 75%,100% { opacity:1; pointer-events:auto; transform:translateY(0); } }
        }

        .hero-eyebrow {
            display: inline-flex;
            align-items: center;
            gap: 0.45rem;
            padding: 0.38rem 0.75rem;
            margin-bottom: 0.85rem;
            border: 1px solid rgba(255,255,255,.24);
            border-radius: 999px;
            color: rgba(255,255,255,.92);
            background: rgba(255,255,255,.11);
            font-size: 0.78rem;
            font-weight: 750;
            letter-spacing: 0.08em;
            text-transform: uppercase;
        }

        .hero-eyebrow-dot {
            width: 0.5rem;
            height: 0.5rem;
            border-radius: 50%;
            background: #70f0d5;
            box-shadow: 0 0 0 5px rgba(112,240,213,.13);
        }

        .parent-brand-card {
            display: flex;
            align-items: center;
            gap: 1.1rem;
            padding: 1.05rem 1.2rem;
            margin: 0.35rem 0 1.35rem;
            overflow: hidden;
            position: relative;
            color: white !important;
            text-decoration: none !important;
            border: 1px solid rgba(255,255,255,.13);
            border-radius: 20px;
            background: #11162a;
            box-shadow: 0 13px 34px rgba(17,22,42,.2);
            transition: transform .2s ease, box-shadow .2s ease;
        }

        .parent-brand-card::before {
            content: "";
            position: absolute;
            width: 230px;
            height: 230px;
            right: 13%;
            top: -150px;
            border: 30px solid rgba(109,93,252,.24);
            border-radius: 50%;
        }

        .parent-brand-card:hover {
            transform: translateY(-3px);
            box-shadow: 0 18px 42px rgba(17,22,42,.28);
        }
        .parent-brand-hit-area {
            position: absolute;
            z-index: 5;
            inset: 0;
            border-radius: inherit;
        }

        .brand-service-showcase {
            position: relative;
            flex: 1 1 auto;
            width: auto;
            min-width: 0;
            height: 62px;
            overflow: hidden;
            border: 0;
            background: transparent;
        }
        .brand-service-showcase::before,
        .brand-service-showcase::after {
            content: "";
            position: absolute;
            z-index: 3;
            top: 0;
            bottom: 0;
            width: 22px;
            pointer-events: none;
        }
        .brand-service-showcase::before {
            left: 0;
            background: linear-gradient(90deg, #11162a, transparent);
        }
        .brand-service-showcase::after {
            right: 0;
            background: linear-gradient(-90deg, #11162a, transparent);
        }
        .service-track {
            position: absolute;
            left: 100%;
            top: 0;
            display: flex;
            align-items: center;
            width: max-content;
            height: 100%;
            animation: services-move-left 16s linear infinite;
        }
        .service-cartoon {
            position: relative;
            flex: 0 0 86px;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            gap: 2px;
        }
        .service-character {
            font-size: 1.65rem;
            line-height: 1;
            filter: drop-shadow(0 4px 5px rgba(0,0,0,.18));
            animation: service-bob 1.25s ease-in-out infinite alternate;
        }
        .service-label {
            color: white;
            font-size: .52rem;
            font-weight: 800;
            letter-spacing: .04em;
            text-transform: uppercase;
        }
        .service-spark {
            position: absolute;
            width: 5px;
            height: 5px;
            border-radius: 50%;
            background: #ffbd3e;
            box-shadow: 61px 36px 0 #ff72aa, 55px -7px 0 #8ce9dc;
            animation: service-sparkle 1.4s ease-in-out infinite alternate;
        }
        @keyframes services-move-left {
            from { transform: translateX(0); }
            to { transform: translateX(calc(-100% - 70vw)); }
        }
        @keyframes service-bob { to { transform: translateY(-3px) rotate(2deg); } }
        @keyframes service-sparkle { to { opacity: .25; transform: scale(.55); } }

        .parent-brand-copy {
            position: relative;
            z-index: 1;
            flex: 0 0 auto;
        }
        .parent-brand-kicker {
            color: #8ce9dc !important;
            font-size: .68rem;
            font-weight: 800;
            letter-spacing: .13em;
            text-transform: uppercase;
        }
        .parent-brand-name {
            margin: .1rem 0 .16rem;
            color: white !important;
            font-size: 1.15rem;
            font-weight: 800;
            letter-spacing: -.02em;
        }
        .parent-brand-line {
            color: rgba(255,255,255,.68) !important;
            font-size: .82rem;
        }

        .voice-wave {
            display: flex;
            flex: 0 0 auto;
            align-items: center;
            gap: 4px;
            height: 34px;
            position: relative;
            z-index: 1;
        }
        .voice-wave i {
            display: block;
            width: 4px;
            height: 9px;
            border-radius: 999px;
            background: linear-gradient(#8ce9dc, #745fff);
            animation: voice-pulse 1s ease-in-out infinite alternate;
        }
        .voice-wave i:nth-child(2) { animation-delay: -.55s; }
        .voice-wave i:nth-child(3) { animation-delay: -.15s; }
        .voice-wave i:nth-child(4) { animation-delay: -.72s; }
        .voice-wave i:nth-child(5) { animation-delay: -.32s; }
        .voice-wave i:nth-child(6) { animation-delay: -.62s; }
        .voice-wave i:nth-child(7) { animation-delay: -.22s; }
        @keyframes voice-pulse { to { height: 31px; } }

        .parent-brand-cta {
            position: relative;
            z-index: 1;
            display: inline-flex;
            align-items: center;
            gap: .45rem;
            padding: .58rem .8rem;
            color: white !important;
            border: 1px solid rgba(255,255,255,.18);
            border-radius: 999px;
            background: rgba(255,255,255,.08);
            font-size: .75rem;
            font-weight: 750;
            white-space: nowrap;
            flex: 0 0 auto;
        }
        .parent-brand-card:hover .parent-brand-cta { background: rgba(255,255,255,.15); }

        .parent-brand-card.hn-network-card { width:100vw; min-height:clamp(330px,48vh,520px); margin:1rem 0 2.5rem calc(50% - 50vw); padding:clamp(2rem,5vw,5rem); gap:clamp(2rem,4vw,5rem); isolation:isolate; border-right:0; border-left:0; border-radius:0; background:radial-gradient(circle at 20% 30%,rgba(86,67,185,.24),transparent 30%),linear-gradient(120deg,#071326,#0c1029 55%,#111833); }
        .hn-network-card::before { width:420px; height:420px; right:-160px; top:-250px; border:1px solid rgba(103,239,217,.18); box-shadow:0 0 0 48px rgba(109,93,252,.045),0 0 0 96px rgba(19,184,166,.025); }
        .hn-network-card::after { content:""; position:absolute; inset:0; z-index:-1; opacity:.22; background-image:radial-gradient(rgba(140,233,220,.6) 1px,transparent 1px); background-size:24px 24px; mask-image:linear-gradient(90deg,transparent,#000 28%,#000 80%,transparent); }
        .hn-network-card .parent-brand-copy { flex:0 0 clamp(260px,25vw,390px); }
        .hn-network-card .parent-brand-kicker { font-size:clamp(.68rem,.9vw,.88rem); }
        .hn-network-card .parent-brand-name { max-width:390px; margin-top:.5rem; font-size:clamp(1.7rem,3vw,3.2rem); line-height:.98; letter-spacing:-.05em; }
        .hn-network-card .parent-brand-line { max-width:360px; margin-top:1rem; font-size:clamp(.72rem,1vw,.92rem); line-height:1.7; }
        .hn-signal-network { position:relative; z-index:2; flex:1 1 auto; align-self:stretch; min-width:560px; min-height:250px; }
        .hn-connection-map { position:absolute; inset:10px 0; width:100%; height:calc(100% - 20px); overflow:visible; }
        .hn-connection-map path { fill:none; stroke:#27d9c0; stroke-width:1.2; stroke-dasharray:7 8; opacity:.55; animation:hn-signal-flow 2.4s linear infinite; }
        .hn-connection-map circle { fill:#f26ce5; filter:drop-shadow(0 0 6px #f26ce5); animation:hn-pulse-dot 2s ease-in-out infinite; }
        @keyframes hn-signal-flow { to { stroke-dashoffset:-30; } }
        @keyframes hn-pulse-dot { 50% { opacity:.35; r:3; } }
        .hn-node { position:absolute; top:50%; display:flex; align-items:center; gap:.75rem; width:clamp(140px,12vw,190px); min-height:110px; padding:.85rem 1rem; color:white; border:1px solid rgba(51,224,200,.62); background:linear-gradient(145deg,rgba(32,42,86,.96),rgba(13,19,48,.96)); clip-path:polygon(14% 0,86% 0,100% 24%,100% 76%,86% 100%,14% 100%,0 76%,0 24%); box-shadow:inset 0 0 24px rgba(109,93,252,.12); transform:translateY(-50%); animation:hn-node-float 3s ease-in-out infinite alternate; }
        .hn-node.n1 { left:0; }.hn-node.n2 { left:27%; animation-delay:-1.1s; }.hn-node.n3 { left:54%; animation-delay:-2.1s; }.hn-node.n4 { right:0; animation-delay:-.55s; }
        @keyframes hn-node-float { to { translate:0 -6px; filter:drop-shadow(0 10px 12px rgba(0,0,0,.26)); } }
        .hn-node-icon { position:relative; display:grid; flex:0 0 52px; place-items:center; width:52px; height:62px; border-radius:18px 18px 22px 22px; color:#081426; background:linear-gradient(145deg,#8ce9dc,#846fff 72%,#f26ce5); box-shadow:0 0 0 5px rgba(140,233,220,.06),0 0 18px rgba(132,111,255,.38); font-size:1.25rem; font-weight:900; }
        .hn-node-icon::before { content:""; position:absolute; left:7px; right:7px; top:-6px; height:14px; border-radius:50%; background:inherit; opacity:.85; }
        .hn-node-copy { min-width:0; }.hn-node-copy b,.hn-node-copy span { display:block; }.hn-node-copy b { color:white; font-size:clamp(.64rem,.8vw,.82rem); line-height:1.15; }.hn-node-copy span { margin-top:.32rem; color:rgba(255,255,255,.6); font-size:clamp(.48rem,.62vw,.64rem); line-height:1.45; }
        .hn-live-signal { position:absolute; left:1%; right:1%; bottom:2px; display:flex; align-items:center; justify-content:center; gap:.42rem; color:#8ce9dc; font-size:.48rem; font-weight:850; letter-spacing:.11em; text-transform:uppercase; }
        .hn-live-signal i { width:6px; height:6px; border-radius:50%; background:#70f0d5; box-shadow:0 0 0 5px rgba(112,240,213,.1); animation:hn-live 1s ease-in-out infinite alternate; }
        @keyframes hn-live { to { opacity:.35; transform:scale(.7); } }
        .hn-network-card .parent-brand-cta { align-self:center; padding:.68rem .9rem; border-color:rgba(140,233,220,.28); background:rgba(140,233,220,.08); }
        .hn-network-card:hover .hn-node { border-color:#f26ce5; }

        .review-hero h1 {
            color: white;
            font-size: clamp(2rem, 4vw, 3.1rem);
            line-height: 1.05;
            margin: 0 0 0.55rem;
            letter-spacing: -0.04em;
        }

        .review-hero p {
            max-width: 720px;
            margin: 0;
            color: rgba(255, 255, 255, 0.86);
            font-size: 1.02rem;
        }

        h2, h3, h4 { color: var(--ink); letter-spacing: -0.025em; }
        h2 {
            position: relative;
            margin-top: 2rem !important;
            padding-bottom: 0.7rem;
        }
        h2::after {
            content: "";
            position: absolute;
            left: 0;
            bottom: 0;
            width: 3.2rem;
            height: 0.24rem;
            border-radius: 999px;
            background: linear-gradient(90deg, var(--brand), var(--accent));
        }

        div[data-testid="stVerticalBlockBorderWrapper"] {
            border-color: var(--border);
            border-radius: 18px;
            background: #ffffff;
            box-shadow: 0 8px 28px rgba(31, 42, 68, 0.06);
            transition: transform 0.2s ease, box-shadow 0.2s ease, border-color 0.2s ease;
        }

        div[data-testid="stVerticalBlockBorderWrapper"]:hover {
            transform: translateY(-2px);
            border-color: rgba(109, 93, 252, 0.3);
            box-shadow: 0 14px 36px rgba(31, 42, 68, 0.1);
        }

        div[data-testid="stMetric"] {
            padding: 1rem 1.15rem;
            border: 1px solid var(--border);
            border-radius: 18px;
            background: #ffffff;
            box-shadow: 0 8px 24px rgba(31, 42, 68, 0.07);
            transition: transform 0.18s ease, box-shadow 0.18s ease;
        }

        div[data-testid="stMetric"]:hover {
            transform: translateY(-3px);
            box-shadow: 0 14px 30px rgba(31, 42, 68, 0.11);
        }

        .stButton > button, .stDownloadButton > button {
            border-radius: 12px;
            border: 1px solid rgba(109, 93, 252, 0.28);
            min-height: 2.8rem;
            font-weight: 650;
            transition: transform 0.16s ease, box-shadow 0.16s ease, border-color 0.16s ease;
        }

        .stButton > button:hover, .stDownloadButton > button:hover {
            transform: translateY(-2px);
            border-color: var(--brand);
            box-shadow: 0 9px 20px rgba(109, 93, 252, 0.18);
        }

        .stButton > button[kind="primary"] {
            color: white;
            border: 0;
            background: linear-gradient(115deg, var(--brand), var(--brand-dark));
            box-shadow: 0 8px 18px rgba(109, 93, 252, 0.25);
        }

        .stDownloadButton > button {
            width: 100%;
            color: var(--brand-dark);
            background: linear-gradient(135deg, #ffffff, #f1efff);
        }

        div[data-baseweb="select"] > div,
        .stTextInput input,
        .stTextArea textarea {
            border-radius: 12px !important;
            border-color: rgba(100, 116, 139, 0.22) !important;
            background: rgba(255, 255, 255, 0.92) !important;
        }

        .stTextInput input:disabled {
            color: #334155 !important;
            -webkit-text-fill-color: #334155 !important;
            opacity: 1 !important;
            background: #f1f4f9 !important;
        }

        div[data-baseweb="select"] > div:focus-within,
        .stTextInput input:focus,
        .stTextArea textarea:focus {
            border-color: var(--brand) !important;
            box-shadow: 0 0 0 3px rgba(109, 93, 252, 0.12) !important;
        }

        div[data-testid="stFileUploaderDropzone"] {
            border-radius: 18px;
            border: 1.5px dashed rgba(109, 93, 252, 0.42);
            background: linear-gradient(135deg, rgba(109, 93, 252, 0.06), rgba(19, 184, 166, 0.05));
            transition: transform 0.18s ease, border-color 0.18s ease;
        }

        div[data-testid="stFileUploaderDropzone"]:hover {
            transform: translateY(-2px);
            border-color: var(--brand);
        }

        div[data-testid="stDataFrame"] {
            overflow: hidden;
            border: 1px solid var(--border);
            border-radius: 16px;
            box-shadow: 0 7px 24px rgba(31, 42, 68, 0.06);
            background: #ffffff;
        }

        div[data-testid="stAlert"] { border-radius: 14px; }

        div[data-testid="stRadio"] label,
        div[data-testid="stMultiSelect"] span {
            transition: color 0.15s ease, transform 0.15s ease;
        }

        div[data-testid="stRadio"] label:hover {
            color: var(--brand-dark);
            transform: translateX(2px);
        }

        div[data-testid="stProgress"] > div > div > div {
            background: linear-gradient(90deg, var(--brand), var(--accent));
        }

        div[data-testid="stPills"] button {
            border-radius: 999px !important;
            min-width: 2.3rem;
            font-weight: 700;
            border: 1px solid rgba(109, 93, 252, 0.2) !important;
            background: linear-gradient(180deg, #fff, #f6f5ff) !important;
        }

        div[data-testid="stPills"] button[aria-pressed="true"] {
            color: white !important;
            border-color: transparent !important;
            background: linear-gradient(135deg, var(--brand), var(--brand-dark)) !important;
            box-shadow: 0 7px 16px rgba(109, 93, 252, 0.3);
        }

        /* Each individual review criterion is a separate colored paper sheet. */
        div[class*="st-key-criterion_sheet_"] div[data-testid="stVerticalBlockBorderWrapper"] {
            position: relative;
            overflow: visible;
            margin: .35rem 0 .8rem;
            padding: .85rem 1rem .55rem 1.15rem;
            border: 1px solid rgba(45, 57, 72, 0.2) !important;
            border-radius: 4px 14px 6px 11px !important;
            box-shadow: 0 9px 18px rgba(31, 42, 68, 0.11), 0 2px 3px rgba(31, 42, 68, 0.07);
            background-color: var(--criteria-paper, #dff1f5) !important;
            background-image:
                linear-gradient(90deg, transparent 0 1.65rem, rgba(211, 91, 91, 0.13) 1.65rem 1.72rem, transparent 1.72rem),
                repeating-linear-gradient(0deg, transparent 0 28px, rgba(57, 76, 96, 0.07) 28px 29px) !important;
            transform: rotate(var(--criteria-tilt, -0.2deg));
            transition: transform 0.2s ease, box-shadow 0.2s ease;
        }

        div[class*="st-key-criterion_sheet_"] div[data-testid="stVerticalBlockBorderWrapper"]::before {
            content: "";
            position: absolute;
            left: .45rem;
            top: .72rem;
            width: 7px;
            height: 7px;
            border-radius: 50%;
            background: rgba(255,255,255,.78);
            border: 1px solid rgba(50,64,80,.18);
            box-shadow: 0 31px 0 rgba(255,255,255,.72), 0 62px 0 rgba(255,255,255,.66);
        }

        div[class*="st-key-criterion_sheet_"] div[data-testid="stVerticalBlockBorderWrapper"]::after {
            content: "";
            position: absolute;
            z-index: 2;
            right: -1px;
            bottom: -1px;
            width: 28px;
            height: 28px;
            pointer-events: none;
            clip-path: polygon(100% 0, 0 100%, 100% 100%);
            background: linear-gradient(135deg, rgba(255,255,255,.74), rgba(89,102,120,.14));
            filter: drop-shadow(-2px -2px 2px rgba(31,42,68,.08));
        }

        div[class*="st-key-criterion_sheet_"] div[data-testid="stVerticalBlockBorderWrapper"]:hover {
            z-index: 3;
            transform: rotate(0deg) translateY(-3px);
            box-shadow: 0 14px 25px rgba(31, 42, 68, 0.16), 0 3px 5px rgba(31, 42, 68, 0.09);
        }

        div[class*="st-key-criterion_sheet_0_"] { --criteria-paper:#dff1f5; --criteria-tilt:-0.25deg; }
        div[class*="st-key-criterion_sheet_1_"] { --criteria-paper:#f8ddd7; --criteria-tilt:0.25deg; }
        div[class*="st-key-criterion_sheet_2_"] { --criteria-paper:#dff2e8; --criteria-tilt:-0.18deg; }
        div[class*="st-key-criterion_sheet_3_"] { --criteria-paper:#f8efc9; --criteria-tilt:0.2deg; }
        div[class*="st-key-criterion_sheet_4_"] { --criteria-paper:#e8e1f6; --criteria-tilt:-0.22deg; }
        div[class*="st-key-criterion_sheet_5_"] { --criteria-paper:#f5dfc9; --criteria-tilt:0.22deg; }
        div[class*="st-key-criterion_sheet_6_"] { --criteria-paper:#dce9f8; --criteria-tilt:-0.16deg; }
        div[class*="st-key-criterion_sheet_7_"] { --criteria-paper:#f3dfea; --criteria-tilt:0.18deg; }

        ::-webkit-scrollbar { width: 10px; height: 10px; }
        ::-webkit-scrollbar-track { background: #eef1f7; }
        ::-webkit-scrollbar-thumb {
            border: 2px solid #eef1f7;
            border-radius: 999px;
            background: linear-gradient(var(--brand), var(--accent));
        }

        @media (prefers-reduced-motion: reduce) {
            *, *::before, *::after {
                animation-duration: 0.01ms !important;
                animation-iteration-count: 1 !important;
                transition-duration: 0.01ms !important;
            }
        }

        @media (max-width: 760px) {
            .block-container { padding-left: 1rem; padding-right: 1rem; }
            div[class*="st-key-criterion_sheet_"] div[data-testid="stVerticalBlockBorderWrapper"] { transform:none; }
            div[data-testid="stMarkdownContainer"]:has(> .inner-site-header) { min-height:142px; }
            .inner-site-header { position:relative !important; left:auto; right:auto; top:auto; display:block !important; width:100%; max-width:100%; height:auto; min-height:132px; margin:.35rem 0 1rem !important; padding:.45rem !important; overflow:hidden; border:1px solid rgba(21,31,36,.08); border-radius:20px; background:rgba(255,255,255,.97); box-shadow:0 12px 30px rgba(21,31,36,.1); }
            .inner-site-header::before { display:none; }
            .inner-site-header > .news-top { position:relative !important; inset:auto !important; display:flex !important; flex-wrap:wrap !important; width:100%; min-width:0; min-height:0; padding:0 !important; opacity:1 !important; pointer-events:auto !important; transform:none !important; border:0; background:transparent; box-shadow:none; }
            .inner-site-header .news-nav { display:flex !important; flex:0 0 100%; width:100%; min-width:0; order:3; overflow-x:auto; }
            .inner-site-header .news-actions { margin-left:auto; }
            .inner-site-header .nav-account-dropdown { position:fixed; z-index:1200; right:1rem; top:5rem; }
            .stButton > button { color:#151f24 !important; background:#ffffff !important; -webkit-text-fill-color:#151f24 !important; }
            .stButton > button p,.stButton > button span { color:inherit !important; -webkit-text-fill-color:inherit !important; }
            .stButton > button[kind="primary"] { color:#ffffff !important; background:linear-gradient(135deg,#6d5dfc,#5145cd) !important; -webkit-text-fill-color:#ffffff !important; }
            .stButton > button:disabled { color:#687377 !important; background:#eef1f2 !important; opacity:.72; -webkit-text-fill-color:#687377 !important; }
            .projects-hero { margin:.5rem auto 1rem; padding:1.5rem; border-radius:22px; }
            .stApp:has(.workspace-page-marker) { background-position:68% top; background-size:auto 100vh; background-attachment:scroll; }
            .block-container:has(.mapping-page-marker) { width:calc(100% - 1rem); margin:4.5rem .5rem 2rem; padding:1rem; border-radius:22px; }
            .mapping-workbench-intro { padding:4.8rem 1rem 1.2rem; }.mapping-workbench-intro::before { left:1rem; top:1rem; }
            .workspace-intro { min-height:0; padding:1.6rem 1.25rem; border-radius:22px; }
            .workspace-intro::before,.workspace-intro::after { display:none; }
            .workspace-intro h1 { font-size:2.35rem; }
            .workspace-flow { gap:.4rem; }.workspace-flow span { font-size:.56rem; }
            .st-key-feature_stage,.st-key-upload_stage { width:100%; min-height:0; padding:1rem; border-radius:20px; background:rgba(255,253,248,.97); }
            .st-key-feature_stage { margin:16rem auto 0; }.st-key-upload_stage { margin:2rem auto 0; }
            .empty-review-state { width:100%; margin:1rem 0 0; }
            .upload-section-head { align-items:flex-start; flex-direction:column; }
            .st-key-feature_stage .upload-section-head { align-items:center; width:100%; padding:1.2rem 3.8rem 1.3rem 1rem; }
            .st-key-feature_stage .upload-section-head::after { right:.55rem; width:58px; }
            .st-key-review_feature_choice > div[role="radiogroup"] { grid-template-columns:1fr; }
            .review-product-grid { grid-template-columns:1fr; }.review-product-card { min-height:360px; }
            .review-hero { padding: 1.35rem; border-radius: 18px; }
            .creative-shape { display: none; }
            .parent-brand-card { display: flex; }
            .parent-brand-card.hn-network-card { align-items:flex-start; flex-direction:column; min-height:350px; padding:1.1rem; }
            .hn-network-card .parent-brand-copy { flex:0 0 auto; }.hn-signal-network { flex:0 0 155px; width:100%; min-width:0; }
            .hn-node { width:128px; }.hn-node.n2,.hn-node.n4 { display:none; }.hn-node.n1 { left:2%; }.hn-node.n3 { left:auto; right:2%; }
            .hn-network-card .parent-brand-cta { position:absolute; right:1rem; top:1rem; }
            .voice-wave { display: none; }
            .brand-service-showcase { display: none; }
            .parent-brand-cta { padding: .5rem; font-size: 0; }
            .parent-brand-cta span { font-size: 1rem; }
            .landing-hero { display:block; min-height:0; padding:2rem 1.3rem; }
            .landing-title { font-size:2.75rem; }
            .product-stage { min-height:350px; margin-top:2rem; }
            .product-window { inset:15px 0 5px; transform:none; }
            .landing-proof { flex-wrap:wrap; }
            .landing-page-nav { position:relative; left:auto; right:auto; top:auto; margin-bottom:1.5rem; }
            .landing-nav-brand { display:none; }
            .landing-nav-links { width:100%; justify-content:center; flex-wrap:wrap; }
            .about-grid, .about-steps { grid-template-columns:1fr; }
            .about-hero,.about-manifesto { grid-template-columns:1fr; }
            .about-hero { min-height:0; padding:4rem 1.25rem; }
            .about-human-loop { min-height:340px; }
            .about-loop-ring { width:260px; height:260px; }
            .about-section-heading { align-items:flex-start; flex-direction:column; }
            .domain-story-head,.domain-subjects,.alignment-usecases { grid-template-columns:1fr; }
            .resource-grid { grid-template-columns:1fr; }
            .rating-guide { grid-template-columns:1fr; }
            .alignment-usecase { border-right:0; border-bottom:1px solid rgba(21,31,36,.1); }
            .about-actions { align-items:flex-start; flex-direction:column; }
            .about-action-links { width:100%; flex-wrap:wrap; }
            .auth-story { padding:.5rem 0 1.5rem; text-align:center; }
            .auth-story h1 { font-size:2.8rem; }
            .auth-benefits { justify-content:center; }
            .auth-proof-row { grid-template-columns:1fr; }
            .account-story { padding:2rem .25rem 1rem; text-align:center; }
            .block-container:has(.auth-page-marker) { background-position:center top; background-size:auto 100vh; background-attachment:scroll; }
            .account-story { padding:1.5rem; background:rgba(7,28,48,.84); }
            .st-key-account_page_shell { width:100%; height:760px; aspect-ratio:auto; min-height:0; padding:0; border-radius:22px; }
            .st-key-account_page_shell { background-position:68% center !important; }
            .st-key-account_auth_panel { left:50%; top:7%; width:calc(100% - 2rem); max-width:430px; margin:0; padding:1.1rem; transform:translateX(-50%); background:rgba(255,255,255,.96) !important; }
            .account-story > p { margin-left:auto; margin-right:auto; }
            .account-trust-grid { grid-template-columns:1fr; text-align:left; }
            .account-signal-line { justify-content:center; }
            .login-cockpit { min-height:690px; border-radius:22px; }
            .evaluation-tunnel { width:280px; height:280px; }
            .cockpit-title { width:88%; }
            .cockpit-response { width:135px; padding:.7rem; }
            .cockpit-response.a { left:3%; top:24%; }.cockpit-response.b { right:3%; top:30%; }.cockpit-response.c { left:8%; bottom:16%; }
            .cockpit-signal.context { left:3%; top:12%; }.cockpit-signal.language { right:3%; top:16%; }.cockpit-signal.emotion { right:3%; bottom:13%; }.cockpit-signal.safety { left:27%; bottom:5%; }
            .stApp:has(.auth-page-marker) .st-key-account_login_zone { min-height:calc(100vh - 180px); padding:2rem .25rem; }
            .site-footer { align-items:flex-start; flex-direction:column; }
            .mira-wordmark small { display:none; }
            .mira-story-nav { gap:.55rem; }
            .mira-story-nav a { font-size:.6rem; }
            .mira-story,.mira-news-header,.news-top { width:100%; max-width:100%; min-width:0; }
            .mira-story { overflow:hidden; }
            .mira-news-header { padding:8px; }
            .news-top { display:flex; flex-wrap:wrap; min-height:0; gap:.55rem; }
            .news-brand { padding:.62rem .75rem; font-size:1rem; }
            .news-brand-mark { width:30px; transform:scale(.85); transform-origin:left center; }
            .news-nav { flex:0 0 100%; width:100%; min-width:0; justify-content:flex-start; order:3; overflow-x:auto; }
            .news-nav a { padding:.62rem .72rem; font-size:.66rem; }
            .news-actions { margin-left:auto; }
            .news-actions > a { display:inline-flex; padding:.55rem .72rem; font-size:.64rem; }
            .news-actions a.primary { display:inline-flex; padding:.55rem .72rem; font-size:.64rem; }
            .news-actions a.primary i { width:21px; height:21px; }
            .depth-collage-hero { min-height:760px; background-position:61% top; }
            .depth-hero-copy { left:7%; top:6%; width:76%; }
            .depth-hero-copy p { margin-top:1rem; }
            .depth-scroll { left:14%; top:63%; }
            .depth-tag.context,.depth-tag.tone { display:none; }
            .mira-quick-pitch { grid-template-columns:1fr; }
            .bento-head { align-items:flex-start; flex-direction:column; }
            .bento-grid { display:block; }
            .bento-card { margin-bottom:1rem; }
            .bento-card.wide { min-height:520px; }
            .depth-card { display:none; }
            .story-intro { grid-template-columns:1fr; }
            .response-xray { min-height:390px; margin-top:.5rem; }
            .xray-card { width:82%; min-height:185px; padding:1.1rem; }
            .story-proof { gap:.4rem; }
            .story-proof span { font-size:.58rem; }
            .evaluation-collage { padding:1.2rem; border-radius:20px; }
            .collage-copy { grid-template-columns:1fr; gap:1rem; margin-bottom:1.4rem; }
            .collage-visual { min-height:480px; background-position:54% center; }
            .collage-note { font-size:.54rem; }
            .collage-note.intent { left:5%; top:8%; }.collage-note.compare { right:5%; top:12%; }.collage-note.decide { right:6%; bottom:14%; }
            .evaluation-collage::before,.evaluation-collage::after { display:none; }
            .signal-stage { min-height:690px; }
            .signal-prompt { top:50%; width:78%; }
            .signal-beam { display:none; }
            .signal-layer { width:74%; padding:.8rem; }
            .signal-layer.a { left:5%; top:4%; }.signal-layer.b { right:5%; top:20%; }.signal-layer.c { left:5%; bottom:20%; }.signal-layer.d { right:5%; bottom:4%; }
            .signal-ticker { bottom:8px; }
            .story-numbers,.process-line { grid-template-columns:1fr; }
            .story-number { border-right:0; }
            .blindspot-story { grid-template-columns:1fr; }
            .decision-anatomy { min-height:520px; }
            .decision-subject { width:145px; }
            .decision-subject.one { left:0; }.decision-subject.two { right:0; }.decision-subject.three { left:3%; }
            .dashboard-banner { grid-template-columns:1fr; padding:1.5rem; }
            .dashboard-banner p { display:none; }
            .dashboard-illustration { display:none; }
            .project-grid { grid-template-columns:1fr; }
            .landing-dashboard { padding:.8rem; }
        }

        @media (max-width: 1050px) and (min-width: 761px) {
            .landing-hero { grid-template-columns: .85fr 1.15fr; padding:2.5rem; gap:1.5rem; }
            .landing-title { font-size:3.2rem; }
            .product-body { grid-template-columns:82px 1fr; }
        }

        @media (max-width: 1180px) {
            .creative-shape { opacity: 0.045; }
        }
        </style>
        <div class="creative-backdrop" aria-hidden="true">
            <span class="creative-shape shape-ring-purple"></span>
            <span class="creative-shape shape-square-yellow"></span>
            <span class="creative-shape shape-pill-pink"></span>
            <span class="creative-shape shape-triangle-teal"></span>
            <span class="creative-shape shape-cross-purple"></span>
        </div>
        """
    render_safe_html(_embed_theme_assets(theme_markup))


def render_page_header(evaluation_started: bool) -> None:
    """Render a contextual hero for setup and evaluation modes."""
    if evaluation_started:
        return

    auth_ready = google_auth_configured()
    signed_in = auth_ready and bool(getattr(st.user, "is_logged_in", False))
    review_href = "/review" if signed_in else "/account"
    if signed_in:
        nav_user_name = escape(str(getattr(st.user, "name", None) or "Google user"))
        nav_user_email = escape(str(getattr(st.user, "email", None) or ""))
        nav_user_initial = (nav_user_name.strip()[:1] or nav_user_email.strip()[:1] or "G").upper()
        account_navigation = f"""<div class="nav-account-menu"><a class="nav-user-avatar" href="/account" target="_self" aria-label="Open account menu">{nav_user_initial}</a><div class="nav-account-dropdown"><div class="nav-account-identity"><strong>{nav_user_name}</strong><span>{nav_user_email}</span></div><a href="/account" target="_self">Account settings</a><a class="sign-out" href="/logout" target="_self">Sign out</a></div></div>"""
    else:
        account_navigation = '<a href="/account" target="_self">Account</a>'

    landing_markup = dedent(
        f"""
        <main class="mira-story">
            <header class="mira-news-header">
                <div class="news-top">
                    <a class="news-brand" href="/" target="_self" aria-label="MIRA home"><span class="news-brand-mark" aria-hidden="true"><i></i><i></i><i></i></span><span>MIRA</span></a>
                    <nav class="news-nav" aria-label="Primary navigation">
                        <a class="active" href="/" target="_self"><i class="nav-icon">⌂</i>Home</a>
                        <a href="/about" target="_self"><i class="nav-icon">◉</i>About</a>
                        <a href="https://www.hyperneuronai.com/" target="_self"><i class="nav-icon">◇</i>Parent Website</a>
                        <a href="{review_href}" target="_self"><i class="nav-icon">→</i>Review Workspace</a>
                        {f'<a href="/projects" target="_self"><i class="nav-icon">▦</i>Projects</a>' if signed_in else ''}
                    </nav>
                    <div class="news-actions">{account_navigation}</div>
                </div>
            </header>
            <section class="depth-collage-hero">
                <div class="evaluation-particles" aria-hidden="true"><i class="particle-swarm one"></i><i class="particle-swarm two"></i></div>
                <div class="depth-hero-copy"><h1>The hidden depths of model evaluation</h1><p>A fluent response is only the visible surface. Beneath it lies context, language, relevance, safety and the human judgment that makes AI trustworthy.</p></div>
                <div class="depth-scroll">Scroll to evaluate deeper</div>
                <div class="depth-tag context">context</div><div class="depth-tag tone">language + tone</div><div class="depth-tag safety">safety</div><div class="depth-tag relevance">relevance</div>
            </section>
            <section class="mira-quick-pitch">
                <h2 class="quick-pitch-title">One row. Multiple responses. <span>Human signal in minutes.</span></h2>
                <div class="quick-pitch-copy"><p>Replace scattered spreadsheets with one evaluation space that keeps prompts, model outputs and human decisions connected.</p><div class="pitch-actions"><a class="pitch-link" href="#capabilities">Explore capabilities</a><a class="pitch-link primary" href="{review_href}"><i>→</i> Start evaluation</a></div></div>
            </section>
            <section id="evaluation-depth" class="story-section story-intro">
                <div class="story-intro-copy"><div class="story-index">01 · Beneath the output</div><h2>Fluent is not the same as <em>right.</em></h2><p class="story-copy">A response can read beautifully and still miss intent, context or cultural nuance. MIRA separates the visible answer from the signals underneath, so reviewers can turn instinct into structured evidence.</p><div class="story-proof"><span>Compare responses</span><span>Expose hidden signals</span><span>Capture human judgment</span></div></div>
                <div class="response-xray" aria-hidden="true">
                    <div class="xray-orbit"></div>
                    <div class="xray-card back"><small>Layer 03 · Decision</small>Which response genuinely serves the user?</div>
                    <div class="xray-card middle"><small>Layer 02 · Human signal</small>Intent, language, relevance and safety become reviewable evidence.</div>
                    <div class="xray-card front"><small>Layer 01 · Visible response</small><div class="xray-line medium"></div><div class="xray-line"></div><div class="xray-line short"></div><div class="xray-score"><span>Reveal evaluation depth</span><b><i></i><i></i><i></i><i></i></b></div></div>
                </div>
            </section>
            <section id="signals" class="story-section" style="padding-top:0;background:#e2f0f2;">
                <div class="evaluation-collage">
                    <div class="collage-copy"><div><small>Human review makes quality visible</small><h2>Look past the polished answer.</h2></div><p>Two responses can sound equally fluent while carrying very different levels of intent, relevance and risk. MIRA gives reviewers a place to inspect the evidence, compare alternatives and preserve the judgment behind every final choice.</p></div>
                    <div class="collage-visual" role="img" aria-label="Editorial collage of a human reviewer comparing AI model responses">
                        <span class="collage-note intent">inspect intent</span><span class="collage-note compare">compare evidence</span><span class="collage-note decide">record the decision</span>
                    </div>
                </div>
            </section>
            <section id="capabilities" class="mira-bento">
                <div class="bento-head"><h2>Everything a reviewer needs. Nothing they don’t.</h2><p>MIRA keeps the interface focused while preserving the depth required for serious model evaluation.</p></div>
                <div class="bento-grid">
                    <article class="bento-card wide"><h3>Compare every response in context</h3><p>See multiple model outputs together, select the strongest answer and preserve an editable final response.</p><div class="bento-response-stack"><div class="bento-response"><b>Response A</b>Clear intent, relevant context, natural language.</div><div class="bento-response"><b>Response B · Selected</b>Stronger alignment with the user’s actual request.</div><div class="bento-response"><b>Final response</b>Reviewer-refined and ready for export.</div></div></article>
                    <article class="bento-card"><h3>Configurable human signals</h3><p>Apply the review dimensions selected for the current evaluation project.</p><div class="rating-orbit"><i>•</i><i>•</i><i>•</i><i>•</i><i>•</i></div></article>
                    <article class="bento-card"><h3>Export-ready evidence</h3><p>Move from reviewed rows to clean data without rebuilding your work.</p><div class="export-flow"><span>Reviewed rows</span><i>→</i><span>CSV · XLSX</span></div></article>
                </div>
            </section>
            <section class="story-section story-closing">
                <div class="story-index">MIRA · Built for human signal</div>
                <h2>Make the invisible quality of a response visible.</h2>
                <a class="story-cta" href="{review_href}">Enter the Review Workspace →</a>
            </section>
        </main>
        """
    ).strip()
    # Streamlit's Markdown parser can interpret indented HTML as a code block on
    # some mobile browsers. A compact string keeps the landing page valid HTML.
    landing_markup = "".join(line.strip() for line in landing_markup.splitlines())
    render_safe_html(landing_markup)


def render_parent_brand_portal() -> None:
    """Render a compact, clickable parent-company brand experience."""
    render_safe_html(
        """
        <div class="parent-brand-card hn-network-card">
            <div class="parent-brand-copy">
                <div class="parent-brand-kicker">A HyperNeuron AI workspace</div>
                <div class="parent-brand-name">Intelligence that speaks Bharat</div>
                <div class="parent-brand-line">Human insight connected to multilingual models, voice and evaluation.</div>
            </div>
            <div class="hn-signal-network" aria-hidden="true">
                <svg class="hn-connection-map" viewBox="0 0 640 130" preserveAspectRatio="none">
                    <path d="M55 66 C125 15 145 116 218 66 S340 15 410 66 S525 116 590 66" />
                    <circle cx="145" cy="66" r="5"/><circle cx="345" cy="66" r="5"/><circle cx="525" cy="66" r="5"/>
                </svg>
                <div class="hn-node n1"><div class="hn-node-icon">अ</div><div class="hn-node-copy"><b>22+ Languages</b><span>India-first linguistic intelligence</span></div></div>
                <div class="hn-node n2"><div class="hn-node-icon">◈</div><div class="hn-node-copy"><b>Model Output</b><span>Business LLM response signals</span></div></div>
                <div class="hn-node n3"><div class="hn-node-icon">✓</div><div class="hn-node-copy"><b>Human Review</b><span>Context, language and quality</span></div></div>
                <div class="hn-node n4"><div class="hn-node-icon">≡</div><div class="hn-node-copy"><b>Voice AI</b><span>Natural speech and expression</span></div></div>
                <div class="hn-live-signal"><i></i> Live evaluation signal network</div>
            </div>
            <div class="parent-brand-cta">Explore HyperNeuron <span>↗</span></div>
            <a class="parent-brand-hit-area" href="https://www.hyperneuronai.com/"
               target="_blank" rel="noopener noreferrer" aria-label="Visit HyperNeuron AI"></a>
        </div>
        """
    )


def display_text(value) -> str:
    """Render empty pandas cells as blank text instead of 'nan'."""
    if pd.isna(value):
        return ""
    return str(value)


def rating_from_scale(value) -> Optional[int]:
    """Return a valid numeric 1–5 rating from the scale widget."""
    if value is None or value == "":
        return None
    rating = int(value)
    return rating if 1 <= rating <= 5 else None


def dynamic_rating_column(source_column, rating_column: str) -> str:
    """Build a rating output column tied to one selected source column."""
    return f"{source_column}_{rating_column}"


def ensure_dynamic_rating_columns(df: pd.DataFrame, source_columns: list) -> pd.DataFrame:
    """Add numeric rating columns for every criteria-enabled source column."""
    for source_column in source_columns:
        for rating_column in RATING_COLUMNS:
            output_column = dynamic_rating_column(source_column, rating_column)
            if output_column not in df.columns:
                df[output_column] = pd.Series(pd.NA, index=df.index, dtype="Int64")
            else:
                df[output_column] = pd.to_numeric(
                    df[output_column], errors="coerce"
                ).astype("Int64")
    return df


def load_dataframe(uploaded_file) -> pd.DataFrame:
    """Load CSV/XLS/XLSX into a pandas DataFrame."""
    filename = uploaded_file.name.lower()

    # Read file into memory first so Streamlit's UploadedFile can be re-used
    data = uploaded_file.read()
    bio = BytesIO(data)

    if filename.endswith(".csv"):
        return pd.read_csv(bio)

    # For Excel use pandas + openpyxl for xlsx.
    # pandas will choose appropriate engine for xls/xlsx.
    return pd.read_excel(bio)


def fetch_google_drive_file(shared_url: str) -> MemoryUpload:
    """Download a public/shared Google Drive file used by a Colab workflow."""
    try:
        import gdown
    except ImportError as exc:
        raise RuntimeError("Google Drive support requires the `gdown` package.") from exc

    with tempfile.TemporaryDirectory() as temp_dir:
        downloaded_path = gdown.download(
            url=shared_url,
            output=f"{temp_dir}/",
            quiet=True,
            fuzzy=True,
        )
        if not downloaded_path:
            raise ValueError(
                "Could not download the file. Ensure the Drive link is shared with anyone who has the link."
            )

        path = Path(downloaded_path)
        if path.suffix.lower() not in {".csv", ".xlsx", ".xls"}:
            raise ValueError("Google Drive file must be a CSV, XLSX, or XLS file.")
        return MemoryUpload(path.read_bytes(), path.name)


def ensure_review_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Add review columns and keep text and numeric ratings in suitable dtypes."""
    deprecated_overall_columns = [
        column for column in df.columns if str(column).endswith("_overall_rating")
    ]
    if deprecated_overall_columns:
        df = df.drop(columns=deprecated_overall_columns)
    for col in REVIEW_COLUMNS:
        if col in RATING_COLUMNS:
            if col not in df.columns:
                df[col] = pd.Series(pd.NA, index=df.index, dtype="Int64")
            else:
                df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")
            continue
        if col not in df.columns:
            df[col] = ""
        else:
            df[col] = df[col].map(display_text)
        df[col] = df[col].astype("object")
    return df


def clear_review_widget_state() -> None:
    """Clear per-row review widget state when a new upload is loaded."""
    prefixes = (
        "choice_",
        "notes_",
        "final_",
        "context_",
        "emotionx_",
        "language_",
        "safety_",
        "select_response_col_",
        "response_display_name_",
        "column_display_name_",
        "uploaded_column_",
        "criteria_rating_",
        "criteria_scale_",
    )
    for key in list(st.session_state.keys()):
        if key.startswith(prefixes):
            del st.session_state[key]
    for key in (
        "select_prompt_col",
        "select_category_col",
        "criteria_target_columns_widget",
    ):
        st.session_state.pop(key, None)
    st.session_state.response_column_count = 2
    st.session_state.response_columns = []
    st.session_state.evaluation_column_slots = []
    st.session_state.evaluation_column_defaults = {}
    st.session_state.response_display_names = {}
    st.session_state.column_display_names = {}
    st.session_state.criteria_target_columns = []
    st.session_state.columns_confirmed = False
    st.session_state.column_mapping_version = COLUMN_MAPPING_VERSION
    st.session_state.pop("jump_to_row", None)
    st.session_state.pop("pending_row_navigation", None)


def user_state_directory() -> Path:
    """Return the private state root for the current signed-in reviewer."""
    identity = str(getattr(st.user, "email", None) or "local-reviewer").strip().lower()
    user_key = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]
    directory = Path.cwd() / ".mira_state" / user_key
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def project_id_for(source_name: str, source_size: int) -> str:
    identity = f"{source_name.strip().lower()}::{int(source_size)}"
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]


def project_directory(project_id: str) -> Path:
    directory = user_state_directory() / "projects" / project_id
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def active_dataset_directory() -> Path:
    """Return the active project's directory, including legacy-state support."""
    root = user_state_directory()
    pointer = root / "active_project.txt"
    if pointer.exists():
        project_id = pointer.read_text(encoding="utf-8").strip()
        if project_id:
            return project_directory(project_id)
    return root


def persist_active_dataset(
    original_df: pd.DataFrame,
    review_df: pd.DataFrame,
    source_name: str,
    source_size: int,
) -> None:
    """Persist the active upload so a browser refresh can restore its mapping page."""
    project_id = project_id_for(source_name, source_size)
    directory = project_directory(project_id)
    original_tmp = directory / "original.tmp.pkl.gz"
    review_tmp = directory / "review.tmp.pkl.gz"
    metadata_tmp = directory / "metadata.tmp.json"
    original_df.to_pickle(original_tmp, compression="gzip")
    review_df.to_pickle(review_tmp, compression="gzip")
    metadata = {
        "project_id": project_id,
        "source_name": source_name,
        "source_size": int(source_size),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "current_index": int(st.session_state.get("current_index", 0)),
        "col_prompt": st.session_state.get("col_prompt"),
        "response_columns": st.session_state.get("response_columns", []),
        "response_display_names": st.session_state.get("response_display_names", {}),
        "column_display_names": st.session_state.get("column_display_names", {}),
        "criteria_target_columns": st.session_state.get("criteria_target_columns", []),
        "columns_confirmed": bool(st.session_state.get("columns_confirmed", False)),
        "evaluation_column_slots": st.session_state.get("evaluation_column_slots", []),
        "evaluation_column_defaults": st.session_state.get("evaluation_column_defaults", {}),
    }
    metadata_tmp.write_text(json.dumps(metadata, default=str), encoding="utf-8")
    original_tmp.replace(directory / "original.pkl.gz")
    review_tmp.replace(directory / "review.pkl.gz")
    metadata_tmp.replace(directory / "metadata.json")
    (user_state_directory() / "active_project.txt").write_text(project_id, encoding="utf-8")


def list_review_projects() -> list[dict]:
    """Return saved project summaries for the signed-in reviewer."""
    projects = []
    projects_root = user_state_directory() / "projects"
    if not projects_root.exists():
        return projects
    for metadata_path in projects_root.glob("*/metadata.json"):
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            review_df = pd.read_pickle(metadata_path.parent / "review.pkl.gz", compression="gzip")
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            continue
        reviewed, total, pct = compute_progress(ensure_review_columns(review_df)["reviewed_status"])
        metadata.update({"reviewed": reviewed, "total": total, "progress": pct})
        metadata["project_id"] = metadata.get("project_id") or metadata_path.parent.name
        projects.append(metadata)
    return sorted(projects, key=lambda item: item.get("updated_at", ""), reverse=True)


def restore_project(project_id: str) -> bool:
    """Restore a selected saved project and make it the active review."""
    directory = project_directory(project_id)
    original_path = directory / "original.pkl.gz"
    review_path = directory / "review.pkl.gz"
    metadata_path = directory / "metadata.json"
    if not all(path.exists() for path in (original_path, review_path, metadata_path)):
        return False
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        original_df = pd.read_pickle(original_path, compression="gzip")
        review_df = pd.read_pickle(review_path, compression="gzip")
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return False
    clear_review_widget_state()
    st.session_state.df_original = original_df
    st.session_state.df_review = ensure_review_columns(review_df)
    max_index = max(len(review_df) - 1, 0)
    st.session_state.current_index = min(max(int(metadata.get("current_index") or 0), 0), max_index)
    st.session_state.rows_loaded = True
    st.session_state.loaded_file_name = str(metadata.get("source_name") or "Uploaded dataset")
    st.session_state.loaded_file_size = int(metadata.get("source_size") or 0)
    st.session_state.autosave_path = get_autosave_path(st.session_state.loaded_file_name)
    st.session_state.col_prompt = metadata.get("col_prompt")
    st.session_state.response_columns = list(metadata.get("response_columns") or [])
    st.session_state.response_display_names = dict(metadata.get("response_display_names") or {})
    st.session_state.column_display_names = dict(metadata.get("column_display_names") or {})
    st.session_state.criteria_target_columns = list(metadata.get("criteria_target_columns") or [])
    st.session_state.columns_confirmed = bool(metadata.get("columns_confirmed", False))
    st.session_state.evaluation_column_slots = list(metadata.get("evaluation_column_slots") or [])
    st.session_state.evaluation_column_defaults = {
        int(key): value for key, value in dict(metadata.get("evaluation_column_defaults") or {}).items()
    }
    (user_state_directory() / "active_project.txt").write_text(project_id, encoding="utf-8")
    return True


def restore_active_dataset() -> bool:
    """Restore the last active upload for the signed-in user after a refresh."""
    directory = active_dataset_directory()
    original_path = directory / "original.pkl.gz"
    review_path = directory / "review.pkl.gz"
    metadata_path = directory / "metadata.json"
    if not all(path.exists() for path in (original_path, review_path, metadata_path)):
        return False
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        original_df = pd.read_pickle(original_path, compression="gzip")
        review_df = pd.read_pickle(review_path, compression="gzip")
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return False
    project_id = metadata.get("project_id")
    if project_id:
        return restore_project(str(project_id))
    # Legacy single-project recovery.
    st.session_state.df_original = original_df
    st.session_state.df_review = ensure_review_columns(review_df)
    st.session_state.current_index = min(max(int(metadata.get("current_index") or 0), 0), max(len(review_df) - 1, 0))
    st.session_state.rows_loaded = True
    st.session_state.loaded_file_name = str(metadata.get("source_name") or "Uploaded dataset")
    st.session_state.loaded_file_size = int(metadata.get("source_size") or 0)
    st.session_state.col_prompt = metadata.get("col_prompt")
    st.session_state.response_columns = list(metadata.get("response_columns") or [])
    st.session_state.response_display_names = dict(metadata.get("response_display_names") or {})
    st.session_state.column_display_names = dict(metadata.get("column_display_names") or {})
    st.session_state.criteria_target_columns = list(metadata.get("criteria_target_columns") or [])
    st.session_state.columns_confirmed = bool(metadata.get("columns_confirmed", False))
    return True


def persist_active_review_state() -> None:
    """Persist data, mapping, progress, and the active row for refresh recovery."""
    original_df = st.session_state.get("df_original")
    review_df = st.session_state.get("df_review")
    source_name = st.session_state.get("loaded_file_name")
    if original_df is None or review_df is None or not source_name:
        return
    persist_active_dataset(
        original_df,
        review_df,
        str(source_name),
        int(st.session_state.get("loaded_file_size") or 0),
    )


def reset_column_confirmation() -> None:
    """Require reconfirmation after a mapped column name changes."""
    st.session_state.columns_confirmed = False


def remove_evaluation_column(slot_id: int) -> None:
    """Remove one mapped evaluation column before evaluation starts."""
    removed_column = st.session_state.get(f"select_response_col_{slot_id}")
    st.session_state.evaluation_column_slots = [
        slot
        for slot in st.session_state.evaluation_column_slots
        if slot != slot_id
    ]
    if "criteria_target_columns_widget" in st.session_state:
        st.session_state.criteria_target_columns_widget = [
            column
            for column in st.session_state.criteria_target_columns_widget
            if column != removed_column
        ]
    st.session_state.pop(f"select_response_col_{slot_id}", None)
    st.session_state.columns_confirmed = False


def navigate_to_row(row_index: int, max_index: int) -> None:
    """Keep navigation buttons and the jump slider on the same row."""
    new_index = min(max(int(row_index), 0), max_index)
    st.session_state.current_index = new_index
    st.session_state.jump_to_row = new_index
    persist_active_review_state()


def apply_jump_to_row() -> None:
    """Apply the jump slider value to the active review row."""
    st.session_state.current_index = int(st.session_state.jump_to_row)
    persist_active_review_state()


def find_likely_column(
    df: pd.DataFrame,
    candidates: list[str],
    excluded: Optional[set[str]] = None,
) -> str:
    """Return the first likely uploaded column name for an editable mapping input."""
    excluded = excluded or set()
    columns_by_name = {str(column).strip().lower(): str(column) for column in df.columns}
    for candidate in candidates:
        match = columns_by_name.get(candidate.lower())
        if match and match not in excluded:
            return match
    return ""


def build_download_bytes(df: pd.DataFrame, fmt: str) -> bytes:
    """Create download bytes from the *current* review dataframe."""
    if fmt == "csv":
        return df.to_csv(index=False).encode("utf-8")

    if fmt == "xlsx":
        bio = BytesIO()
        with pd.ExcelWriter(bio, engine="openpyxl") as writer:
            # Use an explicit sheet name for stability.
            df.to_excel(writer, index=False, sheet_name="reviewed")
        return bio.getvalue()

    raise ValueError(f"Unsupported download format: {fmt}")


def prepare_download_dataframe(
    df: pd.DataFrame,
    criteria_target_columns: list,
) -> tuple[pd.DataFrame, list[str]]:
    """Add readable overall ratings to downloads without changing review UI."""
    result = df.copy(deep=True)
    overall_rating_columns = []
    for source_column in criteria_target_columns:
        source_rating_columns = [
            dynamic_rating_column(source_column, rating_column)
            for rating_column in RATING_COLUMNS
            if dynamic_rating_column(source_column, rating_column) in result.columns
        ]
        if not source_rating_columns:
            continue
        output_column = f"{source_column} Overall Rating"
        numeric_ratings = result[source_rating_columns].apply(
            pd.to_numeric, errors="coerce"
        )
        result[output_column] = numeric_ratings.mean(axis=1).round(2).astype("Float64")
        overall_rating_columns.append(output_column)
    return result, overall_rating_columns


def get_autosave_path(source_name: str) -> Path:
    """Return a stable autosave path for an uploaded source file."""
    stem = Path(source_name).stem or "reviewed_output"
    safe_stem = "".join(ch if ch.isalnum() or ch in (" ", "-", "_") else "_" for ch in stem).strip()
    return Path.cwd() / f"{safe_stem or 'reviewed_output'}_autosave.xlsx"


def write_review_xlsx(df: pd.DataFrame, output_path: Path) -> None:
    """Write review data as xlsx, using a temporary file to avoid partial saves."""
    with tempfile.NamedTemporaryFile(
        dir=output_path.parent,
        prefix=f".{output_path.stem}.",
        suffix=".tmp.xlsx",
        delete=False,
    ) as tmp_file:
        tmp_path = Path(tmp_file.name)

    try:
        with pd.ExcelWriter(tmp_path, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="reviewed")
        tmp_path.replace(output_path)
    finally:
        tmp_path.unlink(missing_ok=True)


def autosave_review_data(df: pd.DataFrame, source_name: str) -> Path:
    """Persist the current review state immediately beside the app."""
    output_path = get_autosave_path(source_name)
    write_review_xlsx(df, output_path)
    return output_path


def can_restore_autosave(uploaded_df: pd.DataFrame, autosave_df: pd.DataFrame) -> bool:
    """Avoid loading an autosave that belongs to a different data shape."""
    if len(uploaded_df) != len(autosave_df):
        return False

    review_cols = set(REVIEW_COLUMNS)
    uploaded_cols = [c for c in uploaded_df.columns if c not in review_cols]
    autosave_cols = set(autosave_df.columns)
    return all(c in autosave_cols for c in uploaded_cols)


def try_restore_autosave(uploaded_df: pd.DataFrame, source_name: str) -> tuple[pd.DataFrame, Optional[Path]]:
    """Load a compatible autosave if one exists, otherwise return uploaded data."""
    autosave_path = get_autosave_path(source_name)
    if not autosave_path.exists():
        return ensure_review_columns(uploaded_df.copy()), None

    autosave_df = pd.read_excel(autosave_path)
    autosave_df = ensure_review_columns(autosave_df)
    if can_restore_autosave(uploaded_df, autosave_df):
        return autosave_df, autosave_path

    return ensure_review_columns(uploaded_df.copy()), None


def save_review_file(df: pd.DataFrame, source_name: str) -> Path:
    """Write a reviewed copy beside the app using the uploaded file's extension when possible."""
    source_path = Path(source_name)
    stem = source_path.stem or "reviewed_output"
    suffix = source_path.suffix.lower()

    if suffix not in {".csv", ".xlsx", ".xls"}:
        suffix = ".xlsx"
    elif suffix == ".xls":
        suffix = ".xlsx"

    output_path = Path.cwd() / f"{stem}_reviewed{suffix}"

    if suffix == ".csv":
        df.to_csv(output_path, index=False)
    else:
        write_review_xlsx(df, output_path)

    return output_path



def compute_progress(reviewed_series: pd.Series) -> tuple[int, int, float]:
    total = len(reviewed_series)
    reviewed = int((reviewed_series == "Reviewed").sum())
    pct = (reviewed / total * 100.0) if total else 0.0
    return reviewed, total, pct


def persist_review_draft(
    row_index,
    choice_key: str,
    final_key: str,
    notes_key: str,
    criteria_widget_keys: dict[str, str],
    response_values: Optional[dict[str, str]] = None,
) -> None:
    """Keep in-progress edits when Streamlit reruns or the user switches rows."""
    df_review = st.session_state.get("df_review")
    if df_review is None or row_index not in df_review.index:
        return
    df_review = ensure_review_columns(df_review)
    st.session_state.df_review = df_review

    radio_key = f"{choice_key}_radio"
    previous_choice = st.session_state.get(choice_key, "")
    selected_choice = st.session_state.get(radio_key, st.session_state.get(choice_key, ""))
    final_response = display_text(st.session_state.get(final_key, ""))

    default_responses = dict(response_values or {})
    default_responses["All responses are bad"] = ""
    previous_default = default_responses.get(previous_choice)
    if selected_choice != previous_choice and (
        not final_response.strip() or final_response == previous_default
    ):
        final_response = default_responses.get(selected_choice, final_response)
        st.session_state[final_key] = final_response

    st.session_state[choice_key] = selected_choice

    df_review.at[row_index, "review_choice"] = str(selected_choice)
    df_review.at[row_index, "final_response"] = final_response
    df_review.at[row_index, "reviewer_notes"] = display_text(st.session_state.get(notes_key, ""))
    for column, key in criteria_widget_keys.items():
        rating = rating_from_scale(st.session_state.get(key))
        df_review.at[row_index, column] = rating if rating is not None else pd.NA

    source_name = st.session_state.get("loaded_file_name")
    if source_name:
        try:
            autosave_path = autosave_review_data(df_review, source_name)
        except Exception as e:
            st.session_state.autosave_status = f"Autosave failed: {e}"
        else:
            st.session_state.autosave_status = f"Autosaved to {autosave_path.name}"
    try:
        persist_active_review_state()
    except (OSError, ValueError, TypeError):
        pass


def review_workspace(force_llm: bool = False, mapping_only: bool = False):
    """Run the existing upload, mapping, and evaluation workflow."""
    st.markdown('<div class="workspace-page-marker"></div>', unsafe_allow_html=True)
    selected_model_type = str(st.session_state.get("review_model_type", "LLM")).upper()
    if not force_llm:
        st.markdown('<div class="feature-page-marker"></div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="llm-upload-page-marker"></div>', unsafe_allow_html=True)

    if "df_review" not in st.session_state:
        st.session_state.df_review = None
    if "df_original" not in st.session_state:
        st.session_state.df_original = None

    if "current_index" not in st.session_state:
        st.session_state.current_index = 0

    if "col_prompt" not in st.session_state:
        st.session_state.col_prompt = None
    if "response_columns" not in st.session_state:
        st.session_state.response_columns = []
    if "evaluation_column_slots" not in st.session_state:
        st.session_state.evaluation_column_slots = []
    if "evaluation_column_defaults" not in st.session_state:
        st.session_state.evaluation_column_defaults = {}
    if "response_display_names" not in st.session_state:
        st.session_state.response_display_names = {}
    if "column_display_names" not in st.session_state:
        st.session_state.column_display_names = {}
    if "criteria_target_columns" not in st.session_state:
        st.session_state.criteria_target_columns = []
    if "response_column_count" not in st.session_state:
        st.session_state.response_column_count = 2
    if "columns_confirmed" not in st.session_state:
        st.session_state.columns_confirmed = False
    if st.session_state.get("column_mapping_version") != COLUMN_MAPPING_VERSION:
        for key in list(st.session_state.keys()):
            if key.startswith(
                (
                    "select_response_col_",
                    "response_display_name_",
                    "column_display_name_",
                    "uploaded_column_",
                )
            ):
                del st.session_state[key]
        for key in (
            "select_prompt_col",
            "select_category_col",
            "criteria_target_columns_widget",
        ):
            st.session_state.pop(key, None)
        st.session_state.response_column_count = 2
        st.session_state.response_columns = []
        st.session_state.evaluation_column_slots = []
        st.session_state.evaluation_column_defaults = {}
        st.session_state.response_display_names = {}
        st.session_state.column_display_names = {}
        st.session_state.criteria_target_columns = []
        st.session_state.columns_confirmed = False
        st.session_state.column_mapping_version = COLUMN_MAPPING_VERSION
    if "rows_loaded" not in st.session_state:
        st.session_state.rows_loaded = False
    if "loaded_file_name" not in st.session_state:
        st.session_state.loaded_file_name = None
    if "loaded_file_size" not in st.session_state:
        st.session_state.loaded_file_size = None
    if "autosave_path" not in st.session_state:
        st.session_state.autosave_path = None
    if "autosave_status" not in st.session_state:
        st.session_state.autosave_status = ""

    if mapping_only and (not st.session_state.rows_loaded or st.session_state.df_review is None):
        if not restore_active_dataset():
            st.components.v1.html(
                """<script>window.parent.location.replace(window.parent.location.origin + '/llm-review');</script>""",
                height=0,
            )
            st.stop()

    if mapping_only:
        page_marker = "evaluation-page-marker" if st.session_state.columns_confirmed else "mapping-page-marker"
        st.markdown(f'<div class="{page_marker}"></div>', unsafe_allow_html=True)
    if mapping_only:
        back_href = "/llm-review"
    elif force_llm:
        back_href = "/review"
    else:
        back_href = "/"
    render_inner_navigation("review", back_href=back_href)

    # ------------------ Upload ------------------
    uploaded = None
    if not st.session_state.columns_confirmed and not mapping_only:
        if not force_llm:
            with st.container(key="feature_stage"):
                render_safe_html(
                    f"""
                    <div class="upload-section-head">
                        <div><i>✦</i><span><strong>Our review features</strong><small>Choose the evaluation workflow designed for your data.</small></span></div>
                    </div>
                    <div class="review-product-grid">
                        <a class="review-product-card" href="/llm-review?model_type=slm" target="_self">
                            <div class="review-product-card-inner">
                                <div class="review-product-icon">◉</div>
                                <h3>SLM Data Review</h3>
                                <p>Evaluate compact and domain-focused model responses with structured human judgment.</p>
                                <ul><li>Multiple response comparison</li><li>Context, language, emotion and safety ratings</li><li>Editable final response</li><li>Reviewed dataset export</li></ul>
                                <span class="review-product-action">Open SLM Review →</span>
                            </div>
                        </a>
                        <a class="review-product-card" href="/llm-review?model_type=llm" target="_self">
                            <div class="review-product-card-inner">
                                <div class="review-product-icon">◇</div>
                                <h3>LLM Data Review</h3>
                                <p>Compare general-purpose model outputs and preserve reviewer decisions row by row.</p>
                                <ul><li>Multiple response comparison</li><li>Configurable rating targets</li><li>Editable final response</li><li>Reviewed dataset export</li></ul>
                                <span class="review-product-action">Open LLM Review →</span>
                            </div>
                        </a>
                    </div>
                    """
                )

        if force_llm:
            with st.container(key="upload_stage"):
                render_safe_html(
                    f"""
                    <div class="upload-section-head">
                        <div><i>⇧</i><span><strong>Upload your {selected_model_type} dataset</strong><small>Choose where your evaluation data lives.</small></span></div>
                        <span class="upload-format-pills"><span>CSV</span><span>XLSX</span><span>XLS</span></span>
                    </div>
                    <div class="review-feature-note">Compare model responses, apply human ratings, edit the final answer, and export structured review data.</div>
                    """
                )
                data_source = st.radio(
                    "Choose data source",
                    options=["Local file", "Google Drive / Colab"],
                    horizontal=True,
                    key="upload_data_source",
                )
                if data_source == "Local file":
                    uploaded = st.file_uploader(
                        "Drop a CSV or spreadsheet here",
                        type=["csv", "xlsx", "xls"],
                        accept_multiple_files=False,
                        help="Maximum file size: 200 MB.",
                    )
                else:
                    drive_url = st.text_input(
                        "Google Drive share link",
                        placeholder="https://drive.google.com/file/d/.../view",
                        help="The file must be shared with anyone who has the link.",
                    ).strip()
                    if st.button("Fetch file from Google Drive", type="primary"):
                        if not drive_url:
                            st.error("Enter a Google Drive share link.")
                        else:
                            try:
                                uploaded = fetch_google_drive_file(drive_url)
                            except Exception as e:
                                st.error(f"Failed to fetch Google Drive file: {e}")
                            else:
                                st.success(f"Fetched `{uploaded.name}` from Google Drive.")
                if uploaded is None and not st.session_state.rows_loaded:
                    st.markdown(
                        '<div class="empty-review-state"><i>⇧</i><div><strong>Your review workspace is ready</strong><span>Upload a CSV or spreadsheet above to begin mapping columns and evaluating model responses.</span></div></div>',
                        unsafe_allow_html=True,
                    )

    if uploaded is not None:
        try:
            current_file_name = uploaded.name
            current_file_size = uploaded.size
            is_new_upload = (
                st.session_state.df_review is None
                or not st.session_state.rows_loaded
                or st.session_state.loaded_file_name != current_file_name
                or st.session_state.loaded_file_size != current_file_size
            )

            df = load_dataframe(uploaded) if is_new_upload else None
        except Exception as e:
            st.error(f"Failed to read the uploaded file: {e}")
            return

        if is_new_upload:
            if df is None or df.empty:
                st.error("Uploaded file contains no data.")
                return

            clear_review_widget_state()

            try:
                df_review, restored_path = try_restore_autosave(df, current_file_name)
            except Exception as e:
                st.warning(f"Could not restore autosave, starting from uploaded file: {e}")
                df_review = ensure_review_columns(df.copy())
                restored_path = None

            st.session_state.df_original = df.copy()
            st.session_state.df_review = df_review
            st.session_state.current_index = 0
            st.session_state.rows_loaded = True
            st.session_state.loaded_file_name = current_file_name
            st.session_state.loaded_file_size = current_file_size
            st.session_state.autosave_path = get_autosave_path(current_file_name)

            try:
                persist_active_dataset(df, df_review, current_file_name, current_file_size)
            except (OSError, ValueError, TypeError) as e:
                st.session_state.autosave_status = f"Refresh recovery unavailable: {e}"

            if restored_path is not None:
                st.session_state.autosave_status = f"Restored autosave from {restored_path.name}"
                st.success(f"Restored autosaved review with {len(df_review)} rows.")
            else:
                try:
                    autosave_path = autosave_review_data(df_review, current_file_name)
                except Exception as e:
                    st.session_state.autosave_status = f"Autosave failed: {e}"
                    st.warning(f"Loaded {len(df)} rows, but initial autosave failed: {e}")
                else:
                    st.session_state.autosave_status = f"Autosaved to {autosave_path.name}"
                    st.success(f"Loaded {len(df)} rows and {len(df.columns)} columns.")

            if force_llm:
                if COLUMN_MAPPING_PAGE is None:
                    st.error("Column Mapping page is unavailable. Please refresh and try again.")
                    st.stop()
                st.switch_page(COLUMN_MAPPING_PAGE)

            st.subheader("Preview")
            st.dataframe(df_review.head(50), width="stretch", hide_index=True)
        else:
            st.caption(f"Continuing review for `{current_file_name}`.")


    # If no data loaded yet, stop here.
    if not st.session_state.rows_loaded or st.session_state.df_review is None:
        return

    df_review = st.session_state.df_review
    df_review = ensure_review_columns(df_review)
    st.session_state.df_review = df_review
    if st.session_state.autosave_status and not st.session_state.columns_confirmed:
        st.caption(st.session_state.autosave_status)

    if not st.session_state.columns_confirmed:
        # ------------------ Column selection ------------------
        if mapping_only:
            loaded_name = escape(str(st.session_state.loaded_file_name or "Uploaded dataset"))
            render_safe_html(
                f"""
                <div class="mapping-workbench-intro">
                    <small>Annotation setup</small>
                    <strong>Shape the workspace around your data</strong>
                    <span><b>{loaded_name}</b> is ready. Assign the prompt and response columns, refine their display names, then begin evaluation.</span>
                </div>
                """
            )
        st.subheader("Map your columns")
        available_columns = list(st.session_state.df_original.columns)
        st.markdown("**Available columns in the uploaded file**")
        st.caption("Original column names are kept internally. Edit only the display names if needed.")
        column_display_names = {}
        for column_index, column in enumerate(available_columns):
            column_name_cols = st.columns(2)
            with column_name_cols[0]:
                st.text_input(
                    "Uploaded column",
                    value=str(column),
                    key=f"uploaded_column_{column_index}",
                    disabled=True,
                    label_visibility="collapsed",
                )
            with column_name_cols[1]:
                column_display_names[column] = st.text_input(
                    f"Display name for {column}",
                    value=str(column),
                    key=f"column_display_name_{column_index}",
                    on_change=reset_column_confirmation,
                    label_visibility="collapsed",
                    placeholder="Custom display name",
                ).strip()

        suggested_prompt = find_likely_column(
            st.session_state.df_original,
            ["user", "user_prompt", "prompt", "question", "instruction", "query"],
        )
        suggested_prompt_column = next(
            (column for column in available_columns if str(column) == suggested_prompt),
            None,
        )
        column_options = [None, *available_columns]
        col_prompt = st.selectbox(
            "User Prompt Column (required)",
            options=column_options,
            index=column_options.index(suggested_prompt_column),
            format_func=lambda column: "Select a column" if column is None else str(column),
            key="select_prompt_col",
            on_change=reset_column_confirmation,
        )

        if not st.session_state.evaluation_column_slots:
            non_prompt_columns = [
                column
                for column in available_columns
                if column != suggested_prompt_column
            ]
            excluded_response_terms = {
                "comment", "comments", "note", "notes", "review", "reviewer",
                "category", "problem", "label", "status", "id", "index",
            }
            response_terms = (
                "assistant", "response", "answer", "chosen", "rejected",
                "gemma", "chatgpt", "model", "output", "completion",
            )
            likely_response_columns = [
                column
                for column in non_prompt_columns
                if any(term in str(column).strip().lower() for term in response_terms)
                and not any(term in str(column).strip().lower() for term in excluded_response_terms)
            ]
            fallback_response_columns = [
                column
                for column in non_prompt_columns
                if not any(term in str(column).strip().lower() for term in excluded_response_terms)
            ]
            default_evaluation_columns = likely_response_columns or fallback_response_columns[:2]
            st.session_state.evaluation_column_slots = list(
                range(len(default_evaluation_columns))
            )
            st.session_state.evaluation_column_defaults = {
                slot_id: column
                for slot_id, column in enumerate(default_evaluation_columns)
            }

        response_columns = []
        response_display_names = []
        st.caption("Select only model-output columns that reviewers should compare. Comment, note, category and metadata columns are not selected automatically.")
        for column_number, slot_id in enumerate(
            st.session_state.evaluation_column_slots,
            start=1,
        ):
            default_column = st.session_state.evaluation_column_defaults.get(slot_id)
            mapping_row = st.columns([8, 1])
            with mapping_row[0]:
                response_column = st.selectbox(
                    f"Response column {column_number}",
                    options=column_options,
                    index=(
                        column_options.index(default_column)
                        if default_column in column_options
                        else 0
                    ),
                    format_func=lambda column: "Select a column" if column is None else str(column),
                    key=f"select_response_col_{slot_id}",
                    on_change=reset_column_confirmation,
                )
            with mapping_row[1]:
                st.button(
                    "✕",
                    key=f"remove_evaluation_column_{slot_id}",
                    help=f"Remove Column {column_number} from evaluation",
                    disabled=len(st.session_state.evaluation_column_slots) <= 1,
                    on_click=remove_evaluation_column,
                    args=(slot_id,),
                )
            display_name = (
                column_display_names.get(response_column, "")
                if response_column is not None
                else ""
            )
            response_columns.append(response_column)
            response_display_names.append(display_name)

        default_criteria_targets = [
            column for column in response_columns if column is not None
        ]
        criteria_target_columns = st.multiselect(
            "Apply Review Criteria to columns",
            options=default_criteria_targets,
            default=default_criteria_targets,
            format_func=str,
            key="criteria_target_columns_widget",
            on_change=reset_column_confirmation,
            help="Choose every uploaded-file column that should receive separate star ratings.",
        )
        st.caption("Beta note: review dimensions are provisional and can change as the evaluation framework is finalised.")

        def validate_mapping() -> list[str]:
            errors = []
            if any(not name for name in column_display_names.values()):
                errors.append("Every uploaded column must have a non-empty display name.")
            selected_responses = [column for column in response_columns if column is not None]
            selected_display_names = [
                response_display_names[index]
                for index, column in enumerate(response_columns)
                if column is not None
            ]
            if col_prompt is None:
                errors.append("Select a User Prompt Column.")
            if len(selected_responses) < 1:
                errors.append("Keep at least one column for evaluation.")
            if len(selected_responses) != len(set(selected_responses)):
                errors.append("Duplicate response column selections are not allowed.")
            if any(not name for name in selected_display_names):
                errors.append("Give every selected response column a display name.")
            if len(selected_display_names) != len(set(selected_display_names)):
                errors.append("Response display names must be unique.")
            return errors

        if st.button("Start Evaluation", type="primary", key="start_evaluation_button"):
            mapping_errors = validate_mapping()
            if mapping_errors:
                for error in mapping_errors:
                    st.error(error)
            else:
                st.session_state.col_prompt = col_prompt
                st.session_state.response_columns = [
                    column for column in response_columns if column is not None
                ]
                st.session_state.response_display_names = {
                    column: response_display_names[index]
                    for index, column in enumerate(response_columns)
                    if column is not None
                }
                st.session_state.column_display_names = column_display_names
                st.session_state.criteria_target_columns = criteria_target_columns
                st.session_state.columns_confirmed = True
                persist_active_review_state()
                st.rerun()

        if not st.session_state.columns_confirmed:
            st.info("Confirm the two response columns, then click Start Evaluation.")
            return

        st.success("Columns confirmed. You can continue reviewing below.")

    df_review = ensure_dynamic_rating_columns(
        st.session_state.df_review,
        st.session_state.criteria_target_columns,
    )
    st.session_state.df_review = df_review

    render_parent_brand_portal()

    # ------------------ Progress tracking ------------------
    reviewed_count, total_rows, pct = compute_progress(df_review["reviewed_status"])
    st.subheader("Progress")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Reviewed", f"{reviewed_count}/{total_rows}")
    with c2:
        st.metric("Total", f"{total_rows}")
    with c3:
        st.metric("Complete", f"{pct:.1f}%")
    st.progress(min(max(pct / 100.0, 0.0), 1.0))

    # ------------------ Review interface ------------------
    st.subheader("Review")

    # Navigation controls
    max_index = max(total_rows - 1, 0)
    if "pending_row_navigation" in st.session_state:
        pending_index = st.session_state.pop("pending_row_navigation")
        navigate_to_row(pending_index, max_index)
    if "jump_to_row" not in st.session_state:
        st.session_state.jump_to_row = int(st.session_state.current_index)
    st.session_state.jump_to_row = min(
        max(int(st.session_state.jump_to_row), 0),
        max_index,
    )
    nav_cols = st.columns([1, 1, 1])

    with nav_cols[0]:
        st.button(
            "← Previous",
            disabled=st.session_state.current_index <= 0,
            on_click=navigate_to_row,
            args=(st.session_state.current_index - 1, max_index),
        )

    with nav_cols[1]:
        st.slider(
            "Jump to row",
            min_value=0,
            max_value=max_index,
            step=1,
            key="jump_to_row",
            on_change=apply_jump_to_row,
        )

    with nav_cols[2]:
        st.button(
            "Next →",
            disabled=st.session_state.current_index >= max_index,
            on_click=navigate_to_row,
            args=(st.session_state.current_index + 1, max_index),
        )

    idx = int(st.session_state.current_index)
    row_num_display = idx + 1
    reviewed_status = display_text(df_review.iloc[idx]["reviewed_status"]) if "reviewed_status" in df_review.columns else ""
    is_reviewed = reviewed_status == "Reviewed"

    st.write(f"Row **{row_num_display} / {total_rows}**")
    if is_reviewed:
        st.success("This row is already reviewed.")
    else:
        st.info("This row is not reviewed yet.")

    # Retrieve row content
    prompt_val = display_text(df_review.iloc[idx][st.session_state.col_prompt])
    response_values = {
        st.session_state.response_display_names.get(column, str(column)): display_text(
            df_review.iloc[idx][column]
        )
        for column in st.session_state.response_columns
    }
    # Display side-by-side responses
    with st.container(border=True):
        st.markdown("#### User prompt")
        st.write(prompt_val)

    st.markdown("**Responses**")
    response_display_cols = st.columns(min(len(response_values), 3))
    for response_number, (column, response_value) in enumerate(response_values.items()):
        with response_display_cols[response_number % len(response_display_cols)]:
            with st.container(border=True):
                st.markdown(f"### {column}")
                st.write(response_value)

    # ---- Inputs for selection + final response ----
    existing_choice = display_text(df_review.iloc[idx]["review_choice"]) if "review_choice" in df_review.columns else ""
    existing_final = display_text(df_review.iloc[idx]["final_response"]) if "final_response" in df_review.columns else ""
    existing_notes = display_text(df_review.iloc[idx]["reviewer_notes"]) if "reviewer_notes" in df_review.columns else ""

    choice_options = [
        *response_values.keys(),
        "All responses are bad",
    ]

    # Set defaults based on existing data.
    # For rows without saved data, default to the first mapped response.
    if existing_choice in choice_options:
        default_choice = existing_choice
    else:
        default_choice = next(iter(response_values))

    # Put choice in a stable session key per index so switching rows restores state.
    choice_key = f"choice_{idx}"
    notes_key = f"notes_{idx}"
    show_notes_key = f"show_notes_{idx}"
    final_key = f"final_{idx}"
    radio_key = f"{choice_key}_radio"
    row_index = df_review.index[idx]
    criteria_widget_keys = {}
    for target_index, source_column in enumerate(st.session_state.criteria_target_columns):
        for rating_column in RATING_COLUMNS:
            output_column = dynamic_rating_column(source_column, rating_column)
            criteria_widget_keys[output_column] = (
                f"criteria_scale_{idx}_{target_index}_{rating_column}"
            )

    # Initialize widget-backed session values BEFORE widget instantiation.
    # IMPORTANT: Do not reassign these keys after the widgets are created.
    # Initialize only the widget values we need *before* widget creation.
    # Use setdefault-like logic without modifying the state dict during reruns.
    if choice_key not in st.session_state or st.session_state[choice_key] not in choice_options:
        st.session_state[choice_key] = default_choice
    if notes_key not in st.session_state:
        st.session_state[notes_key] = existing_notes
    if show_notes_key not in st.session_state:
        st.session_state[show_notes_key] = bool(existing_notes.strip())
    if final_key not in st.session_state:
        if is_reviewed:
            st.session_state[final_key] = existing_final
        else:
            st.session_state[final_key] = response_values.get(default_choice, "")
    if radio_key not in st.session_state or st.session_state[radio_key] not in choice_options:
        st.session_state[radio_key] = st.session_state[choice_key]
    for column, key in criteria_widget_keys.items():
        if key not in st.session_state:
            saved_value = df_review.iloc[idx][column]
            try:
                numeric_rating = int(saved_value)
            except (TypeError, ValueError):
                numeric_rating = 0
            st.session_state[key] = numeric_rating if 1 <= numeric_rating <= 5 else None

    draft_callback_args = (
        row_index,
        choice_key,
        final_key,
        notes_key,
        criteria_widget_keys,
        response_values,
    )

    rating_values = {}

    render_safe_html(
        """
        <style>
        div[data-testid="stPills"] button {
            transition: transform 0.15s ease, box-shadow 0.15s ease;
        }
        div[data-testid="stPills"] button:hover {
            transform: scale(1.16) translateY(-2px);
            box-shadow: 0 4px 10px rgba(0, 0, 0, 0.18);
        }
        </style>
        """
    )

    def scale_rating(label: str, key: str) -> Optional[int]:
        st.markdown(f"**{label}**")
        selection = st.pills(
            "Rating",
            options=[1, 2, 3, 4, 5],
            selection_mode="single",
            key=key,
            on_change=persist_review_draft,
            args=draft_callback_args,
            label_visibility="collapsed",
        )
        rating = rating_from_scale(selection)
        st.caption(RATING_MEANINGS[rating] if rating is not None else "Not rated")
        return rating

    if st.session_state.criteria_target_columns:
        review_columns = st.columns(
            len(st.session_state.criteria_target_columns)
        )
        for target_index, source_column in enumerate(
            st.session_state.criteria_target_columns
        ):
            display_name = st.session_state.response_display_names.get(
                source_column,
                st.session_state.column_display_names.get(source_column, str(source_column)),
            )
            with review_columns[target_index]:
                with st.container(
                    border=True,
                    key=f"criteria_paper_{target_index % 8}",
                ):
                    st.markdown(f"#### Review criteria: {display_name}")
                    for criterion_index, (rating_column, label) in enumerate(
                        RATING_COLUMNS.items()
                    ):
                        output_column = dynamic_rating_column(source_column, rating_column)
                        with st.container(
                            border=True,
                            key=f"criterion_sheet_{criterion_index % 8}_{target_index}",
                        ):
                            rating_values[output_column] = scale_rating(
                                label,
                                criteria_widget_keys[output_column],
                            )

    st.markdown("#### Select the best response")
    st.caption("Choose the response that should be copied into the editable final response field. Select ‘All responses are bad’ only when none is usable.")
    selected_choice = st.radio(
        "Response to use",
        options=choice_options,
        index=choice_options.index(st.session_state[radio_key]),
        key=radio_key,
        help="Select one mapped response, or reject all available responses.",
        on_change=persist_review_draft,
        args=draft_callback_args,
        label_visibility="collapsed",
    )

    final_response_text = st.text_area(
        "Final response (editable)",
        key=final_key,
        height=180,
        on_change=persist_review_draft,
        args=draft_callback_args,
    )

    reviewer_notes = display_text(st.session_state.get(notes_key, ""))
    add_reviewer_notes = st.checkbox(
        "Add reviewer notes (optional)",
        key=show_notes_key,
    )
    if add_reviewer_notes:
        reviewer_notes = st.text_area(
            "Reviewer notes",
            height=120,
            key=notes_key,
            on_change=persist_review_draft,
            args=draft_callback_args,
        )


    # Save button
    save_disabled = False
    if selected_choice != "All responses are bad" and not display_text(final_response_text).strip():
        # Empty output is valid only when all responses are rejected.
        save_disabled = True

    if st.button("Save current row", type="primary", disabled=save_disabled):
        # Validation
        if selected_choice != "All responses are bad" and not display_text(final_response_text).strip():
            st.error("Final response should not be empty for the selected response column.")
            return

        st.session_state.df_review.at[df_review.index[idx], "review_choice"] = selected_choice

        st.session_state.df_review.at[df_review.index[idx], "final_response"] = display_text(final_response_text)
        st.session_state.df_review.at[df_review.index[idx], "reviewer_notes"] = display_text(reviewer_notes)
        for output_column, rating in rating_values.items():
            st.session_state.df_review.at[df_review.index[idx], output_column] = (
                rating if rating is not None else pd.NA
            )
        st.session_state.df_review.at[df_review.index[idx], "reviewed_status"] = "Reviewed"

        try:
            autosave_path = autosave_review_data(
                st.session_state.df_review,
                st.session_state.loaded_file_name or "reviewed_output.xlsx",
            )
        except Exception as e:
            st.session_state.autosave_status = f"Autosave failed: {e}"
            st.error(f"Saved in this session, but autosave failed: {e}")
            return
        else:
            st.session_state.autosave_status = f"Autosaved to {autosave_path.name}"

        try:
            persist_active_review_state()
        except (OSError, ValueError, TypeError):
            pass

        # Mark reviewed status as updated in local variables.
        st.success("Saved.")

        if idx < max_index:
            st.session_state.pending_row_navigation = idx + 1

        # Do not modify widget-backed session_state keys after widgets are created.


        # Rerun to refresh progress/status.
        st.rerun()

    # ------------------ Download ------------------
    st.subheader("Download reviewed data")

    # Force-sync the currently visible row before building download payloads.
    # This also captures edits when a download click happens before a widget
    # blur/on_change callback has completed.
    current_row_index = df_review.index[idx]
    st.session_state.df_review.at[current_row_index, "review_choice"] = selected_choice
    st.session_state.df_review.at[current_row_index, "final_response"] = display_text(
        final_response_text
    )
    st.session_state.df_review.at[current_row_index, "reviewer_notes"] = display_text(
        reviewer_notes
    )
    for output_column, rating in rating_values.items():
        st.session_state.df_review.at[current_row_index, output_column] = (
            rating if rating is not None else pd.NA
        )

    # Use an immutable snapshot so both download formats contain identical,
    # up-to-date data for this rerun.
    df_to_download, overall_rating_columns = prepare_download_dataframe(
        st.session_state.df_review,
        st.session_state.criteria_target_columns,
    )

    # Small confirmation preview of saved review columns.
    cols_to_preview = list(
        dict.fromkeys(
            [
                c
                for c in ["review_choice", "final_response"]
                if c in df_to_download.columns
            ]
            + overall_rating_columns
            + [
                c
                for c in ["reviewer_notes", "reviewed_status"]
                if c in df_to_download.columns
            ]
        )
    )
    if cols_to_preview:
        preview_cols = st.columns([1, 1])
        with preview_cols[0]:
            preview_scope = st.selectbox(
                "Preview rows",
                options=["First 20 rows", "All rows", "Reviewed rows", "Unreviewed rows"],
                key="download_preview_scope",
            )
        with preview_cols[1]:
            preview_columns = st.radio(
                "Preview columns",
                options=["Review fields only", "All columns"],
                horizontal=True,
                key="download_preview_columns",
            )

        if preview_scope == "All rows":
            df_preview = df_to_download
        elif preview_scope == "Reviewed rows":
            df_preview = df_to_download[df_to_download["reviewed_status"] == "Reviewed"]
        elif preview_scope == "Unreviewed rows":
            df_preview = df_to_download[df_to_download["reviewed_status"] != "Reviewed"]
        else:
            df_preview = df_to_download.head(20)

        if preview_columns == "Review fields only":
            df_preview = df_preview[cols_to_preview]

        st.caption(f"Preview showing {len(df_preview)} row(s). Downloads still include all {len(df_to_download)} row(s).")
        st.dataframe(df_preview, width="stretch", hide_index=True)

    dl_cols = st.columns(2)
    csv_bytes = build_download_bytes(df_to_download, "csv")
    download_revision = hashlib.sha256(csv_bytes).hexdigest()[:12]

    with dl_cols[0]:
        st.download_button(
            label="Download CSV",
            data=csv_bytes,
            file_name=f"reviewed_output_{download_revision}.csv",
            mime="text/csv",
            key=f"download_csv_{download_revision}",
        )

    with dl_cols[1]:
        xlsx_bytes = build_download_bytes(df_to_download, "xlsx")
        st.download_button(
            label="Download Excel (.xlsx)",
            data=xlsx_bytes,
            file_name=f"reviewed_output_{download_revision}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key=f"download_xlsx_{download_revision}",
        )

    if st.button("Save reviewed copy in this folder"):
        try:
            output_path = save_review_file(df_to_download, st.session_state.loaded_file_name or "reviewed_output.xlsx")
        except Exception as e:
            st.error(f"Failed to save reviewed copy: {e}")
        else:
            st.success(f"Saved reviewed copy to {output_path}")


    # ------------------ Optional LLM Judge Check placeholder ------------------
    st.subheader("LLM Judge Check")
    st.caption("Placeholder UI only. No real API call is performed.")

    guidelines = st.text_area(
        "Guidelines for LLM Judge Check",
        value="",
        height=140,
        key="judge_guidelines",
    )

    if st.button("Check Final Response"):
        st.info("API integration can be added later.")


def render_site_footer() -> None:
    """Render shared product footer navigation."""
    render_safe_html(
        """
        <footer class="site-footer">
            <a class="site-footer-brand" href="/" target="_self" aria-label="Go to MIRA home"><i></i> MIRA</a>
            <div>Built for thoughtful human evaluation, not endless spreadsheets.</div>
            <div class="site-footer-links"><a href="/account" target="_self">Account</a><a href="/about" target="_self">About</a><a href="https://www.hyperneuronai.com/" target="_self">HyperNeuron ↗</a></div>
        </footer>
        """
    )


def render_inner_navigation(active_page: str, back_href: str = "/") -> None:
    """Render consistent navigation across secondary product pages."""
    signed_in = google_auth_configured() and bool(getattr(st.user, "is_logged_in", False))
    review_href = "/review" if signed_in else "/account"
    home_active = " active" if active_page == "home" else ""
    about_active = " active" if active_page == "about" else ""
    account_active = " active" if active_page == "account" else ""
    review_active = " active" if active_page == "review" else ""
    projects_active = " active" if active_page == "projects" else ""
    if signed_in:
        nav_user_name = escape(str(getattr(st.user, "name", None) or "Google user"))
        nav_user_email = escape(str(getattr(st.user, "email", None) or ""))
        nav_user_initial = (nav_user_name.strip()[:1] or nav_user_email.strip()[:1] or "G").upper()
        account_navigation = f"""<div class="nav-account-menu"><a class="nav-user-avatar{account_active}" href="/account" target="_self" aria-label="Open account menu">{nav_user_initial}</a><div class="nav-account-dropdown"><div class="nav-account-identity"><strong>{nav_user_name}</strong><span>{nav_user_email}</span></div><a href="/account" target="_self">Account settings</a><a class="sign-out" href="/logout" target="_self">Sign out</a></div></div>"""
    else:
        account_navigation = f'<a class="{account_active.strip()}" href="/account" target="_self">Account</a>'
    navigation_markup = dedent(
        f"""
        <header class="inner-site-header">
            <div class="news-top">
                <a class="route-back-link" href="{escape(back_href)}" target="_self" aria-label="Go back">←</a>
                <a class="news-brand" href="/" target="_self" aria-label="MIRA home"><span class="news-brand-mark" aria-hidden="true"><i></i><i></i><i></i></span><span>MIRA</span></a>
                <nav class="news-nav" aria-label="Primary navigation">
                    <a class="{home_active.strip()}" href="/" target="_self"><i class="nav-icon">⌂</i>Home</a>
                    <a class="{about_active.strip()}" href="/about" target="_self"><i class="nav-icon">◉</i>About</a>
                    <a href="https://www.hyperneuronai.com/" target="_self"><i class="nav-icon">◇</i>Parent Website</a>
                    <a class="{review_active.strip()}" href="{review_href}" target="_self"><i class="nav-icon">→</i>Review Workspace</a>
                    {f'<a class="{projects_active.strip()}" href="/projects" target="_self"><i class="nav-icon">▦</i>Projects</a>' if signed_in else ''}
                </nav>
                <div class="news-actions">{account_navigation}</div>
            </div>
        </header>
        """
    ).strip()
    navigation_markup = "".join(line.strip() for line in navigation_markup.splitlines())
    render_safe_html(navigation_markup)


def home_page():
    """Render the product landing page without workspace controls."""
    render_page_header(False)
    render_site_footer()


def start_new_review_project() -> None:
    """Clear only the active browser state; saved project history remains intact."""
    clear_review_widget_state()
    st.session_state.df_original = None
    st.session_state.df_review = None
    st.session_state.current_index = 0
    st.session_state.rows_loaded = False
    st.session_state.loaded_file_name = None
    st.session_state.loaded_file_size = None
    st.session_state.autosave_path = None
    st.session_state.autosave_status = ""


def projects_page():
    """Show the signed-in reviewer's saved evaluations and resume them."""
    signed_in = google_auth_configured() and bool(getattr(st.user, "is_logged_in", False))
    if not signed_in:
        st.components.v1.html(
            """<script>window.parent.location.replace(window.parent.location.origin + '/account');</script>""",
            height=0,
        )
        st.stop()
    st.markdown('<div class="projects-page-marker"></div>', unsafe_allow_html=True)
    render_inner_navigation("projects")
    render_safe_html(
        """
        <section class="projects-hero">
            <small>Saved evaluation workspace</small>
            <h1>Your review projects</h1>
            <p>Every upload keeps its mapping, ratings, edited responses, progress and last active row. Resume after a disconnect without rebuilding the evaluation.</p>
        </section>
        """
    )
    projects = list_review_projects()
    action_left, action_right = st.columns([1, 2])
    with action_left:
        if st.button("Start a new project", icon=":material/add:", width="stretch"):
            start_new_review_project()
            st.switch_page(LLM_REVIEW_PAGE)
    with action_right:
        st.caption(f"{len(projects)} saved project{'s' if len(projects) != 1 else ''} for this account")
    if not projects:
        st.info("No saved projects yet. Upload a dataset to create your first review project.")
        render_site_footer()
        return
    for row_start in range(0, len(projects), 3):
        cards = st.columns(min(3, len(projects) - row_start))
        for offset, project in enumerate(projects[row_start:row_start + 3]):
            project_id = str(project["project_id"])
            updated_raw = str(project.get("updated_at") or "")
            try:
                updated_label = datetime.fromisoformat(updated_raw).astimezone().strftime("%d %b %Y, %I:%M %p")
            except ValueError:
                updated_label = "Saved recently"
            reviewed = int(project.get("reviewed") or 0)
            total = int(project.get("total") or 0)
            progress = float(project.get("progress") or 0)
            current_row = min(int(project.get("current_index") or 0) + 1, max(total, 1))
            with cards[offset]:
                render_safe_html(
                    f"""<div class="saved-project-card"><small>Updated {escape(updated_label)}</small><h3>{escape(str(project.get('source_name') or 'Untitled review'))}</h3><p>{reviewed} of {total} rows reviewed · resume at row {current_row}</p><div class="saved-project-progress"><i style="width:{min(max(progress, 0), 100):.1f}%"></i></div></div>"""
                )
                if st.button("Resume project →", key=f"resume_project_{project_id}", width="stretch"):
                    if restore_project(project_id):
                        st.switch_page(COLUMN_MAPPING_PAGE)
                    else:
                        st.error("This project could not be restored.")
    render_site_footer()


def about_page():
    """Explain the product, workflow, and parent-company connection."""
    st.markdown('<div class="about-page-marker"></div>', unsafe_allow_html=True)
    render_inner_navigation("about")
    render_safe_html(
        """
        <section class="about-hero">
            <div class="about-hero-copy"><small>About MIRA</small><h1>Human judgment is the final layer of intelligent AI.</h1><p>MIRA, Model Inference and Response Annotation, helps teams compare model responses with context, capture structured feedback, and produce reliable evaluation datasets without losing the nuance only a human reviewer can provide.</p></div>
            <div class="about-human-loop" aria-hidden="true"><div class="about-loop-ring"></div><div class="about-loop-core"><i>✓</i><b>Human signal</b><span>structured and preserved</span></div><span class="about-loop-tag one">Prompt context</span><span class="about-loop-tag two">Response quality</span><span class="about-loop-tag three">Reviewer rationale</span></div>
        </section>
        <section class="about-manifesto"><div><small>Why MIRA exists</small><h2>Evaluation should explain, not just score.</h2></div><p>A number can tell a team which response won. It cannot explain whether the answer understood the user, sounded natural in their language, or deserved trust. MIRA keeps those human decisions attached to the data so improvement remains traceable.</p></section>
        <section class="about-domain-story"><div class="domain-story-head"><div><small>Built for language in the real world</small><h2>Nuance becomes critical where data is scarce.</h2></div><p>LLMs may sound increasingly natural while still missing domain factuality, instruction intent, cultural context and emotional expression. The gap becomes sharper in low-resource Indic languages and high-stakes domains such as BFSI, where a fluent but incorrect answer can create real risk.</p></div><div class="domain-subjects"><article class="domain-subject"><i>अ</i><h3>Indic language nuance</h3><p>Evaluate whether English, Hindi and Hinglish responses match the user’s language, register and cultural context, rather than simply checking whether the words are grammatical.</p></article><article class="domain-subject"><i>₹</i><h3>Domain-aware judgment</h3><p>Help experts look beyond confident phrasing to assess instruction adherence, contextual relevance and the appropriateness of financial claims.</p></article><article class="domain-subject"><i>H</i><h3>Human preference signal</h3><p>Capture the syntactic, semantic and naturalness judgments that automated similarity scores and model judges can overlook.</p></article></div><div class="alignment-usecases"><div class="alignment-usecase"><b>Response evaluation</b><span>Pairwise comparison and individual response review.</span></div><div class="alignment-usecase"><b>Gold datasets</b><span>Curated examples for reliable benchmarking.</span></div><div class="alignment-usecase"><b>Preference data</b><span>Structured choices suitable for DPO and quality analysis.</span></div><div class="alignment-usecase"><b>Extensible tasks</b><span>A foundation for translation, summarisation and linguistic review.</span></div></div></section>
        <section class="about-principles"><div class="about-section-heading"><div><small>What MIRA protects</small><h2>Human judgment without losing structure.</h2></div><p>Designed around the decisions reviewers actually make, from understanding intent to preserving the reasoning behind a final answer.</p></div><div class="about-grid">
            <article class="about-card"><div class="about-card-icon">◫</div><h3>Meet the data where it is</h3><p>Bring CSV or Excel files, map your own prompt and response columns, and preserve original data throughout the review.</p></article>
            <article class="about-card"><div class="about-card-icon">◎</div><h3>Make judgment consistent</h3><p>Compare multiple responses, capture column-wise criteria, select the strongest answer and refine the final response.</p></article>
            <article class="about-card"><div class="about-card-icon">↗</div><h3>Carry evidence forward</h3><p>Autosave every reviewed row and export decisions, ratings and notes for analysis or model improvement.</p></article>
        </div></section>
        <section class="about-workflow"><div class="about-section-heading"><div><small>From raw output to trusted data</small><h2>One continuous review journey.</h2></div><p>Every stage stays connected, so teams spend less time managing spreadsheets and more time improving model behavior.</p></div><div class="about-steps">
            <div class="about-step"><b>01 · Upload</b>Add the dataset you want to evaluate.</div>
            <div class="about-step"><b>02 · Map</b>Choose prompt, responses, labels, and rating targets.</div>
            <div class="about-step"><b>03 · Review</b>Compare outputs and capture human judgment.</div>
            <div class="about-step"><b>04 · Export</b>Download a structured, evaluation-ready dataset.</div>
        </div></section>
        """
    )
    render_safe_html(
        """
        <div class="about-actions">
            <div class="about-actions-copy">
                <strong>Ready to continue?</strong>
                <span>Return to the product overview or discover the company behind this workspace.</span>
            </div>
            <div class="about-action-links">
                <a class="about-home-link" href="/">← Back to Home</a>
                <a class="about-company-link" href="https://www.hyperneuronai.com/" target="_blank" rel="noopener noreferrer">Explore HyperNeuron AI ↗</a>
            </div>
        </div>
        """
    )
    render_site_footer()


def google_auth_configured() -> bool:
    """Return whether the required Google OIDC settings are available."""
    try:
        auth = st.secrets.get("auth", {})
    except (FileNotFoundError, KeyError):
        return False
    return all(
        auth.get(key)
        for key in ("redirect_uri", "cookie_secret", "client_id", "client_secret", "server_metadata_url")
    )


def account_page():
    """Provide Google OIDC sign-in and signed-in account controls."""
    configured = google_auth_configured()
    logged_in = configured and bool(getattr(st.user, "is_logged_in", False))
    st.markdown('<div class="auth-page-marker"></div>', unsafe_allow_html=True)
    render_inner_navigation("account")
    with st.container(key="account_page_shell"):
        with st.container(border=True, key="account_auth_panel"):
                auth_state = "ready" if logged_in else "secure"
                render_safe_html(f'<div class="account-auth-state {auth_state}"><i></i>{"Workspace ready" if logged_in else "Secure sign in"}</div>')
                render_safe_html(
                    f"""
                    <div class="auth-panel-marker"></div>
                    <div class="auth-panel-head">
                        <div class="google-logo-pro"><span>G</span></div>
                        <h2>{"Welcome back" if logged_in else "Sign in to MIRA"}</h2>
                        <p>{"Your secure review workspace is ready." if logged_in else "Continue with Google to access model evaluation."}</p>
                    </div>
                    """
                )
                if logged_in:
                    user_name = escape(str(getattr(st.user, "name", None) or "Google user"))
                    user_email = escape(str(getattr(st.user, "email", None) or ""))
                    initial = str(user_name).strip()[:1].upper() or "G"
                    render_safe_html(
                        f'<div class="signed-user"><div class="signed-avatar">{initial}</div><div><strong>{user_name}</strong><span>{user_email}</span></div></div>'
                    )
                    render_safe_html('<a class="auth-route-link primary" href="/review">Continue to Review Workspace →</a>')
                    st.button("Sign out", on_click=st.logout, width="stretch")
                elif configured:
                    st.button("Continue with Google", type="primary", icon=":material/login:", on_click=st.login, width="stretch")
                else:
                    st.button("Continue with Google", disabled=True, width="stretch")
                    st.warning("Google authentication has not been configured yet.")
                    st.caption("Add the Google Client ID and Client Secret to `.streamlit/secrets.toml` to activate sign-in.")
                render_safe_html('<div class="auth-trust">Protected through Google OpenID Connect.</div>')
    render_site_footer()


def protected_review_workspace():
    """Require Google authentication before rendering any evaluation data."""
    signed_in = google_auth_configured() and bool(getattr(st.user, "is_logged_in", False))
    if not signed_in:
        st.components.v1.html(
            """<script>window.parent.location.replace(window.parent.location.origin + '/account');</script>""",
            height=0,
        )
        st.info("Sign in is required. Redirecting you to the login page…")
        st.stop()
    review_workspace()


def protected_llm_review_workspace():
    """Open the dedicated SLM/LLM upload and evaluation workflow."""
    signed_in = google_auth_configured() and bool(getattr(st.user, "is_logged_in", False))
    if not signed_in:
        st.components.v1.html(
            """<script>window.parent.location.replace(window.parent.location.origin + '/account');</script>""",
            height=0,
        )
        st.info("Sign in is required. Redirecting you to the login page…")
        st.stop()
    requested_model_type = str(st.query_params.get("model_type", "")).strip().lower()
    if requested_model_type in {"slm", "llm"}:
        st.session_state.review_model_type = requested_model_type.upper()
    # This route is the step immediately before column mapping/evaluation.
    # When browser Back returns here, leave the evaluation view instead of
    # rendering the same Progress screen again. The loaded dataset, ratings,
    # autosave and current row remain intact and can be confirmed again.
    if st.session_state.get("columns_confirmed", False):
        st.session_state.columns_confirmed = False
    review_workspace(force_llm=True)


def protected_column_mapping_workspace():
    """Open the uploaded dataset on a fresh column-mapping page."""
    signed_in = google_auth_configured() and bool(getattr(st.user, "is_logged_in", False))
    if not signed_in:
        st.components.v1.html(
            """<script>window.parent.location.replace(window.parent.location.origin + '/account');</script>""",
            height=0,
        )
        st.info("Sign in is required. Redirecting you to the login page…")
        st.stop()
    review_workspace(force_llm=True, mapping_only=True)


def logout_page():
    """Sign out from Google and return to the public home page."""
    if google_auth_configured() and bool(getattr(st.user, "is_logged_in", False)):
        st.logout()
        st.stop()
    st.components.v1.html(
        """<script>window.parent.location.replace(window.parent.location.origin + '/');</script>""",
        height=0,
    )
    st.stop()


def run_app():
    """Configure and run the multipage Streamlit application."""
    global COLUMN_MAPPING_PAGE, LLM_REVIEW_PAGE
    st.set_page_config(page_title="MIRA · Model Inference and Response Annotation", page_icon="◉", layout="wide")
    inject_app_theme()
    install_navigation_history_support()
    auth_ready = google_auth_configured()
    signed_in = auth_ready and bool(getattr(st.user, "is_logged_in", False))
    COLUMN_MAPPING_PAGE = st.Page(
        protected_column_mapping_workspace,
        title="Column Mapping",
        icon=":material/account_tree:" if signed_in else ":material/lock:",
        url_path="column-mapping",
    )
    LLM_REVIEW_PAGE = st.Page(
        protected_llm_review_workspace,
        title="SLM / LLM Data Review",
        icon=":material/table_view:" if signed_in else ":material/lock:",
        url_path="llm-review",
    )
    if signed_in:
        pages = [
            st.Page(home_page, title="Home", icon=":material/home:", url_path="home", default=True),
            st.Page(protected_review_workspace, title="Review Workspace", icon=":material/rate_review:", url_path="review"),
            LLM_REVIEW_PAGE,
            COLUMN_MAPPING_PAGE,
            st.Page(projects_page, title="Projects", icon=":material/folder_open:", url_path="projects"),
            st.Page(about_page, title="About", icon=":material/info:", url_path="about"),
            st.Page(account_page, title="Account", icon=":material/account_circle:", url_path="account"),
            st.Page(logout_page, title="Sign out", icon=":material/logout:", url_path="logout"),
        ]
    else:
        pages = [
            st.Page(home_page, title="Home", icon=":material/home:", url_path="home", default=True),
            st.Page(protected_review_workspace, title="Review Workspace", icon=":material/lock:", url_path="review"),
            LLM_REVIEW_PAGE,
            COLUMN_MAPPING_PAGE,
            st.Page(projects_page, title="Projects", icon=":material/lock:", url_path="projects"),
            st.Page(about_page, title="About", icon=":material/info:", url_path="about"),
            st.Page(account_page, title="Sign in", icon=":material/login:", url_path="account"),
            st.Page(logout_page, title="Sign out", icon=":material/logout:", url_path="logout"),
        ]
    navigation = st.navigation(pages, position="hidden")
    navigation.run()


if __name__ == "__main__":
    run_app()
