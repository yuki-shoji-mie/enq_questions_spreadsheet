import streamlit as st
import pandas as pd
import io
import chardet

st.set_page_config(page_title="アンケートデータ分割ツール", layout="wide")

st.title("📊 アンケートデータ「;」分割ツール")
st.markdown("""
このツールは、アンケート調査結果のCSVファイルから、「;」で区切られた複数回答セルを検出し、
選択肢ごとに別列に分割します。文字コードは自動判定します。
""")

# ファイルアップロード
uploaded_file = st.file_uploader("CSVファイルをアップロード", type=['csv'])

if uploaded_file is not None:
    # 文字コードを自動判定して読み込み
    try:
        raw_data = uploaded_file.read()
        detected = chardet.detect(raw_data)
        encoding = detected['encoding'] or 'cp932'
        st.info(f"🔍 文字コード自動判定: {encoding}（信頼度: {detected['confidence']:.0%}）")
        df = pd.read_csv(io.BytesIO(raw_data), encoding=encoding)
        st.success(f"✅ ファイルを読み込みました: {df.shape[0]}行 × {df.shape[1]}列")
    except Exception as e:
        st.error(f"ファイルの読み込みエラー: {e}")
        st.stop()

    # 元のデータを表示
    with st.expander("📄 元のデータを表示", expanded=False):
        st.dataframe(df, use_container_width=True)

    # 処理ボタン
    if st.button("🔄 データを処理する", type="primary"):
        with st.spinner("処理中..."):
            split_info = []
            df_processed = df.copy()
            insert_plan = []  # (元列名, 追加列名リスト, col_data)

            for col in df.columns:
                # 最大分割数を確認
                max_parts = 1
                for value in df[col]:
                    if pd.isna(value):
                        continue
                    value_str = str(value)
                    if ';' in value_str:
                        n = len(value_str.split(';'))
                        if n > max_parts:
                            max_parts = n

                if max_parts <= 1:
                    continue  # この列には「;」なし

                # 追加列の名前を生成（例: Q1_1, Q1_2, ...）
                new_col_names = [f"{col}_{i+1}" for i in range(max_parts)]
                col_data = {name: [None] * len(df) for name in new_col_names}

                for idx, value in enumerate(df[col]):
                    if pd.isna(value):
                        continue
                    value_str = str(value)
                    if ';' not in value_str:
                        col_data[new_col_names[0]][idx] = value_str.strip()
                        continue

                    parts = [p.strip() for p in value_str.split(';')]
                    for i, part in enumerate(parts):
                        col_data[new_col_names[i]][idx] = part

                    split_info.append({
                        '行': idx + 2,
                        '列': col,
                        '元の値': value_str[:80] + '...' if len(value_str) > 80 else value_str,
                        '分割数': len(parts),
                    })

                insert_plan.append((col, new_col_names, col_data))

            # 元の列の右隣に順番に挿入
            for col, new_col_names, col_data in insert_plan:
                base_idx = df_processed.columns.get_loc(col)
                for offset, new_col_name in enumerate(new_col_names):
                    df_processed.insert(base_idx + 1 + offset, new_col_name, col_data[new_col_name])

        # 処理結果を表示
        st.success(f"✅ 処理完了: {len(split_info)}件のセルを分割しました")

        if split_info:
            with st.expander(f"🔍 分割されたセルの詳細 ({len(split_info)}件)", expanded=True):
                split_df = pd.DataFrame(split_info)
                st.dataframe(split_df, use_container_width=True)
        else:
            st.info("ℹ️ 「;」区切りのセルは見つかりませんでした")

        with st.expander("📄 処理後のデータを表示", expanded=True):
            st.dataframe(df_processed, use_container_width=True)

        st.markdown("---")
        col1, col2 = st.columns(2)

        with col1:
            csv_buffer = io.StringIO()
            df_processed.to_csv(csv_buffer, index=False, encoding='utf-8-sig')
            csv_data = csv_buffer.getvalue().encode('utf-8-sig')
            st.download_button(
                label="📥 処理済みCSVをダウンロード",
                data=csv_data,
                file_name="processed_data.csv",
                mime="text/csv",
                type="primary"
            )

        with col2:
            if split_info:
                split_csv_buffer = io.StringIO()
                split_df.to_csv(split_csv_buffer, index=False, encoding='utf-8-sig')
                split_csv_data = split_csv_buffer.getvalue().encode('utf-8-sig')
                st.download_button(
                    label="📥 分割情報CSVをダウンロード",
                    data=split_csv_data,
                    file_name="split_info.csv",
                    mime="text/csv"
                )

else:
    st.info("👆 CSVファイルをアップロードしてください")

    with st.expander("📖 使い方"):
        st.markdown("""
        ### 処理内容

        1. **文字コード自動判定**: UTF-8 / Shift-JIS などを自動検出して読み込みます
        2. **セルの検出**: 「;」を含むセルをすべて対象にします
        3. **分割処理**: 「;」で分割し、選択肢ごとに別列（列名_1, 列名_2, ...）を生成
        4. **新しい列**: 元の列の右隣に順番に挿入

        ### 使用例

        **元のデータ（387:checkbox 列）:**
        ```
        １．Nombres de edificios;５．Cuestionario de consulta
        ```

        **処理後:**
        ```
        387:checkbox_1 列: "１．Nombres de edificios"
        387:checkbox_2 列: "５．Cuestionario de consulta"
        ```
        """)
