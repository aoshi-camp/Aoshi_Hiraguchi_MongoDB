from collections import Counter
from pymongo import MongoClient

def main():
    
    # 1. MongoDBへの接続設定
    mongo_uri = input("Enter MongoDB Connection URI (Press Enter for default): ").strip()
    if not mongo_uri:
        mongo_uri = "mongodb://localhost:27017/"
        
    try:
        client = MongoClient(mongo_uri)
        db = client["sdlc_certificate_db"]
        collection = db["SD_Marks"]
        print("[success] MongoDB接続OK\n")
    except Exception as e:
        print(f"[error] {e}")
        return

    # 2. コレクションから全生徒のデータを取得して集計
    students_cursor = collection.find({})
    score_counts = Counter()
    total_students = 0

    for student in students_cursor:
        total_students += 1
        certificates = student.get("certificates", [])
        
        # 生徒ごとのトータルスコアを算出
        total_marks = sum(cert.get("score", 0) for cert in certificates)
        score_counts[total_marks] += 1

    if total_students == 0:
        print("[error] 集計するデータが見つかりませんでした。")
        return

    # 3. VS Codeの出力側に綺麗に表示する
    print("=========================")
    print("         result          ")
    print("=========================")
    
    # 高いポイント（最大4）から 0 ポイントまで順番に表示
    max_score = max(score_counts.keys()) if score_counts else 0
    display_max = max(4, max_score)  # 最低でも4ポイントまでは表示枠を作る
    
    for score in range(display_max, -1, -1):
        count = score_counts.get(score, 0)
        print(f"  {score} point : {count:2d} people")
        
    print("=========================")
    print(f"total : {total_students} people")
    print("=========================")

if __name__ == "__main__":
    main()