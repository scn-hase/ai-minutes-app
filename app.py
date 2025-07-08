import streamlit as st
import os
import datetime
import io
from google.cloud import storage
import vertexai
from vertexai.generative_models import GenerativeModel, Part
from google.oauth2 import service_account
from docx import Document

# === アプリのUI部分 ===
st.title("AI議事録作成アプリ 📄✍️")
st.markdown("""
このアプリは、音声ファイルをアップロードするだけで、AIが自動で文字起こしと議事録の作成を行います。
""")

# ファイルアップロードのウィジェット
uploaded_file = st.file_uploader(
    "議事録を作成したい音声・動画ファイル（MP3, WAV, M4A, MP4）をアップロードしてください。",
    type=["mp3", "wav", "m4a", "mp4"]
)

# === メインの処理は、すべてこの if ブロックの中に入れる ===
if uploaded_file is not None:
    st.success(f"ファイル「{uploaded_file.name}」がアップロードされました。処理を開始します。")

    # --- 1. 認証と初期化 ---
    with st.spinner("認証と初期設定を行っています..."):
        try:
            creds_dict = st.secrets["gcp_service_account"]
            creds = service_account.Credentials.from_service_account_info(creds_dict)
            storage_client = storage.Client(credentials=creds)
            project_id = "gizirokuapp"
            location = "asia-northeast1"  # 東京リージョン
            vertexai.init(project=project_id, location=location, credentials=creds)
        except (FileNotFoundError, KeyError):
            st.info("ローカル環境として実行します。")
            storage_client = storage.Client()
            project_id = "gizirokuapp"
            location = "asia-northeast1"  # 東京リージョン
            vertexai.init(project=project_id, location=location)

    # --- 2. GCSへのファイルアップロード ---
    gcs_uri = None
    with st.spinner("ファイルをクラウドにアップロード中..."):
        bucket_name = "scn-giziroku-tokyo"
        bucket = storage_client.bucket(bucket_name)
        timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        blob_name = f"{timestamp}-{uploaded_file.name}"
        blob = bucket.blob(blob_name)
        blob.upload_from_file(uploaded_file, content_type=uploaded_file.type)
        gcs_uri = f"gs://{bucket_name}/{blob_name}"
        st.info(f"ファイルのアップロードが完了しました: {gcs_uri}")

    # --- 3. AIによる文字起こし ---
    transcribed_text = None
    with st.spinner("AIが音声を文字起こし中です... この処理には数分かかることがあります。"):
        model = GenerativeModel(model_name="gemini-1.5-flash-preview-0514") # 推奨モデル
        #audio_file = Part.from_uri(mime_type=uploaded_file.type, uri=gcs_uri)
        #prompt = "この音声ファイルを日本語で文字起こししてください。"
        #response = model.generate_content([audio_file, prompt])
        st.info("デバッグ中：音声ファイルの代わりに、シンプルなテキストでAPIをテストします。")
        test_prompt = "空の色は何色ですか？一言で答えてください。"
        response = model.generate_content(test_prompt)
        transcribed_text = response.text
        st.subheader("文字起こし結果")
        st.write(transcribed_text)

    # --- 4. AIによる議事録生成 ---
    generated_minutes = None
    with st.spinner("AIが議事録を生成中です..."):
        prompt_for_minutes = f"""
        以下の会議の文字起こしテキストを元に、プロフェッショナルな議事録を作成してください。
        以下のフォーマットに従って、要点を明確にまとめてください。
        # 議事録
        ## 1. 会議の要約
        （会議全体のサマリーを3〜5行で記述）
        ## 2. 決定事項
        （会議で決定された事項を箇条書きでリストアップ）
        ## 3. ToDoリスト（担当者と期限）
        （発生したタスクを箇条書きでリストアップし、誰がいつまでに行うかを明記）
        ---
        # 文字起こしテキスト
        {transcribed_text}
        """
        response_minutes = model.generate_content(prompt_for_minutes)
        generated_minutes = response_minutes.text
        st.subheader("生成された議事録")
        st.markdown(generated_minutes)

    # --- 5. Wordファイル出力 ---
    with st.spinner("Wordファイルを生成中です..."):
        document = Document()
        document.add_heading('AI自動生成議事録', 0)
        document.add_heading('生成された議事録', level=1)
        # MarkdownテキストをパースしてWordに追加
        for line in generated_minutes.split('\n'):
            if line.startswith('### '):
                document.add_heading(line.replace('### ', ''), level=3)
            elif line.startswith('## '):
                document.add_heading(line.replace('## ', ''), level=2)
            elif line.startswith('# '):
                document.add_heading(line.replace('# ', ''), level=1)
            elif line.startswith('- '):
                document.add_paragraph(line, style='List Bullet')
            else:
                document.add_paragraph(line)
        document.add_page_break()
        document.add_heading('文字起こし全文', level=1)
        document.add_paragraph(transcribed_text)
        
        # Wordファイルをメモリ上に保存
        file_stream = io.BytesIO()
        document.save(file_stream)
        file_stream.seek(0)
    
    st.success("すべての処理が完了しました！")

    # ダウンロードボタン
    st.download_button(
        label="議事録をWordファイルでダウンロード",
        data=file_stream,
        file_name=f"議事録_{os.path.splitext(uploaded_file.name)[0]}.docx",
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )