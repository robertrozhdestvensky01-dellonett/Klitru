import os
import json
import time
import random
import urllib.request
import urllib.error

TOKEN = os.environ.get('BOT_TOKEN') or os.environ.get('TELEGRAM_BOT_TOKEN')
if not TOKEN:
    raise SystemExit('BOT_TOKEN is missing: set it in Bothost, not GitHub')
API = 'https://api.telegram.org/bot' + TOKEN + '/'
GAMES = {}
LINES = [(0,1,2),(3,4,5),(6,7,8),(0,3,6),(1,4,7),(2,5,8),(0,4,8),(2,4,6)]

def request(method, **kwargs):
    req = urllib.request.Request(API + method,
        data=json.dumps(kwargs, ensure_ascii=False).encode('utf-8'),
        headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req, timeout=45) as response:
        ans = json.load(response)
    if not ans.get('ok'):
        raise RuntimeError(ans)
    return ans['result']

def result(board):
    for a,b,c in LINES:
        if board[a] and board[a] == board[b] == board[c]:
            return board[a]
    return 'D' if all(board) else None

def new_round(game):
    game['round'] += 1
    game['board'] = [''] * 9
    game['board'][random.randrange(9)] = 'S'
    game['finished'] = None

def rich(game):
    score = game['score']
    end = game['finished']
    status = {'P':'🏆 Guinness победил!', 'S':'🐑 Овца победила!',
              'D':'🤝 Ничья!', None:'🍺 Твой ход! Выбери клетку.'}[end]
    parts = [
      '<h3>🍺 GUINNESS × 🐑 ОВЦА</h3>',
      f'<p>🍺 {score["P"]} · 🐑 {score["S"]} · 🤝 {score["D"]}</p>',
      f'<p><b>{status}</b></p>'
    ]
    for y in range(3):
        row = ['<tg-button-row align="center">']
        for i in range(y*3, y*3+3):
            mark = game['board'][i]
            if mark == 'P':
                row.append('<tg-button type="disabled">🍺</tg-button>')
            elif mark == 'S':
                row.append('<tg-button type="disabled">🐑</tg-button>')
            elif end:
                row.append('<tg-button type="disabled">▫️</tg-button>')
            else:
                row.append(f'<tg-button type="callback_data" data="m:{game["round"]}:{i}">▫️</tg-button>')
        row.append('</tg-button-row>')
        parts.append(''.join(row))
    parts.append('<tg-button-row align="center">'
                 f'<tg-button type="callback_data" data="n:{game["round"]}">🔄 Новая партия</tg-button>'
                 '</tg-button-row>')
    return '\n'.join(parts)

def start(msg):
    chat_id = msg['chat']['id']
    game = {'owner': msg['from']['id'], 'round':0,
            'score':{'P':0,'S':0,'D':0}}
    new_round(game)
    sent = request('sendRichMessage', chat_id=chat_id,
                   rich_message={'html': rich(game)})
    GAMES[(chat_id, sent['message_id'])] = game

def click(cb):
    msg = cb.get('message') or {}
    chat = msg.get('chat') or {}
    key = (chat.get('id'), msg.get('message_id'))
    game = GAMES.get(key)
    data = (cb.get('data') or '').split(':')
    if game is None:
        request('answerCallbackQuery', callback_query_id=cb['id'],
                text='Отправь /game для новой игры')
        return
    if cb['from']['id'] != game['owner']:
        request('answerCallbackQuery', callback_query_id=cb['id'],
                text='Это чужая партия. Отправь /game')
        return
    if len(data)<2 or data[1]!=str(game['round']):
        request('answerCallbackQuery', callback_query_id=cb['id'], text='Устаревший ход')
        return
    if data[0] == 'n':
        new_round(game)
    elif data[0]=='m' and len(data)==3 and data[2].isdigit():
        i = int(data[2])
        board = game['board']
        if not 0<=i<9 or board[i] or game['finished']:
            request('answerCallbackQuery', callback_query_id=cb['id'])
            return
        board[i] = 'P'
        outcome = result(board)
        if outcome is None:
            options = [j for j, v in enumerate(board) if not v]
            board[random.choice(options)] = 'S'
            outcome = result(board)
        if outcome:
            game['finished'] = outcome
            game['score'][outcome] += 1
    else:
        request('answerCallbackQuery', callback_query_id=cb['id'])
        return
    request('answerCallbackQuery', callback_query_id=cb['id'])
    request('editMessageText', chat_id=key[0], message_id=key[1],
            rich_message={'html': rich(game)})

def main():
    request('deleteWebhook', drop_pending_updates=False)
    offset = None
    print('Guinness rich game started', flush=True)
    while True:
        try:
            events = request('getUpdates', offset=offset, timeout=25,
                             allowed_updates=['message','callback_query'])
            for event in events:
                offset = event['update_id']+1
                try:
                    if 'callback_query' in event:
                        click(event['callback_query'])
                    elif 'message' in event:
                        m = event['message']
                        cmd = (m.get('text') or '').split(' ')[0].split('@')[0]
                        if cmd in ('/start','/game') and m.get('from'):
                            start(m)
                except Exception as e:
                    print('Update failed:', repr(e), flush=True)
        except Exception as e:
            print('Connection failed:', repr(e), flush=True)
            time.sleep(3)

if __name__=='__main__':
    main()
