import discord
import sqlite3
import random
import time
import asyncio
import os
from datetime import datetime
from dotenv import load_dotenv

# 設定読み込み
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

# ==============================
# 定数と設定
# ==============================
GAME_TIMEOUT = 120  # 秒
QUESTIONS_PER_GAME = 10  # 1ゲームあたりの問題数
POINT_DISTRIBUTION = [5, 3, 1]  # 1位、2位、3位の得点
BOT_VERSION = "1.1.0"

# Discord Botの設定
intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

# カスタム絵文字
correct_emoji = "<:manuo:1125090432062333009>"  # 正解用の絵文字ID
miss_emoji = "<:manuox:1102613654643421246>"    # 不正解用の絵文字ID

# ==============================
# データベース設定
# ==============================
def setup_database():
    """データベース接続を設定して返す"""
    try:
        os.chdir(os.path.dirname(os.path.abspath(__file__)))
        os.makedirs('typing', exist_ok=True)
        db_path = "C:\\Users\\2004a\\jikkencho\\typing\\typing_game.db"
        conn = sqlite3.connect(db_path)
        print(f"データベースに接続しました: {db_path}")
        return conn
    except Exception as e:
        print(f"データベース接続エラー: {e}")
        return None

# データベース接続
conn = setup_database()
cursor = conn.cursor()

# ==============================
# ゲーム状態管理
# ==============================
class GameState:
    """ゲームの状態を管理するクラス"""
    def __init__(self):
        self.reset()
    
    def reset(self):
        """ゲーム状態をリセット"""
        self.participants = {}
        self.game_started = False
        self.current_sentence = ""
        self.start_time = 0
        self.difficulty = ""
        self.questions_remaining = 0
        self.answers = []
        self.channel_id = None
        self.current_question_finished = False
        self.timeout_task = None
        self.waiting_for_players = False
        self.waiting_for_difficulty = False
        self.game_logs = []  # ゲームの進行を記録
        self.last_activity_time = time.time()  # アクティビティタイムスタンプを追加

# ゲーム状態のインスタンス
game = GameState()

# ==============================
# ゲームのヘルパー関数
# ==============================
def get_random_sentence(difficulty):
    """指定された難易度のランダムな文章を取得する"""
    try:
        difficulty_map = {
            '初級': 0,
            '中級': 1,
            '上級': 2
        }
        difficulty_value = difficulty_map.get(difficulty, 0)
        
        cursor.execute(
            "SELECT sentence FROM sentences WHERE type = ? ORDER BY RANDOM() LIMIT 1",
            (difficulty_value,)
        )
        result = cursor.fetchone()
        return result[0] if result else "サンプル文章"
    except Exception as e:
        print(f"文章取得エラー: {e}")
        return "エラーが発生しました。もう一度お試しください。"

def log_game_event(event_type, details=None):
    """ゲームイベントをログに記録"""
    event = {
        'type': event_type,
        'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'details': details or {}
    }
    game.game_logs.append(event)
    print(f"ゲームログ: {event_type} - {details}")

# ==============================
# タイマーと非同期タスク
# ==============================
async def timeout_monitor():
    """ゲームのタイムアウトを監視する常駐タスク"""
    while True:
        try:
            # 現在ゲーム中かつ最後のアクティビティから設定時間以上経過した場合
            now = time.time()
            if game.game_started and (now - game.last_activity_time >= GAME_TIMEOUT):
                print(f"タイムアウト検出: 最後のアクティビティから{now - game.last_activity_time:.1f}秒経過")
                game.game_started = False
                channel = client.get_channel(game.channel_id)
                if channel:
                    await channel.send('⏰ タイムアウトしました。ゲームを終了します。')
                    log_game_event('timeout', {
                        'remaining_questions': game.questions_remaining,
                        'elapsed': now - game.last_activity_time
                    })
                game.reset()
        except Exception as e:
            print(f"タイムアウトモニター エラー: {e}")
        
        # 短い間隔で確認（5秒間隔）
        await asyncio.sleep(5)  

def reset_timeout_timer():
    """タイムアウトタイマーをリセット（現在時刻を更新するだけ）"""
    game.last_activity_time = time.time()
    log_game_event('timer_reset', {
        'timeout_at': game.last_activity_time + GAME_TIMEOUT,
        'current_time': game.last_activity_time
    })
    print(f"タイマーリセット: {time.strftime('%H:%M:%S', time.localtime(game.last_activity_time))}")

async def send_in_chunks(channel, text, chunk_size=2000):
    """長いメッセージを分割して送信"""
    lines = text.split('\n')
    buffer = ''
    for line in lines:
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

# ==============================
# Discordイベントハンドラ
# ==============================
@client.event
async def on_ready():
    """Botが起動したときのイベント"""
    print(f'ログインしました: {client.user} (v{BOT_VERSION})')
    # タイムアウトモニタータスクを起動
    asyncio.create_task(timeout_monitor())
    # 起動時のステータス設定（オプション）
    await client.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.playing, 
            name="タイピングゲーム | !help"
        )
    )

@client.event
async def on_message(message):
    """メッセージを受信したときのイベント"""
    # Bot自身のメッセージは無視
    if message.author == client.user:
        return

    # ヘルプコマンド
    if message.content.startswith('!help'):
        help_text = (
            "# 🎮 **タイピングゲームボット - ヘルプ**\n\n"
            "## コマンド:\n"
            "- `!cash` - タイピングゲームを開始します\n"
            "- `!time` - 全問題の最速記録ランキングを表示します\n"
            "- `!help` - このヘルプメッセージを表示します\n\n"
            "## ゲームの流れ:\n"
            "1. `!cash`で開始 → 参加人数入力 → 難易度選択\n"
            "2. お題をタイプして送信\n"
            "3. 最速回答者から順に5点、3点、1点が付与されます\n"
            f"4. {QUESTIONS_PER_GAME}問終了でゲーム終了\n\n"
            f"⏰ {GAME_TIMEOUT}秒間無回答の場合、タイムアウトします。"
        )
        await message.channel.send(help_text)
        return

    # ゲーム開始コマンド
    if message.content.startswith('!cash'):
        await message.channel.send('参加人数を入力してください。')
        game.reset()
        game.waiting_for_players = True
        game.channel_id = message.channel.id
        log_game_event('game_init', {'channel': message.channel.name})
        return

    # 参加人数入力処理
    if game.waiting_for_players and message.channel.id == game.channel_id and message.content.isdigit():
        await handle_player_count_input(message)
        return

    # 難易度選択処理
    if game.waiting_for_difficulty and message.channel.id == game.channel_id:
        await handle_difficulty_selection(message)
        return

    # ランキング表示コマンド
    if message.content.startswith('!time'):
        await show_rankings(message.channel)
        return

    # ゲーム中の回答処理
    if game.game_started and message.channel.id == game.channel_id:
        await handle_game_answer(message)

# ==============================
# メッセージハンドラ関数
# ==============================
async def handle_player_count_input(message):
    """参加人数入力の処理"""
    try:
        num_participants = int(message.content)
        if num_participants <= 0 or num_participants > 1000000:
            await message.channel.send("参加人数は1～1000000人の範囲で入力してください。")
            return
    except (ValueError, OverflowError):
        await message.channel.send("正しい人数を入力してください。")
        return

    await message.channel.send(f'👥 {num_participants}人の参加者でゲームを開始します。\n難易度を選択してください（初級、中級、上級）。')
    game.participants['count'] = num_participants
    game.participants['scores'] = {}
    game.waiting_for_players = False
    game.waiting_for_difficulty = True
    log_game_event('players_set', {'count': num_participants})

async def handle_difficulty_selection(message):
    """難易度選択の処理"""
    if message.content in ['初級', '中級', '上級']:
        game.difficulty = message.content
        difficulty_emoji = {"初級": "🟢", "中級": "🟡", "上級": "🔴"}
        emoji = difficulty_emoji.get(game.difficulty, "")
        
        await message.channel.send(f'{emoji} {game.difficulty}モードでゲームを開始します。')
        game.game_started = True
        game.waiting_for_difficulty = False
        game.questions_remaining = QUESTIONS_PER_GAME
        
        # 最初の問題を出題
        game.current_sentence = get_random_sentence(game.difficulty)
        if game.participants['count'] > 1:
            await asyncio.sleep(1)
        await message.channel.send(f'# お題: {game.current_sentence}')
        game.start_time = time.time()
        
        # タイマーをリセット
        reset_timeout_timer()
        
        log_game_event('game_start', {'difficulty': game.difficulty, 'first_sentence': game.current_sentence})
    else:
        await message.channel.send("「初級」「中級」「上級」のいずれかを入力してください。")

async def show_rankings(channel):
    """ランキングの表示処理"""
    try:
        # resultsテーブルから最速記録を取得
        cursor.execute('''
            SELECT s.sentence, r.player, MIN(r.time_taken) AS best_time
            FROM results r
            JOIN sentences s ON r.sentence_id = s.id
            GROUP BY r.sentence_id
            ORDER BY best_time ASC
            LIMIT 20
        ''')
        ranking = cursor.fetchall()
        
        if not ranking:
            await channel.send('まだ最速記録はありません。')
            return

        # 見やすい形式で出力
        ranking_msg = "# 🏆 【最速記録ランキング】\n"
        for i, row in enumerate(ranking):
            sentence, player, best_time = row
            medal = ["🥇", "🥈", "🥉"][i] if i < 3 else f"{i+1}."
            ranking_msg += f"{medal} {sentence}\n   最速: {best_time:.2f}秒（{player}）\n\n"

        # 2000文字を超える場合は分割送信
        await send_in_chunks(channel, ranking_msg)
        log_game_event('ranking_shown', {'count': len(ranking)})
        
    except Exception as e:
        await channel.send(f"ランキング表示中にエラーが発生しました: {e}")
        print(f"ランキング表示エラー: {e}")

async def handle_game_answer(message):
    """ゲーム中の回答処理"""
    # すべての回答でタイマーをリセット
    reset_timeout_timer()
    
    if message.content == game.current_sentence and not game.current_question_finished:
        # 正解の処理
        await handle_correct_answer(message)
    elif message.content == game.current_sentence and game.current_question_finished:
        await message.channel.send(f'{message.author.name}さん、すでに回答は終了しています。')
    else:
        # 不正解の処理
        await message.add_reaction(miss_emoji)
        await message.channel.send(f'{message.author.name}さん、間違っています。もう一度試してください。')

async def handle_correct_answer(message):
    """正解時の処理"""
    game.current_question_finished = True
    end_time = time.time()
    time_taken = end_time - game.start_time
    
    # 回答情報を記録
    game.answers.append((message.author.name, time_taken, message))
    await asyncio.sleep(1)  # 1秒の間を空ける
    
    if game.answers:
        # 時間の短い順にソート
        game.answers.sort(key=lambda x: x[1])
        
        # 得点付与
        points = POINT_DISTRIBUTION + [0] * max(0, game.participants['count'] - len(POINT_DISTRIBUTION))
        for i, (name, time_taken, msg) in enumerate(game.answers):
            if i < len(points) and points[i] > 0:
                # スコア計算
                if name not in game.participants['scores']:
                    game.participants['scores'][name] = 0
                game.participants['scores'][name] += points[i]
                
                # リアクションと通知
                await msg.add_reaction(correct_emoji)
                
                # 順位に応じたメッセージ
                rank_emoji = ["🥇", "🥈", "🥉"][i] if i < 3 else "👏"
                await message.channel.send(
                    f'{rank_emoji} {name}! {time_taken:.2f}秒で正解です。{points[i]}ポイント獲得！'
                )
                
        # 最速記録の更新処理
        try:
            cursor.execute('SELECT id FROM sentences WHERE sentence = ?', (game.current_sentence,))
            sentence_id = cursor.fetchone()[0]
            cursor.execute(
                'SELECT time_taken FROM results WHERE sentence_id = ? ORDER BY time_taken ASC LIMIT 1', 
                (sentence_id,)
            )
            record = cursor.fetchone()
            
            # レコードがない場合 or 新しい記録が最速の場合
            fastest_answer = game.answers[0]
            if record is None or fastest_answer[1] < record[0]:
                cursor.execute(
                    'INSERT INTO results (player, sentence_id, time_taken) VALUES (?, ?, ?)',
                    (fastest_answer[0], sentence_id, fastest_answer[1])
                )
                await message.channel.send(f"🎉 {fastest_answer[0]}さんが新記録を樹立しました！")
            conn.commit()
        except Exception as e:
            print(f"記録更新エラー: {e}")

        # ゲーム進行処理
        game.answers = []
        game.questions_remaining -= 1
        
        # 次の問題へ進むか、ゲーム終了
        if game.questions_remaining > 0:
            await proceed_to_next_question(message.channel)
        else:
            await end_game(message.channel)

async def proceed_to_next_question(channel):
    """次の問題へ進む処理"""
    game.current_question_finished = False
    game.current_sentence = get_random_sentence(game.difficulty)
    
    if game.participants['count'] > 1:
        await asyncio.sleep(1)  # 1秒のクールタイム
    
    # 次の問題の案内
    question_num = QUESTIONS_PER_GAME - game.questions_remaining + 1
    await channel.send(f'# 問題 {question_num}/{QUESTIONS_PER_GAME}\n{game.current_sentence}')
    
    game.start_time = time.time()
    
    # タイマーをリセット
    reset_timeout_timer()
    
    log_game_event('next_question', {
        'number': question_num,
        'sentence': game.current_sentence
    })

async def end_game(channel):
    """ゲーム終了処理"""
    game.game_started = False
    
    # 結果をソート
    sorted_scores = sorted(
        game.participants['scores'].items(),
        key=lambda x: x[1],
        reverse=True
    )
    
    # 結果発表メッセージ作成
    result_msg = "# 🏁 ゲーム終了！結果発表:\n\n"
    
    for i, (player, score) in enumerate(sorted_scores):
        medal = ["🥇", "🥈", "🥉"][i] if i < 3 else f"{i+1}."
        result_msg += f"{medal} {player}: {score}ポイント\n"
    
    await channel.send(result_msg)
    
    # 次のゲーム案内
    await channel.send("次のゲームを始めるには `!cash` コマンドを使用してください。")
    
    log_game_event('game_end', {'scores': dict(sorted_scores)})
    game.reset()

# ==============================
# Botを起動
# ==============================
try:
    client.run(TOKEN)
except Exception as e:
    print(f"Bot起動エラー: {e}")
finally:
    # 終了時にデータベース接続を閉じる
    if conn:
        conn.close()
        print("データベース接続を閉じました")
