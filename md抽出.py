import streamlit as st
import io
import re

st.set_page_config(page_title="Markdown見出し抽出ツール", layout="wide")

st.title("♯ Markdown見出し抽出ツール")
st.write("アップロードされたファイルから `#` で始まる行（見出し）のみを抽出します。")

# 1. ファイルアップロード
uploaded_file = st.file_uploader("Markdownファイルをアップロードしてください", type=["md", "txt"])

if uploaded_file is not None:
    # ファイル内容の読み込み
    content = uploaded_file.getvalue().decode("utf-8")
    
    # 2. 抽出ロジック
    # YAMLブロックなどのコードブロック内にある # を無視するため、
    # 1行ずつ判定する際に「コードブロック外であること」を考慮します
    lines = content.splitlines()
    extracted_headings = []
    is_inside_code_block = False

    for line in lines:
        # コードブロック（```）の開始・終了を判定
        if line.strip().startswith("```"):
            is_inside_code_block = not is_inside_code_block
            continue
        
        # コードブロック外で、かつ # で始まる行を抽出
        if not is_inside_code_block:
            if line.strip().startswith("#"):
                extracted_headings.append(line)

    # 3. 結果の表示
    if extracted_headings:
        st.subheader("📋 抽出された見出し一覧")
        
        # プレビュー表示
        result_text = "\n".join(extracted_headings)
        st.code(result_text, language="markdown")
        
        st.info(f"合計 {len(extracted_headings)} 行の見出しが見つかりました。")

        # 4. ダウンロード機能
        st.download_button(
            label="💾 抽出結果を保存 (.txt)",
            data=result_text,
            file_name=f"headings_{uploaded_file.name}",
            mime="text/plain"
        )
    else:
        st.warning("見出し（# で始まる行）が見つかりませんでした。")

else:
    st.info("左側のボックスにファイルをドラッグ＆ドロップしてください。")