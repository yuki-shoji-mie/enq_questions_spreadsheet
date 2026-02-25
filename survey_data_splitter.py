import streamlit as st
import pandas as pd
import re
import io

st.set_page_config(page_title="アンケートデータ分割ツール", layout="wide")

st.title("📊 アンケートデータ「:」分割ツール")
st.markdown("""
このツールは、アンケート調査結果のCSVファイルから、「数値:テキスト」形式のセルを検出し、
":"で分割して新しい列にテキスト部分を追加します。
""")

# ファイルアップロード
uploaded_file = st.file_uploader("CSVファイルをアップロード", type=['csv'])

if uploaded_file is not None:
    # CSVファイルを読み込み
    try:
        df = pd.read_csv(uploaded_file, encoding='utf-8-sig')
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
            # 分割されたセルを記録
            split_info = []
            
            # 新しいデータフレームを作成（元のデータをコピー）
            df_processed = df.copy()
            
            # 各列を処理
            new_columns_data = {}  # 新しい列のデータを保存
            
            for col in df.columns:
                # 新しい列のデータ初期化
                text_column_data = [None] * len(df)
                has_split = False
                
                # 各行を処理
                for idx, value in enumerate(df[col]):
                    if pd.isna(value):
                        continue
                    
                    value_str = str(value)
                    
                    # ":"を含むかチェック
                    if ':' in value_str:
                        # ":"で分割
                        parts = value_str.split(':', 1)
                        
                        if len(parts) == 2:
                            left_part = parts[0].strip()
                            right_part = parts[1].strip()
                            
                            # 左側が数値またはコンマ区切りの数値かチェック
                            # 例: "14", "6,12", "1,2,3"
                            if re.match(r'^[\d,\s]+$', left_part):
                                # 分割を実行
                                df_processed.at[idx, col] = left_part
                                text_column_data[idx] = right_part
                                has_split = True
                                
                                # 分割情報を記録
                                split_info.append({
                                    '行': idx + 2,  # ヘッダー行を考慮して+2
                                    '列': col,
                                    '元の値': value_str[:50] + '...' if len(value_str) > 50 else value_str,
                                    '数値部分': left_part,
                                    'テキスト部分': right_part[:50] + '...' if len(right_part) > 50 else right_part
                                })
                
                # この列で分割があった場合、新しい列を追加
                if has_split:
                    new_col_name = f"{col}_テキスト"
                    new_columns_data[new_col_name] = text_column_data
            
            # 新しい列を元の列の右隣に挿入
            for col in df.columns:
                new_col_name = f"{col}_テキスト"
                if new_col_name in new_columns_data:
                    # 元の列の位置を取得
                    col_idx = df_processed.columns.get_loc(col)
                    # 新しい列を挿入
                    df_processed.insert(col_idx + 1, new_col_name, new_columns_data[new_col_name])
        
        # 処理結果を表示
        st.success(f"✅ 処理完了: {len(split_info)}個のセルを分割しました")
        
        # 分割情報を表示
        if split_info:
            with st.expander(f"🔍 分割されたセルの詳細 ({len(split_info)}件)", expanded=True):
                split_df = pd.DataFrame(split_info)
                st.dataframe(split_df, use_container_width=True)
        else:
            st.info("ℹ️ 「数値:テキスト」形式のセルは見つかりませんでした")
        
        # 処理後のデータを表示
        with st.expander("📄 処理後のデータを表示", expanded=True):
            st.dataframe(df_processed, use_container_width=True)
        
        # ダウンロードボタン
        st.markdown("---")
        col1, col2 = st.columns(2)
        
        with col1:
            # 処理後のCSVをダウンロード
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
            # 分割情報をダウンロード
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
    
    # 使い方の説明
    with st.expander("📖 使い方"):
        st.markdown("""
        ### 処理内容
        
        このツールは以下の処理を行います：
        
        1. **セルの検出**: "数値:テキスト" 形式のセルを検出
           - 例: `14:外国人が増えすぎていること`
           - 例: `6,12:日本人向けは充実していないからな`
        
        2. **分割処理**: ":"で左右に分割
           - 左側（数値部分）: 元の列に残す
           - 右側（テキスト部分）: 新しい列に追加
        
        3. **新しい列**: 元の列名に「_テキスト」を付けた列名で、元の列の右隣に挿入
        
        ### 対象となるセル
        
        - ":"を含むセル
        - ":"の左側が数値または数値をコンマで区切った文字列
        - ":"の右側がテキスト
        
        ### 使用例
        
        **元のデータ:**
        ```
        Q5列: "14:外国人が増えすぎていること"
        ```
        
        **処理後:**
        ```
        Q5列: "14"
        Q5_テキスト列: "外国人が増えすぎていること"
        ```
        """)
