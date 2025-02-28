import discord
import sqlite3
import random
import time
import asyncio
import os

from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

# Discord Botの設定
intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

# カスタム絵文字
correct = "<:manuo:1125090432062333009>"
miss = "<:manuox:1102613654643421246>"
# データベース接続
os.chdir(os.path.dirname(os.path.abspath(__file__)))
os.makedirs('typing', exist_ok=True)
db_path = "C:\\Users\\2004a\\jikkencho\\typing\\typing_game.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# ランダムな文章を取得する関数
def get_random_sentence(difficulty):
    if difficulty == '初級':
        cursor.execute("SELECT sentence FROM sentences WHERE type = 0 ORDER BY RANDOM() LIMIT 1")
    elif difficulty == '中級':
        cursor.execute("SELECT sentence FROM sentences WHERE type = 1 ORDER BY RANDOM() LIMIT 1")
    else:  # 上級
        cursor.execute("SELECT sentence FROM sentences WHERE type = 2 ORDER BY RANDOM() LIMIT 1")
    result = cursor.fetchone()
    return result[0] if result else None

# 参加者情報を保持する変数
participants = {}
game_started = False
current_sentence = ""
start_time = 0
difficulty = ""
questions_remaining = 0
answers = []
channel_id = None
current_question_finished = False
timeout_task = None
waiting_for_players = False    # 追加
waiting_for_difficulty = False # 追加

# タイムアウト処理
async def timeout_check():
    global game_started, questions_remaining, channel_id
    await asyncio.sleep(120)
    if game_started and questions_remaining > 0:
        game_started = False
        await client.get_channel(channel_id).send('タイムアウトしました。ゲームを終了します。')

# Botが起動したときのイベント
@client.event
async def on_ready():
    print(f'Logged in as {client.user}')

def reset_game():
    global answers, current_question_finished, participants, difficulty, questions_remaining, game_started, timeout_task
    global waiting_for_players, waiting_for_difficulty  # 追加
    answers = []
    current_question_finished = False
    participants = {}
    difficulty = ""
    questions_remaining = 0
    game_started = False
    waiting_for_players = False    # 追加
    waiting_for_difficulty = False # 追加
    if timeout_task:
        timeout_task.cancel()
        timeout_task = None

# テキストを2000文字以内に分割送信するヘルパー関数
async def send_in_chunks(channel, text, chunk_size=2000):
    lines = text.split('\n')
    buffer = ''
    for line in lines:
        # +1 for the newline
        if len(buffer) + len(line) + 1 > chunk_size:
            await channel.send(buffer)
            buffer = line
        else:
            if buffer:
                buffer += '\n' + line
            else:
                buffer = line
    if buffer:
        await channel.send(buffer)

# メッセージを受信したときのイベント
@client.event
async def on_message(message):
    global game_started, participants, current_sentence, start_time, difficulty, questions_remaining
    global answers, channel_id, current_question_finished, timeout_task, waiting_for_players, waiting_for_difficulty  # 追加

    # Bot自身のメッセージは無視
    if message.author == client.user:
        return

    # ゲーム開始コマンド
    if message.content.startswith('!cash'):
        await message.channel.send('参加人数を入力してください。')
        reset_game()
        waiting_for_players = True  # フラグを立てる
        channel_id = message.channel.id
        return

    # 参加人数入力 (waiting_for_playersがTrueの時のみ受付)
    if waiting_for_players and message.channel.id == channel_id and message.content.isdigit():
        try:
            num_participants = int(message.content)
            if num_participants <= 0 or num_participants > 1000000:
                await message.channel.send("参加人数は1～1000000人の範囲で入力してください。")
                return
        except OverflowError:
            await message.channel.send("入力された値が大きすぎます。正しい人数を再入力してください。")
            return

        await message.channel.send(f'{num_participants}人の参加者でゲームを開始します。難易度を選択してください（初級、中級、上級）。')
        participants['count'] = num_participants
        participants['scores'] = {}
        waiting_for_players = False    # プレイヤー入力完了
        waiting_for_difficulty = True  # 難易度入力待ちへ
        return

    # 難易度選択 (waiting_for_difficultyがTrueの時のみ受付)
    if waiting_for_difficulty and message.channel.id == channel_id and message.content in ['初級', '中級', '上級']:
        difficulty = message.content
        await message.channel.send(f'{difficulty}モードでゲームを開始します。')
        game_started = True
        waiting_for_difficulty = False  # 難易度入力完了
        questions_remaining = 10  # 問題数を設定
        current_sentence = get_random_sentence(difficulty)
        if participants['count'] > 1:
            await asyncio.sleep(1)
        await message.channel.send(f'# お題: {current_sentence}')
        start_time = time.time()
        if timeout_task:
            timeout_task.cancel()
        timeout_task = asyncio.create_task(timeout_check())
        return

    # ランキング表示コマンド
    if message.content.startswith('!time'):
        # resultsテーブルから最速記録を取得
        cursor.execute('''
            SELECT s.sentence, r.player, MIN(r.time_taken) AS best_time
            FROM results r
            JOIN sentences s ON r.sentence_id = s.id
            GROUP BY r.sentence_id
            ORDER BY best_time ASC
        ''')
        ranking = cursor.fetchall()
        if not ranking:
            await message.channel.send('まだ最速記録はありません。')
            return

        # 見やすい形式で出力
        ranking_msg = "#【最速記録ランキング】\n"
        for row in ranking:
            sentence, player, best_time = row
            ranking_msg += f"・{sentence}\n   最速: {best_time:.2f}秒（{player}）\n"

        # 2000文字を超える場合は分割送信
        await send_in_chunks(message.channel, ranking_msg)
        return

    # ゲーム中の処理
    if game_started and message.channel.id == channel_id:
        if message.content == current_sentence and not current_question_finished:
            current_question_finished = True
            end_time = time.time()
            time_taken = end_time - start_time
            answers.append((message.author.name, time_taken, message))
            await asyncio.sleep(1)  # 1秒の間を空ける
            if answers:
                # 時間の短い順にソート
                answers.sort(key=lambda x: x[1])
                # 得点テーブル生成
                points = [5, 3, 1] + [0] * max(0, participants['count'] - 3)
                for i, (name, time_taken, msg) in enumerate(answers):
                    if i < len(points):
                        if name not in participants['scores']:
                            participants['scores'][name] = 0
                        participants['scores'][name] += points[i]
                        await msg.add_reaction(correct)
                        await message.channel.send(f'{name}! {time_taken:.2f}秒で正解です。{points[i]}ポイント獲得！')

                # 最速記録の更新
                cursor.execute('SELECT id FROM sentences WHERE sentence = ?', (current_sentence,))
                sentence_id = cursor.fetchone()[0]
                cursor.execute('SELECT time_taken FROM results WHERE sentence_id = ? ORDER BY time_taken ASC LIMIT 1', (sentence_id,))
                record = cursor.fetchone()
                # レコードがない場合 or 新しい記録が最速の場合
                if record is None or time_taken < record[0]:
                    cursor.execute(
                        'INSERT INTO results (player, sentence_id, time_taken) VALUES (?, ?, ?)',
                        (answers[0][0], sentence_id, time_taken)
                    )
                conn.commit()

                answers = []
                questions_remaining -= 1
                # 次の問題へ
                if questions_remaining > 0:
                    current_question_finished = False
                    current_sentence = get_random_sentence(difficulty)
                    if participants['count'] > 1:
                        await asyncio.sleep(1)  # 1秒のクールタイム
                    await message.channel.send(f'# 次のお題: {current_sentence}')
                    start_time = time.time()
                    if timeout_task:
                        timeout_task.cancel()
                    timeout_task = asyncio.create_task(timeout_check())
                else:
                    # ゲーム終了
                    game_started = False
                    await message.channel.send('ゲーム終了！結果発表:')
                    for player, score in participants['scores'].items():
                        await message.channel.send(f'{player}: {score}ポイント')
                    reset_game()
        elif message.content == current_sentence and current_question_finished:
            await message.channel.send(f'{message.author.name}さん、すでに回答は終了しています。')
        else:
            # 不正解者
            await message.add_reaction(miss)
            await message.channel.send(f'{message.author.name}さん、間違っています。もう一度試してください。')

# Botを起動
client.run(TOKEN)
