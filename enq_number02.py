import streamlit as st
import fitz  # PyMuPDF
import io
import os

def add_numbering_with_fitz(pdf_bytes, pages_per_doc, start_number):
    # メモリ効率を考え、ストリームで開く
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    total_pages = len(doc)
    num_docs = total_pages // pages_per_doc

    for i in range(num_docs):
        # 開始番号から採番（4桁表示）
        current_number = start_number + i
        doc_number_str = f"{current_number:04d}"

        start_idx = i * pages_per_doc

        if start_idx < total_pages:
            page = doc[start_idx]
            rect = page.rect  # 標準化されたA4サイズ (595 x 842)

            # 再PDF化後の標準A4に合わせた右上の位置
            # 右端から100pt、上端から50pt
            text_x = rect.width - 100
            text_y = 50

            try:
                # 最も安全な標準フォント（Helvetica）を使用
                page.insert_text(
                    (text_x, text_y),
                    doc_number_str,
                    fontsize=32,
                    color=(0, 0, 0),
                    fontname="helv",
                    rotate=0,
                    overlay=True
                )
            except Exception:
                # 万が一フォント名でエラーが出る場合は、デフォルト設定で書き込む
                page.insert_text(
                    (text_x, text_y),
                    doc_number_str,
                    fontsize=32,
                    rotate=0,
                    overlay=True
                )

    # garbage=3 で不要なオブジェクトを削除し、deflate=True で圧縮
    return doc.tobytes(garbage=3, deflate=True)

# --- UI ---
st.set_page_config(page_title="調査票ナンバリング・確定版")
st.title("アンケート調査票ナンバリングツール")

uploaded_file = st.file_uploader("再PDF化したファイルをアップロードしてください", type="pdf")
pages_per_doc = st.number_input("1部あたりのページ数（例：4）", min_value=1, value=4)

# ★追加：開始番号（初期番号）
start_number = st.number_input("開始番号（例：1 → 0001、25 → 0025）", min_value=1, value=1)

if uploaded_file is not None:
    if st.button("ナンバリングを実行"):
        with st.spinner("重いファイルを処理中..."):
            try:
                input_data = uploaded_file.read()
                output_pdf = add_numbering_with_fitz(input_data, pages_per_doc, start_number)

                st.success("成功しました！")
                # 入力ファイル名（拡張子除く） + "nm" + ".pdf" にする
                base_name, _ = os.path.splitext(uploaded_file.name)
                output_name = f"{base_name}nm.pdf"

                st.download_button(
                    label="ダウンロード",
                    data=output_pdf,
                    file_name=output_name,
                    mime="application/pdf"
                )
            except Exception as e:
                st.error(f"エラーが発生しました: {e}")
