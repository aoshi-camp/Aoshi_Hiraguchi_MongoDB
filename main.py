import os
import re
from datetime import datetime
import pdfplumber
from pymongo import MongoClient

def parse_date(date_str):
    """
    様々な形式の日付文字列を datetime オブジェクトに変換する
    """
    if not date_str:
        return None
    
    formats = [
        '%d %B %Y',      # 15 January 2026
        '%m-%d-%Y',      # 01-15-2026
        '%d/%m/%Y',      # 15/01/2026
        '%d-%m-%Y',      # 15-01-2026
        '%Y-%m-%d'       # 2026-01-15
    ]
    
    for fmt in formats:
        try:
            return datetime.strptime(date_str.strip(), fmt)
        except ValueError:
            continue
    return None

def parse_folder_name(folder_name):
    """
    サブフォルダ名から生徒名と提出日を抽出する
    """
    match = re.match(r'^\d+-\d+\s+-\s+(.+?)\s+SOI-[A-Z]+\s+-\s+(\d{1,2}\s+[A-Za-z]+\s+\d{4})', folder_name)
    if match:
        student_name = match.group(1).strip()
        sub_date_str = match.group(2).strip()
        return student_name, sub_date_str
    return None, None

def main():
    
    cert_name_input = input("Enter Name of Certificate (e.g., MongoDB and the Document Model): ").strip()
    folder_url = input("Enter URL of the Folder to be processed: ").strip()
    target_date_str = input("Enter Target Completion Date (e.g., 15-01-2026): ").strip()
    
    target_date_dt = parse_date(target_date_str)
    if not target_date_dt:
        print("[error] 目標完了日のフォーマットが認識できませんでした。")
    
    mongo_uri = input("Enter MongoDB Connection URI (Press Enter for default): ").strip()
    if not mongo_uri:
        mongo_uri = "mongodb://localhost:27017/"
        
    try:
        client = MongoClient(mongo_uri)
        db = client["sdlc_certificate_db"]
        collection = db["SD_Marks"]
        print("[success] MongoDB接続OK (コレクション: SD_Marks)")
    except Exception as e:
        print(f"[error] {e}")
        return

    if os.path.exists(folder_url) and os.path.isdir(folder_url):

        subfolders = os.listdir(folder_url)
        success_count = 0
        
        print("処理とスコアリングを実行中...\n")
        
        for subfolder in subfolders:
            subfolder_path = os.path.join(folder_url, subfolder)
            
            if os.path.isdir(subfolder_path):
                folder_student_name, sub_date_str = parse_folder_name(subfolder)
                
                pdf_files = [f for f in os.listdir(subfolder_path) if f.lower().endswith('.pdf')]
                
                if len(pdf_files) == 1 and folder_student_name:
                    pdf_filename = pdf_files[0]
                    pdf_full_path = os.path.join(subfolder_path, pdf_filename)
                    
                    extracted_text = ""
                    try:
                        with pdfplumber.open(pdf_full_path) as pdf:
                            for page in pdf.pages:
                                text = page.extract_text()
                                if text:
                                    extracted_text += text + "\n"
                    except Exception as e:
                        continue

                    # --- データの抽出（行番号インデックスでシンプルに取得） ---
                    lines = [line.strip() for line in extracted_text.split('\n') if line.strip()]
                    
                    # 構造に応じた直接取得
                    extracted_cert_name = lines[1] if len(lines) > 1 else ""  # 2行目：証明書名
                    cert_date_str = lines[2] if len(lines) > 2 else None     # 3行目：日付
                    cert_id = lines[-1] if lines else None                     # 最後の行：認定ID

                    # --- バリデーションチェック ---
                    reasons = []
                    is_valid = True

                    #  生徒名チェック
                    name_parts = folder_student_name.lower().split()
                    name_matched = all(part in extracted_text.lower() for part in name_parts)
                    if not name_matched:
                        is_valid = False
                        reasons.append("Student name mismatch")

                    #  認定IDチェック
                    if not cert_id or cert_id == "UNKNOWN_ID" or len(cert_id) < 5:
                        is_valid = False
                        reasons.append("Certificate ID missing or invalid")

                    #  証明書名チェック
                    if cert_name_input.lower() not in extracted_cert_name.lower():
                        is_valid = False
                        reasons.append("Certificate name mismatch")

                    #  日付チェック
                    sub_date_dt = parse_date(sub_date_str)
                    cert_date_dt = parse_date(cert_date_str) if cert_date_str else None

                    if cert_date_dt and sub_date_dt:
                        if cert_date_dt > sub_date_dt:
                            is_valid = False
                            reasons.append("Certificate date is later than submission date")
                    else:
                        is_valid = False
                        reasons.append("Date parsing failed")

                    # --- スコア算出 ---
                    if not is_valid:
                        score = 0
                        rationale = f"Score 0: Requirements failed ({', '.join(reasons)})."
                    else:
                        if target_date_dt and sub_date_dt:
                            if sub_date_dt > target_date_dt:
                                score = 1
                                rationale = "Score 1: Requirements met, but submitted after target completion date."
                            else:
                                score = 2
                                rationale = "Score 2: Requirements met and submitted on time."
                        else:
                            score = 1
                            rationale = "Score 1: Requirements met, but target date comparison unavailable."

                    # MongoDB格納用ドキュメント（DBにはPDFから取得した `extracted_cert_name` が入る）
                    cert_document = {
                        "certificate_name": extracted_cert_name,
                        "score": score,
                        "scoring_rationale": rationale,
                        "submission_date": sub_date_str,
                        "certificate_number": cert_id
                    }
                    
                    collection.update_one(
                        {"student_name": folder_student_name},
                        {"$pull": {"certificates": {"certificate_name": extracted_cert_name}}}
                    )
                    
                    collection.update_one(
                        {"student_name": folder_student_name},
                        {"$push": {"certificates": cert_document}},
                        upsert=True
                    )
                    
                    success_count += 1
                    
                    if success_count <= 3:
                        print(f"student name: {folder_student_name}")
                        print(f"  certificate name: {extracted_cert_name}")
                        print(f"  score: {score} | reason: {rationale}")
                        print(f"  submission date: {sub_date_str} | certificate number: {cert_id}")
                        print("-" * 50)
                        
        print(f"\ncompleted: 合計 {success_count} 件のデータを格納しました！")
        
    else:
        print("\n[error] 指定されたフォルダが見つからないか、パスが正しくありません。")

if __name__ == "__main__":
    main()