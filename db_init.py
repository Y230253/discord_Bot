import csv
import sqlite3
import os

# データベースに接続
db_path = 'typing/typing_game.db'
print("DB path:", db_path, "Exists:", os.path.exists(db_path))
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# sentencesテーブルの作成
cursor.execute('''
CREATE TABLE IF NOT EXISTS sentences (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sentence TEXT NOT NULL,
    type INTEGER NOT NULL
)
''')

# resultsテーブルの作成
cursor.execute('''
CREATE TABLE IF NOT EXISTS results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    player TEXT NOT NULL,
    sentence_id INTEGER,
    time_taken REAL,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (sentence_id) REFERENCES sentences(id)
)
''')

# CSVファイルからデータを読み取り、sentencesテーブルに挿入
with open('typing/sentences.csv', 'r', encoding='utf-8') as csvfile:
    csvreader = csv.reader(csvfile)
    for row in csvreader:
        sentence, type = row[0], int(row[1])
        cursor.execute('SELECT COUNT(*) FROM sentences WHERE sentence = ? AND type = ?', (sentence, type))
        if cursor.fetchone()[0] == 0:
            cursor.execute('INSERT INTO sentences (sentence, type) VALUES (?, ?)', (sentence, type))

# 変更を保存して接続を閉じる
conn.commit()
conn.close()
