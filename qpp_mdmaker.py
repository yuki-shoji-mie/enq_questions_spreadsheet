import streamlit as st
import pandas as pd
import io

st.set_page_config(page_title="アンケート定義ファイル作成ツール", layout="wide")

st.title("📝 アンケートMD/YAML生成ツール")
st.write("QuestionsとChoicesのシートを読み込み、n8nと同じ形式のMarkdownを出力します。")

# 1. ファイルアップロード（2つのファイルを指定）
col1, col2 = st.columns(2)
with col1:
    q_file = st.file_uploader("Questions（設問）ファイルをアップロード", type=["csv", "xlsx"])
with col2:
    c_file = st.file_uploader("Choices（選択肢）ファイルをアップロード", type=["csv", "xlsx"])

if q_file and c_file:
    # データの読み込み
    def load_data(file):
        if file.name.endswith('.csv'):
            try: return pd.read_csv(file, encoding='utf-8')
            except: return pd.read_csv(file, encoding='cp932')
        else:
            return pd.read_excel(file)

    df_q = load_data(q_file)
    df_c = load_data(c_file)

    # カラム名の空白除去と正規化
    df_q.columns = [c.strip() for c in df_q.columns]
    df_c.columns = [c.strip() for c in df_c.columns]

    st.success("ファイルの読み込みに成功しました。")

    # 2. Markdown生成ロジック
    def generate_markdown(questions, choices):
        md_output = "# 設問定義\n\n"
        
        # 選択肢をqkeyでグループ化
        choice_map = {}
        for _, row in choices.iterrows():
            key = str(row.get('qkey', '')).strip()
            if not key: continue
            if key not in choice_map: choice_map[key] = []
            choice_map[key].append(row)

        # 設問ループ
        for _, q in questions.iterrows():
            qid = str(q.get('qid', 'N/A'))
            qkey = str(q.get('qkey', 'undefined'))
            level = int(q.get('q_level', 2))
            title = str(q.get('question', ''))

            # 見出し生成
            header = "## " if level <= 2 else "### "
            md_output += f"{header}{qid} {title}\n\n"

            # YAMLブロック生成
            md_output += f"```yaml {{# {qkey} .qmeta}}\n"
            md_output += f"id: {qkey}\n"
            md_output += f"qid: {qid}\n"
            md_output += f"level: {level}\n"
            md_output += f"type: {q.get('type', 'SA')}\n"
            
            # 任意項目の追加
            for col in ['var_name', 'instruction', 'show_if']:
                val = q.get(col)
                if pd.notna(val) and val != "":
                    md_output += f"{col}: {val}\n"
            
            # tagsの処理
            tags = q.get('tags')
            if pd.notna(tags) and tags != "":
                tag_list = [f'"{t.strip()}"' for t in str(tags).split(',')]
                md_output += f"tags: [{', '.join(tag_list)}]\n"

            # 選択肢の紐付
            relevant = choice_map.get(qkey)
            if relevant:
                md_output += "choices:\n"
                # choice_noがあればソート
                relevant.sort(key=lambda x: x.get('choice_no', 0))
                for c in relevant:
                    md_output += f'  "{c.get("choice_value")}": "{c.get("choice_label")}"\n'

            md_output += "```\n\n"
        
        return md_output

    # 3. 実行とプレビュー
    if st.button("Markdownを生成する"):
        final_md = generate_markdown(df_q, df_c)
        
        st.subheader("📄 プレビュー")
        st.code(final_md, language="markdown")

        # ダウンロードボタン
        st.download_button(
            label="💾 Markdownファイルをダウンロード",
            data=final_md,
            file_name="survey_definition.md",
            mime="text/markdown"
        )
else:
    st.info("QuestionsとChoicesの2つのファイルをアップロードしてください。")