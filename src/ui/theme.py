"""Visual constants and the global stylesheet.

Colour maps are keyed by the exact vocabulary used in the models, so a typo in
a label shows up as the neutral grey instead of silently disappearing.
"""
from __future__ import annotations

NEUTRAL = "#94a3b8"
GREEN = "#16a34a"
RED = "#dc2626"
SLATE = "#64748b"

DIRECTION_COLORS = {
    "支持改动方向": GREEN,
    "反对改动方向": RED,
    "对方向没有明确态度": NEUTRAL,
    "无法判断": "#cbd5e1",
}
DIRECTION_ORDER = ["支持改动方向", "反对改动方向", "对方向没有明确态度", "无法判断"]

INTENSITY_COLORS = {
    "力度不足": "#f59e0b",
    "力度适中": GREEN,
    "力度过大": RED,
    "不适用": NEUTRAL,
    "无法判断": "#cbd5e1",
}
INTENSITY_ORDER = ["力度不足", "力度适中", "力度过大", "不适用", "无法判断"]

ROOT_COLORS = {
    "原问题已缓解": GREEN,
    "原问题部分缓解": "#84cc16",
    "原问题仍未解决": RED,
    "产生了新问题": "#9333ea",
    "无法判断": "#cbd5e1",
}
ROOT_ORDER = ["原问题已缓解", "原问题部分缓解", "原问题仍未解决", "产生了新问题", "无法判断"]

STANCE_COLORS = {
    "支持": GREEN,
    "条件性支持": "#65a30d",
    "反对": RED,
    "需要继续观察": "#d97706",
    "仅描述现象": SLATE,
    "玩梗或无有效信息": NEUTRAL,
    "与当前改动无关": NEUTRAL,
    "无法判断": NEUTRAL,
}

CONTROVERSY_STYLE = {
    "高": ("#b91c1c", "#fef2f2"),
    "中": ("#b45309", "#fffbeb"),
    "低": ("#15803d", "#f0fdf4"),
    "证据不足": ("#475569", "#f1f5f9"),
}
CONTROVERSY_ORDER = {"高": 0, "中": 1, "低": 2, "证据不足": 3}
CONTROVERSY_LEVELS = ["高", "中", "低", "证据不足"]

CUSTOM_CSS = """
<style>
    .stApp { background:#f5f7fa; color:#1f2a37; }
    [data-testid="stSidebar"] { background:#17212d; }
    [data-testid="stSidebar"] { color:#edf2f7; }
    [data-testid="stSidebar"] label,
    [data-testid="stSidebar"] p,
    [data-testid="stSidebar"] h1,
    [data-testid="stSidebar"] h2,
    [data-testid="stSidebar"] h3 { color:#edf2f7 !important; }
    [data-testid="stSidebar"] button,
    [data-testid="stSidebar"] button * { color:#111827 !important; -webkit-text-fill-color:#111827 !important; }
    [data-testid="stSidebar"] input,
    [data-testid="stSidebar"] textarea,
    [data-testid="stSidebar"] [contenteditable="true"],
    [data-testid="stSidebar"] [role="combobox"],
    [data-testid="stSidebar"] [data-baseweb="input"] *,
    [data-testid="stSidebar"] [data-baseweb="textarea"] * { color:#111827 !important; background:#ffffff !important; -webkit-text-fill-color:#111827 !important; caret-color:#111827 !important; opacity:1 !important; }
    [data-testid="stSidebar"] .stTextInput input::placeholder,
    [data-testid="stSidebar"] .stTextArea textarea::placeholder { color:#64748b !important; -webkit-text-fill-color:#64748b !important; }
    [data-testid="stSidebar"] [data-baseweb="select"] > div { background:#ffffff !important; border-color:#94a3b8 !important; }
    /* Scoped to the value container only. Earlier rules targeted every nested
       `div`/`span`, which also hit baseweb's absolutely-positioned helper
       elements; forcing those visible is what made the controls overlap. */
    [data-testid="stSidebar"] [data-baseweb="select"] > div > div { color:#111827 !important; -webkit-text-fill-color:#111827 !important; }
    [data-testid="stSidebar"] [data-baseweb="select"] svg { fill:#334155 !important; }
    [data-testid="stSidebar"] [data-testid="stJson"], [data-testid="stSidebar"] [data-testid="stJson"] pre { background:#f8fafc !important; }
    [data-testid="stSidebar"] [data-testid="stJson"] code { color:#0f172a !important; -webkit-text-fill-color:#0f172a !important; }

    [data-testid="stSidebar"] [data-testid="stBaseButton-primary"],
    [data-testid="stSidebar"] button[kind="primary"] { background:#2563eb !important; }
    [data-testid="stSidebar"] [data-testid="stBaseButton-primary"] p,
    [data-testid="stSidebar"] button[kind="primary"] p { color:#ffffff !important; -webkit-text-fill-color:#ffffff !important; }
    [data-testid="stSidebar"] [data-baseweb="input"],
    [data-testid="stSidebar"] [data-baseweb="textarea"] { background:#ffffff !important; border-color:#94a3b8 !important; }
    [data-baseweb="popover"] [role="option"],
    [data-baseweb="popover"] [role="option"] * { background:#ffffff !important; color:#111827 !important; -webkit-text-fill-color:#111827 !important; }

    /* The default 336px sidebar truncates model ids and wraps every label. */
    [data-testid="stSidebar"] { min-width:348px; max-width:480px; }
    [data-testid="stSidebar"] [data-baseweb="select"] > div > div { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; display:block; }
    [data-testid="stSidebar"] [data-testid="stExpander"] summary p { font-size:13px; }
    /* Reserve clearance for the fixed Streamlit toolbar. */
    .block-container { max-width:1440px; padding-top:4.5rem; }
    div[data-testid="stMetric"] {
        background:white; border:1px solid #e4e9ef; border-radius:10px; padding:12px 14px;
    }
    div[data-testid="stMetric"] label { color:#64748b; font-size:12px; }
    div[data-testid="stMetric"] [data-testid="stMetricValue"] { font-size:22px; font-weight:650; }
    .notice { border-left:4px solid #c34a36; background:#fff7f5; padding:10px 14px; margin:8px 0 16px; }
    .card { background:white; border:1px solid #dce2e9; border-radius:8px; padding:16px; margin:8px 0; }

    /* Pipeline steps: make the four main-line buttons read as one strip. */
    [data-testid="stColumn"] > div > [data-testid="stButton"] button,
    [data-testid="stHorizontalBlock"] [data-testid="stButton"] button {
        border-radius:10px; font-weight:600; font-size:14px; padding:10px 12px;
    }
    div[data-testid="stProgress"] > div > div { border-radius:999px; }
    hr { margin:1.1rem 0; }
    [data-testid="stExpander"] details { border:1px solid #e4e9ef; border-radius:10px; }
</style>
"""
