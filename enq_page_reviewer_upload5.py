import json
from io import BytesIO
from pathlib import Path
from datetime import datetime
import re
import unicodedata
import time

import fitz  # PyMuPDF
import pandas as pd
import streamlit as st
from PIL import Image, ImageDraw, ImageFont

# =========================
# Autosave / Checkpoint
# =========================
APP_DIR = Path(__file__).resolve().parent
AUTOSAVE_DIR = APP_DIR / "autosave"
AUTOSAVE_DIR.mkdir(exist_ok=True)

def stem_from_name(name: str, fallback="ocr_output"):
    try:
        return Path(name).stem or fallback
    except Exception:
        return fallback

def progress_path_for(base: str, datestr: str | None = None) -> Path:
    datestr = datestr or datetime.now().strftime("%Y%m%d")
    return AUTOSAVE_DIR / f"{base}_{datestr}_progress.json"

def checkpoint_paths_for(base: str) -> tuple[Path, Path]:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = AUTOSAVE_DIR / f"{base}_checkpoint_{ts}.csv"
    prog_path = AUTOSAVE_DIR / f"{base}_checkpoint_{ts}_progress.json"
    return csv_path, prog_path

def save_progress_file(progress_path: Path, autosave_path: str = ""):
    prog = {
        "autosave_path": autosave_path or st.session_state.get("autosave_path", ""),
        "current_resp": st.session_state.get("current_resp", ""),
        "current_page": st.session_state.get("current_page", ""),
        "pages_per_resp": int(st.session_state.get("pages_per_resp_ui", 16)),
        "cover_pages": int(st.session_state.get("cover_pages_ui", 1)),
        "checked": st.session_state.get("checked", {}),
        "timestamp": datetime.now().isoformat(timespec="seconds"),
    }
    progress_path.write_text(json.dumps(prog, ensure_ascii=False, indent=2), encoding="utf-8")

def load_progress(progress_path: Path) -> dict:
    return json.loads(progress_path.read_text(encoding="utf-8"))

def save_checkpoint(base: str, df_edit: pd.DataFrame, reason: str = "manual") -> tuple[str, str]:
    """編集途中を退避（未反映でもOK）。CSV＋progressを保存してパスを返す。"""
    csv_path, prog_path = checkpoint_paths_for(base)
    df_edit.to_csv(csv_path, index=False, encoding="utf-8-sig")

    # checkpointのprogressはこのcheckpoint CSVを autosave_path として記録
    save_progress_file(prog_path, autosave_path=str(csv_path))

    st.session_state.last_checkpoint_time = time.time()
    st.session_state.last_checkpoint_csv = str(csv_path)
    st.session_state.last_checkpoint_reason = reason
    return str(csv_path), str(prog_path)

# =========================
# Pending restore (ウィジェット生成前に反映)
# =========================
# 復元ボタンを押した直後に session_state を直接書き換えると例外が出るので、
# pending_restore に詰めて、次回実行の最初（ここ）で反映する。
if "pending_restore" in st.session_state:
    pr = st.session_state.pop("pending_restore")
    st.session_state["pages_per_resp_ui"] = int(pr.get("pages_per_resp", 16))
    st.session_state["cover_pages_ui"] = int(pr.get("cover_pages", 1))
    st.session_state["checked"] = pr.get("checked", {})
    # autosave_path（復元元CSV）も反映（任意）
    if pr.get("autosave_path"):
        st.session_state["autosave_path"] = pr["autosave_path"]
    # 位置
    if pr.get("current_resp") is not None:
        st.session_state["current_resp"] = pr["current_resp"]
    if pr.get("current_page") is not None:
        st.session_state["current_page"] = pr["current_page"]

# =========================
# Utilities
# =========================

def _text_wh(draw, text, font):
    # Pillowのバージョン差に強い順で試す
    if hasattr(draw, "textbbox"):
        l, t, r, b = draw.textbbox((0, 0), text, font=font)
        return (r - l), (b - t)
    if hasattr(font, "getbbox"):
        l, t, r, b = font.getbbox(text)
        return (r - l), (b - t)
    if hasattr(font, "getsize"):
        return font.getsize(text)
    # 最後の保険
    return (len(text) * 10, 20)



def clamp01(v: float) -> float:
    return max(0.0, min(1.0, v))

def norm_qid(s: str) -> str:
    return unicodedata.normalize("NFKC", (s or "")).strip()

def denorm_bbox(b, w, h):
    x0 = int(clamp01(float(b[0])) * w)
    y0 = int(clamp01(float(b[1])) * h)
    x1 = int(clamp01(float(b[2])) * w)
    y1 = int(clamp01(float(b[3])) * h)
    if x1 < x0:
        x0, x1 = x1, x0
    if y1 < y0:
        y0, y1 = y1, y0
    return x0, y0, x1, y1

def draw_overlay_boxes(
    img: Image.Image,
    qid_to_bbox: dict,
    qid_to_value: dict | None = None,
    show_labels: bool = True,
    show_values: bool = False,
    value_font_size: int = 48,
    value_alpha: int = 80,   # 0..255（例：80=約31%）
    value_max_chars: int = 12,
) -> Image.Image:
    """
    - 赤枠＋問番号（show_labels）
    - 枠内にOCR値を半透明で描画（show_values）
    """
    # ベースはRGBで受ける想定。合成用にRGBAにする
    base = img.convert("RGBA")
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # フォント（問番号）
    font_label = None
    for fp in [
        "/usr/share/fonts/opentype/ipafont-gothic/ipag.ttf",
        "/usr/share/fonts/truetype/fonts-japanese-gothic.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    ]:
        try:
            font_label = ImageFont.truetype(fp, 32)
            break
        except Exception:
            pass
    if font_label is None:
        font_label = ImageFont.load_default()

    # フォント（値表示）
    font_value = None
    for fp in [
        "/usr/share/fonts/opentype/ipafont-gothic/ipag.ttf",
        "/usr/share/fonts/truetype/fonts-japanese-gothic.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    ]:
        try:
            font_value = ImageFont.truetype(fp, value_font_size)
            break
        except Exception:
            pass
    if font_value is None:
        font_value = ImageFont.load_default()

    w, h = base.size
    i = 0

    for qid, b in (qid_to_bbox or {}).items():
        try:
            x0, y0, x1, y1 = denorm_bbox(b, w, h)
        except Exception:
            continue

        # 赤枠
        draw.rectangle([x0, y0, x1, y1], outline=(255, 0, 0, 255), width=3)

        # 問番号ラベル（枠の左上）
        if show_labels:
            dy = (i % 3) * 36
            draw.text((x0 + 4, y0 + 4 + dy), str(qid), fill=(255, 0, 0, 255), font=font_label)
            i += 1

        # 枠内OCR値（半透明）
        if show_values and qid_to_value is not None:
            raw = qid_to_value.get(qid, "")
            txt = "" if raw is None else str(raw).strip()
            if txt == "":
                txt = "空"  # 未回答を見落としにくくする

            # 長い場合は省略（最適化はしない方針なので単純に切る）
            if len(txt) > value_max_chars:
                txt = txt[:value_max_chars] + "…"

            # 枠の中央に配置（枠が小さいと読めないがOK）
            tw, th =  _text_wh(draw, txt, font_value)
            cx = (x0 + x1) // 2
            cy = (y0 + y1) // 2
            tx = x0 + 50
            ty = cy - th // 2

            # 半透明色（青系）※必要なら黒でもOK
            draw.text((tx, ty), txt, fill=(0, 0, 0, value_alpha), font=font_value)

    # 合成してRGBで返す
    out = Image.alpha_composite(base, overlay).convert("RGB")
    return out

@st.cache_data(show_spinner=False)
def load_template_from_bytes(tpl_bytes: bytes) -> dict:
    return json.loads(tpl_bytes.decode("utf-8"))

@st.cache_data(show_spinner=False)
def load_master_from_bytes(csv_bytes: bytes) -> pd.DataFrame:
    m = pd.read_csv(BytesIO(csv_bytes), dtype=str, keep_default_na=False)
    for col in ["設問ID", "設問文", "形式", "type", "選択肢"]:
        if col not in m.columns:
            m[col] = ""
    return m

@st.cache_data(show_spinner=False)
def load_ocr_csv_from_bytes(csv_bytes: bytes) -> pd.DataFrame:
    df = pd.read_csv(BytesIO(csv_bytes), dtype=str, keep_default_na=False)
    if "回答者番号" not in df.columns:
        df.insert(0, "回答者番号", [str(i) for i in range(1, len(df) + 1)])
    else:
        df["回答者番号"] = df["回答者番号"].astype(str)
    return df

@st.cache_data(show_spinner=False)
def pdf_page_count_from_bytes(pdf_bytes: bytes) -> int:
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    return doc.page_count

@st.cache_resource
def open_pdf(pdf_bytes: bytes):
    return fitz.open(stream=pdf_bytes, filetype="pdf")


def render_page(doc, page_index: int, dpi: int):
    page = doc.load_page(page_index)
    zoom = dpi / 72
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
    return Image.frombytes("RGB", [pix.width, pix.height], pix.samples)


def build_page_map(template: dict) -> dict:
    pages = template.get("pages", {})
    return {pno: list(qmap.keys()) for pno, qmap in pages.items()}

def parse_choices(choice_str: str):
    allowed = set()
    if not choice_str:
        return allowed
    parts = choice_str.split("|")
    for p in parts:
        m = re.match(r"\s*([0-9]+)\s*:", p)
        if m:
            allowed.add(m.group(1))
    return allowed

def flag_cell(qid: str, val: str, meta: dict):
    v = "" if val is None else str(val).strip()
    info = meta.get(norm_qid(qid), {})
    typ = info.get("type", "other")
    allowed = info.get("allowed", set())

    # 未回答は必ず⚠
    if v == "":
        return True, "未回答（空欄）"

    if typ == "single":
        nums = re.findall(r"\d+", v)
        if len(nums) != 1:
            return True, "単一選択なのに複数/解釈不能"
        if allowed and nums[0] not in allowed:
            return True, f"単一選択の範囲外: {nums[0]}"
        return False, ""

    if typ == "multi":
        nums = re.findall(r"\d+", v)
        if len(nums) == 0:
            return True, "複数選択なのに解釈不能"
        if allowed:
            bad = [n for n in nums if n not in allowed]
            if bad:
                return True, f"複数選択の範囲外: {','.join(bad)}"
        return False, ""

    return False, ""

# =========================
# UI
# =========================
st.set_page_config(layout="wide")
st.markdown("### アンケート OCR 修正ページレビュア（チェックポイント付き）")

with st.sidebar:
    st.header("入力（アップロード）")
    up_ocr = st.file_uploader("OCR出力CSV", type=["csv"])
    up_tpl = st.file_uploader("template.json", type=["json"])
    up_pdf = st.file_uploader("回答済みPDF", type=["pdf"])
    up_master = st.file_uploader("設問マスタCSV（任意）", type=["csv"])

    st.divider()
    st.header("表示")
    dpi = st.slider("PDF→画像 DPI", 150, 350, 220, 10)
    page_zoom = st.slider("ページ全体の表示倍率", 50, 200, 100, 10)

    st.divider()
    st.subheader("照合オーバーレイ")
    show_boxes = st.checkbox("設問領域の赤枠を表示", value=True)
    show_labels = st.checkbox("問番号ラベルを表示", value=True)
    st.subheader("OCR値の枠内表示")
    show_values = True
    value_font_size = st.slider("値の文字サイズ", 16, 80, 48, 1)
    value_alpha = st.slider("値の透明度（薄いほど透ける）", 20, 160, 80, 5)  # 0..255
    value_max_chars = st.slider("値の最大文字数", 6, 20, 12, 1)
    st.divider()
    st.header("ページ割り当て")
    pages_per_resp = st.number_input(
        "1人あたりページ数（表紙含む）", min_value=1, value=16, step=1, key="pages_per_resp_ui"
    )
    cover_pages = st.number_input(
        "表紙ページ数（通常1）", min_value=0, value=1, step=1, key="cover_pages_ui"
    )

    st.divider()
    st.header("チェックポイント")
    auto_cp = st.checkbox("自動チェックポイントを有効化", value=True)
    auto_cp_min = st.number_input("自動保存間隔（分）", min_value=1, value=10, step=1)
    st.caption("※未反映があるときだけ、操作タイミングで自動保存します。")

    if st.button("🔄 キャッシュをクリア", width="stretch"):
        st.cache_data.clear()
        st.success("キャッシュをクリアしました。")
        st.rerun()

# 必須入力
if not (up_ocr and up_tpl and up_pdf):
    st.info("左で **OCR出力CSV / template.json / 回答済みPDF** をアップロードしてください。")
    st.stop()

base = stem_from_name(up_ocr.name, fallback="ocr_output")

ocr_bytes = up_ocr.getvalue()
tpl_bytes = up_tpl.getvalue()
pdf_bytes = up_pdf.getvalue()
master_bytes = up_master.getvalue() if up_master else None

template = load_template_from_bytes(tpl_bytes)
page_map = build_page_map(template)

df_raw = load_ocr_csv_from_bytes(ocr_bytes)

doc = open_pdf(pdf_bytes)
total_pages = doc.page_count

# 復元（CSV）
if "restore_path" in st.session_state and st.session_state.restore_path:
    try:
        df_raw = pd.read_csv(st.session_state.restore_path, dtype=str, keep_default_na=False)
        st.success(f"自動保存から復元しました: {Path(st.session_state.restore_path).name}")
    except Exception as e:
        st.error(f"復元に失敗: {e}")

# 編集データ保持（CSVが変わったら初期化）
session_key = f"df_edit::{up_ocr.name}"
if "df_edit_key" not in st.session_state or st.session_state.df_edit_key != session_key:
    st.session_state.df_edit = df_raw.copy()
    st.session_state.df_edit_key = session_key
    st.session_state.dirty = False
    st.session_state.page_dirty = False
    st.session_state.page_dirty_count = 0
    st.session_state.restore_path = ""
    st.session_state.checked = {}
    st.session_state.last_checkpoint_time = 0.0
    st.session_state.last_checkpoint_csv = ""
    st.session_state.last_checkpoint_reason = ""

df_edit: pd.DataFrame = st.session_state.df_edit

# 自動保存先（反映用）
if "autosave_path" not in st.session_state or not st.session_state.autosave_path:
    datestr = datetime.now().strftime("%Y%m%d")
    st.session_state.autosave_path = str(AUTOSAVE_DIR / f"{base}_{datestr}_autosave.csv")

# メタ（type・選択肢）
meta = {}
if master_bytes:
    mdf = load_master_from_bytes(master_bytes)
    qid_col = None
    for c in ["設問ID", "qid", "QID", "設問番号", "問ID"]:
        if c in mdf.columns:
            qid_col = c
            break
    if qid_col:
        for _, r in mdf.iterrows():
            qid = str(r.get(qid_col, "")).strip()
            if not qid:
                continue
            typ = str(r.get("type", "")).strip().lower()
            if typ not in ("single", "multi", "other"):
                typ = "other"
            choice_str = str(r.get("選択肢", "")).strip()
            allowed = parse_choices(choice_str)
            meta[norm_qid(qid)] = {"type": typ, "allowed": allowed}

# タブ
tabs = st.tabs(["① ページレビュー", "② 修正キュー", "③ 全体表（参考）", "④ 出力（ダウンロード）"])

# サイドバー後半（復元UI・チェックポイントUI）は df_edit ができてから出したいので、ここで描画する
with st.sidebar:
    st.divider()
    st.subheader("💾 一時保存（手動チェックポイント）")
    # 未反映でも押せる
    if st.button("💾 いまの状態を一時保存", width="stretch"):
        cp_csv, cp_prog = save_checkpoint(base, df_edit, reason="manual")
        st.success(f"保存しました: {Path(cp_csv).name}")

    if st.session_state.get("last_checkpoint_csv"):
        st.caption(f"最新チェックポイント: {Path(st.session_state.last_checkpoint_csv).name}")

    st.divider()
    st.subheader("自動保存（復元）")
    autosaves = sorted(AUTOSAVE_DIR.glob("*_autosave.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
    if autosaves:
        pick = st.selectbox("復元する自動保存ファイル", autosaves, format_func=lambda p: p.name)
        if st.button("復元する", width="stretch"):
            st.session_state.restore_path = str(pick)
            st.success(f"復元対象をセット: {pick.name}")
            st.rerun()
    else:
        st.caption("自動保存はまだありません。")

    st.divider()
    st.subheader("作業位置（再開）")
    pfiles = sorted(AUTOSAVE_DIR.glob(f"{base}_*_progress.json"), key=lambda p: p.stat().st_mtime, reverse=True)

    if pfiles:
        p_pick = st.selectbox("再開用 progress.json", pfiles, format_func=lambda p: p.name)
        if st.button("▶ 位置を復元して再開", width="stretch"):
            prog = load_progress(p_pick)
            st.session_state["pending_restore"] = {
                "pages_per_resp": prog.get("pages_per_resp", 16),
                "cover_pages": prog.get("cover_pages", 1),
                "checked": prog.get("checked", {}),
                "autosave_path": prog.get("autosave_path", ""),
                "current_resp": prog.get("current_resp", ""),
                "current_page": prog.get("current_page", ""),
            }
            st.success("作業位置を復元しました。")
            st.rerun()
    else:
        st.caption("progress.json がまだありません（反映やチェックポイント保存で作成されます）。")

# =========================
# ① ページレビュー
# =========================
with tabs[0]:
    colA, colB = st.columns([1, 2], gap="large")

    with colA:
        st.subheader("対象の選択")

        is_page_dirty = bool(st.session_state.get("page_dirty", False))
        dirty_count = int(st.session_state.get("page_dirty_count", 0))

        # 未反映時は大きく注意＋チェックポイント導線
        if is_page_dirty:
            st.error(f"未反映の修正があります（{dirty_count}件）。反映するか、チェックポイント保存してから続けてください。")
            if st.button("💾 未反映のまま一時保存（チェックポイント）", width="stretch"):
                cp_csv, cp_prog = save_checkpoint(base, df_edit, reason="unsaved")
                st.success(f"保存しました: {Path(cp_csv).name}")

        resp_list = df_edit["回答者番号"].astype(str).tolist()
        if "current_resp" not in st.session_state:
            st.session_state.current_resp = resp_list[0]
        if st.session_state.current_resp not in resp_list:
            st.session_state.current_resp = resp_list[0]
        ridx = resp_list.index(st.session_state.current_resp)

        c1, c2 = st.columns(2)
        with c1:
            if st.button("← 前の回答者", width="stretch", disabled=is_page_dirty):
                st.session_state.current_resp = resp_list[max(0, ridx - 1)]
        with c2:
            if st.button("次の回答者 →", width="stretch", disabled=is_page_dirty):
                st.session_state.current_resp = resp_list[min(len(resp_list) - 1, ridx + 1)]

        resp = st.selectbox("回答者番号", resp_list, key="current_resp", disabled=is_page_dirty)

        logical_pages = sorted([int(k) for k in page_map.keys()])
        if "current_page" not in st.session_state:
            st.session_state.current_page = logical_pages[0]
        if st.session_state.current_page not in logical_pages:
            st.session_state.current_page = logical_pages[0]
        pidx = logical_pages.index(st.session_state.current_page)

        p1, p2 = st.columns(2)
        with p1:
            if st.button("← 前ページ", width="stretch", disabled=is_page_dirty):
                st.session_state.current_page = logical_pages[max(0, pidx - 1)]
        with p2:
            if st.button("次ページ →", width="stretch", disabled=is_page_dirty):
                st.session_state.current_page = logical_pages[min(len(logical_pages) - 1, pidx + 1)]

        page_no = st.selectbox("設問ページ（論理ページ）", logical_pages, key="current_page", disabled=is_page_dirty)

        # 回答者番号が6始まりでもOK：選択順でブロック先頭を計算
        resp_idx = resp_list.index(str(resp))
        start_page = resp_idx * int(pages_per_resp)
        target_page_index = start_page + int(cover_pages) - 1 + int(page_no)

        st.caption(f"PDFページindex: {target_page_index}（resp_idx={resp_idx}, start={start_page}, cover={cover_pages}, logical={page_no}）")

        if target_page_index < 0 or target_page_index >= total_pages:
            st.error("ページ範囲外です。pages_per_resp / cover_pages を見直してください。")
            st.stop()

        qids = [q for q in page_map.get(str(page_no), []) if q in df_edit.columns]
        rix = df_edit.index[df_edit["回答者番号"].astype(str) == str(resp)][0]

        rows = []
        for qid in qids:
            now = df_edit.at[rix, qid]
            flg, reason = flag_cell(qid, now, meta)
            rows.append({
                "設問ID": qid,
                "現在値": "" if now is None else str(now),
                "修正値": "" if now is None else str(now),
                "⚠": "⚠" if flg else "",
                "理由": reason,
            })
        page_df = pd.DataFrame(rows)

        st.divider()
        st.subheader("ページ内の回答（編集）")
        st.caption("表で修正したら「このページの修正を反映」を押してください。未反映の間は移動できません。")

        editor_key = f"page_editor_{resp}_{page_no}"

        def mark_dirty():
            st.session_state.page_dirty = True

        edited = st.data_editor(
            page_df,
            key=editor_key,
            width="stretch",
            hide_index=True,
            disabled=["設問ID", "現在値", "⚠", "理由"],
            on_change=mark_dirty,
        )
        # --- 差分プレビュー（修正値を赤字）: jinja2不要版 ---
        diff_only = edited[edited["修正値"].fillna("") != edited["現在値"].fillna("")][
            ["設問ID", "現在値", "修正値", "⚠", "理由"]
        ].copy()

        st.caption("差分プレビュー（修正値が赤字＝未反映。反映すると消えます）")

        if len(diff_only) == 0:
            st.write("差分はありません。")
        else:
            rows_html = []
            for _, r in diff_only.iterrows():
                rows_html.append(
                    "<tr>"
                    f"<td>{r['設問ID']}</td>"
                    f"<td>{r['現在値']}</td>"
                    f"<td style='color:red;font-weight:700'>{r['修正値']}</td>"
                    f"<td>{r['⚠']}</td>"
                    f"<td>{r['理由']}</td>"
                    "</tr>"
                )

            table_html = (
                "<div style='max-height:320px; overflow:auto; border:1px solid #ddd; padding:6px; border-radius:6px;'>"
                "<table style='width:100%; border-collapse:collapse; font-size:0.95rem;'>"
                "<thead><tr>"
                "<th style='border-bottom:1px solid #ccc; text-align:left; padding:4px;'>設問ID</th>"
                "<th style='border-bottom:1px solid #ccc; text-align:left; padding:4px;'>現在値</th>"
                "<th style='border-bottom:1px solid #ccc; text-align:left; padding:4px;'>修正値</th>"
                "<th style='border-bottom:1px solid #ccc; text-align:left; padding:4px;'>⚠</th>"
                "<th style='border-bottom:1px solid #ccc; text-align:left; padding:4px;'>理由</th>"
                "</tr></thead>"
                "<tbody>"
                + "".join(rows_html) +
                "</tbody></table></div>"
            )
            st.markdown(table_html, unsafe_allow_html=True)

        changed_mask = (edited["修正値"].fillna("") != edited["現在値"].fillna(""))
        dirty_now = bool(changed_mask.any())
        dirty_count_now = int(changed_mask.sum())
        st.session_state.page_dirty = dirty_now
        st.session_state.page_dirty_count = dirty_count_now

        # 自動チェックポイント（未反映があるときだけ）
        if auto_cp and dirty_now:
            last = float(st.session_state.get("last_checkpoint_time", 0.0))
            interval = int(auto_cp_min) * 60
            if time.time() - last >= interval:
                save_checkpoint(base, df_edit, reason="auto")

        if dirty_now:
            st.warning(f"⚠ 未反映の修正があります（{dirty_count_now}件）。反映または一時保存をしてください。")

        apply_clicked = st.button(
            "このページの修正を反映",
            width="stretch",
            disabled=(not dirty_now),
        )

        if apply_clicked:
            for _, rr in edited.iterrows():
                q = rr["設問ID"]
                df_edit.at[rix, q] = str(rr["修正値"]).strip()

            # チェック済み登録（resp,page）
            resp_key = str(resp)
            page_key = int(page_no)
            checked = st.session_state.get("checked", {})
            checked.setdefault(resp_key, [])
            if page_key not in checked[resp_key]:
                checked[resp_key].append(page_key)
                checked[resp_key] = sorted(checked[resp_key])
            st.session_state.checked = checked

            st.session_state.dirty = True
            st.session_state.page_dirty = False
            st.session_state.page_dirty_count = 0

            # 反映保存（確定）
            df_edit.to_csv(st.session_state.autosave_path, index=False, encoding="utf-8-sig")
            save_progress_file(progress_path_for(base), autosave_path=st.session_state.autosave_path)

            st.success(f"反映＋自動保存しました：{Path(st.session_state.autosave_path).name}")
            st.rerun()

    with colB:
        st.subheader("ページ全体画像（照合）")
        full_img = render_page(doc, target_page_index, dpi=int(dpi))

        img_to_show = full_img
        if show_boxes:
            page_tpl = template.get("pages", {}).get(str(page_no), {})
            qid_to_bbox = {qid: page_tpl[qid] for qid in qids if qid in page_tpl}
            qid_to_value = {qid: df_edit.at[rix, qid] for qid in qids if qid in df_edit.columns}

            img_to_show = draw_overlay_boxes(
                full_img,
                qid_to_bbox=qid_to_bbox,
                qid_to_value=qid_to_value,
                show_labels=show_labels,
                show_values=show_values,               # サイドバーのチェック
                value_font_size=value_font_size,
                value_alpha=value_alpha,
                value_max_chars=value_max_chars,
            )
        page_w = img_to_show.size[0]
        page_disp_w = int(page_w * page_zoom / 100)

        st.image(img_to_show, caption=f"ページ全体（PDF index={target_page_index}）", width=page_disp_w)

# =========================
# ② 修正キュー（未チェックのみ）
# =========================
with tabs[1]:
    st.subheader("修正キュー（要確認セル：未チェックページのみ）")
    st.caption("⚠ 判定のうち、まだチェックしていないページ由来だけを表示します。")

    resp_list = df_edit["回答者番号"].astype(str).tolist()
    q_resp = st.selectbox("対象回答者（キュー）", resp_list, key="queue_resp")

    checked = st.session_state.get("checked", {})
    checked_pages = set(checked.get(str(q_resp), []))

    rix = df_edit.index[df_edit["回答者番号"].astype(str) == str(q_resp)][0]

    qid_to_page = {}
    for pno, qids in page_map.items():
        for q in qids:
            if q not in qid_to_page:
                qid_to_page[q] = int(pno)

    queue_rows = []
    for col in df_edit.columns:
        if col == "回答者番号":
            continue
        val = df_edit.at[rix, col]
        flg, reason = flag_cell(col, val, meta)
        if not flg:
            continue
        page_of_q = qid_to_page.get(col, None)
        if page_of_q is not None and page_of_q in checked_pages:
            continue
        queue_rows.append({
            "設問ID": col,
            "ページ": page_of_q if page_of_q is not None else "",
            "現在値": val,
            "理由": reason,
        })

    if queue_rows:
        qdf = pd.DataFrame(queue_rows).sort_values(["ページ", "設問ID"])
        st.dataframe(qdf, width="stretch", height=460)
    else:
        st.success("未チェックの要確認はありません。")

# =========================
# ③ 全体表（参考）
# =========================
with tabs[2]:
    st.subheader("全体データ（参考表示）")
    st.dataframe(df_edit, width="stretch", height=520)

# =========================
# ④ 出力（ダウンロード）
# =========================
with tabs[3]:
    st.subheader("修正後CSVの出力")
    st.write("編集中:", "✅" if st.session_state.get("dirty", False) else "（変更なし）")

    datestr = datetime.now().strftime("%Y%m%d")
    out_name = f"{base}_{datestr}.csv"

    csv_bytes = df_edit.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        label=f"修正後CSVをダウンロード（{out_name}）",
        data=csv_bytes,
        file_name=out_name,
        mime="text/csv",
    )
