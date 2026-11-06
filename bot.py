#!/usr/bin/env python3
"""Guinness × Sheep. Rich-message tic-tac-toe, including inline sharing.

Python 3.11+, standard library only. No secrets belong in this file.
BOT_TOKEN must be configured at your hosting provider.
Enable inline mode in @BotFather using /setinline.
"""

import copy
import html
import json
import os
import random
import secrets
import time
import urllib.error
import urllib.request

TOKEN = os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise SystemExit("Set BOT_TOKEN in Bothost. Never paste it into GitHub.")

API = "https://api.telegram.org/bot" + TOKEN + "/"
WIN_LINES = (
    (0, 1, 2), (3, 4, 5), (6, 7, 8),
    (0, 3, 6), (1, 4, 7), (2, 5, 8),
    (0, 4, 8), (2, 4, 6),
)
# (chat_id, message_id) -> game
PRIVATE_GAMES = {}
# inline_message_id -> game (unique per destination message)
INLINE_GAMES = {}
# short token -> initial game (Telegram does not include a destination ID
# until an inline result has actually been sent and tapped)
INLINE_TEMPLATES = {}


def tg(method, **payload):
    req = urllib.request.Request(
        API + method,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as response:
            body = json.load(response)
    except urllib.error.HTTPError as exc:
        # Never log the request URL: it embeds the bot token.
        details = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Telegram HTTP {exc.code}: {details}") from None
    if not body.get("ok"):
        raise RuntimeError(str(body.get("description", "Telegram API error")))
    return body["result"]


def determine_winner(cells):
    for line in WIN_LINES:
        a, b, c = line
        if cells[a] and cells[a] == cells[b] == cells[c]:
            return cells[a], line
    if all(cells):
        return "D", ()
    return None, ()


def new_round(game):
    game["round"] += 1
    game["cells"] = [""] * 9
    game["cells"][random.randrange(9)] = "S"
    game["outcome"] = None
    game["winning"] = ()
    game["thinking"] = False


def new_game(owner=None):
    game = {
        "owner": owner,
        "round": 0,
        "score": {"P": 0, "D": 0, "S": 0},
        "token": secrets.token_hex(5),
        "created": time.time(),
    }
    new_round(game)
    return game


def tile(text, callback=None, style=None):
    style_attr = f' style="{style}"' if style else ""
    if callback is None:
        return f'<tg-button type="disabled"{style_attr}>{text}</tg-button>'
    return (f'<tg-button type="callback_data"{style_attr} '
            f'data="{html.escape(callback, quote=True)}">{text}</tg-button>')


def render(game):
    score = game["score"]
    outcome = game["outcome"]
    if outcome == "P":
        status = "🏆 <b>ПОБЕДА GUINNESS!</b> Поднимаем бокалы!"
    elif outcome == "S":
        status = "🐑 <b>ПОБЕДИЛА ОВЦА!</b> Нужен реванш."
    elif outcome == "D":
        status = "🤝 <b>НИЧЬЯ!</b> Ещё одна партия?"
    elif game["thinking"]:
        status = "🐑 <b>Овца выбирает клетку…</b>"
    else:
        status = "🍺 <b>ТВОЙ ХОД.</b> Нажми на свободную клетку."

    result = [
        "<h2>🍀 GUINNESS × SHEEP</h2>",
        "<p><i>THE IRISH PUB CLUB · TIC-TAC-TOE</i></p>",
        "<hr/>",
        "<table compact>",
        "<tr><th align=\"center\">🍺 GUINNESS</th>"
        "<th align=\"center\">🤝 НИЧЬИ</th>"
        "<th align=\"center\">🐑 SHEEP</th></tr>",
        f'<tr><td align="center"><b>{score["P"]}</b></td>'
        f'<td align="center"><b>{score["D"]}</b></td>'
        f'<td align="center"><b>{score["S"]}</b></td></tr>',
        "</table>",
        f"<p>{status}</p>",
    ]
    token = game["token"]
    rnd = game["round"]
    for row in range(3):
        buttons = []
        for i in range(row * 3, row * 3 + 3):
            mark = game["cells"][i]
            winning = i in game["winning"]
            if mark == "P":
                buttons.append(tile("⭐🍺" if winning else "🍺", style="success"))
            elif mark == "S":
                buttons.append(tile("⭐🐑" if winning else "🐑", style="danger" if winning else None))
            elif game["thinking"] or outcome:
                buttons.append(tile("▫️"))
            else:
                buttons.append(tile("▫️", f"m:{token}:{rnd}:{i}"))
        result.append('<tg-button-row align="center">' + "".join(buttons) + "</tg-button-row>")
    result.extend([
        '<tg-button-row align="center">'
        + tile("🔄 НОВАЯ ПАРТИЯ", f"n:{token}:{rnd}", "success")
        + "</tg-button-row>",
        "<footer>✦  Для отправки другу: в его чате напиши @Guinnness_bot и выбери игру.  ✦</footer>",
    ])
    return "\n".join(result)


def send_private_game(message):
    game = new_game(owner=(message.get("from") or {}).get("id"))
    chat = message["chat"]["id"]
    result = tg("sendRichMessage", chat_id=chat, rich_message={"html": render(game)})
    PRIVATE_GAMES[(chat, result["message_id"])] = game


def answer_inline(query):
    # This uses InputRichMessageContent, supported in the Bot API since 2026.
    game = new_game(owner=None)
    token = game["token"]
    INLINE_TEMPLATES[token] = game
    result = {
        "type": "article",
        "id": token,
        "title": "🍺 Guinness vs 🐑 Овца — сыграть",
        "description": "Крестики-нолики прямо в сообщении Telegram",
        "input_message_content": {"rich_message": {"html": render(game)}},
    }
    tg("answerInlineQuery", inline_query_id=query["id"], results=[result],
       cache_time=0, is_personal=True)


def callback_message_target(callback, game):
    if callback.get("inline_message_id"):
        return {"inline_message_id": callback["inline_message_id"]}
    msg = callback.get("message") or {}
    return {"chat_id": msg["chat"]["id"], "message_id": msg["message_id"]}


def update_message(callback, game):
    return tg("editMessageText", **callback_message_target(callback, game),
              rich_message={"html": render(game)})


def get_game(callback, token):
    inline_id = callback.get("inline_message_id")
    if inline_id:
        if inline_id in INLINE_GAMES:
            return INLINE_GAMES[inline_id]
        template = INLINE_TEMPLATES.get(token)
        if template is None:
            return None
        # Each inline sent message needs its own state; don't share one board
        # between two different destination chats.
        game = copy.deepcopy(template)
        INLINE_GAMES[inline_id] = game
        return game
    message = callback.get("message") or {}
    chat_id = (message.get("chat") or {}).get("id")
    msg_id = message.get("message_id")
    return PRIVATE_GAMES.get((chat_id, msg_id))


def handle_click(callback):
    query_id = callback["id"]
    parts = (callback.get("data") or "").split(":")
    if len(parts) not in (3, 4) or parts[0] not in ("m", "n"):
        tg("answerCallbackQuery", callback_query_id=query_id, text="Неизвестная команда")
        return
    command, token, round_num = parts[:3]
    game = get_game(callback, token)
    if not game or game["token"] != token:
        tg("answerCallbackQuery", callback_query_id=query_id,
           text="Для своей игры напиши @Guinnness_bot в нужном чате")
        return
    # Direct bot messages have a private owner. Inline games are accessible to
    # people in their destination chat (one shared board per message).
    if game["owner"] is not None and (callback.get("from") or {}).get("id") != game["owner"]:
        tg("answerCallbackQuery", callback_query_id=query_id,
           text="Эта партия создана для другого игрока. Напиши @Guinnness_bot")
        return
    if round_num != str(game["round"]):
        tg("answerCallbackQuery", callback_query_id=query_id, text="Партия уже обновлена")
        return
    if command == "n" and len(parts) == 3:
        tg("answerCallbackQuery", callback_query_id=query_id)
        new_round(game)
        update_message(callback, game)
        return
    if command != "m" or len(parts) != 4 or not parts[3].isdigit():
        tg("answerCallbackQuery", callback_query_id=query_id, text="Ошибка клетки")
        return
    index = int(parts[3])
    if index not in range(9) or game["cells"][index] or game["outcome"] or game["thinking"]:
        tg("answerCallbackQuery", callback_query_id=query_id, text="Клетка занята")
        return
    tg("answerCallbackQuery", callback_query_id=query_id)
    game["cells"][index] = "P"
    outcome, winning = determine_winner(game["cells"])
    if outcome:
        game["outcome"] = outcome
        game["winning"] = winning
        game["score"][outcome] += 1
        update_message(callback, game)
        return
    game["thinking"] = True
    update_message(callback, game)
    time.sleep(0.55)
    choices = [i for i, val in enumerate(game["cells"]) if not val]
    if choices:
        game["cells"][random.choice(choices)] = "S"
    game["thinking"] = False
    outcome, winning = determine_winner(game["cells"])
    if outcome:
        game["outcome"] = outcome
        game["winning"] = winning
        game["score"][outcome] += 1
    update_message(callback, game)


def handle_message(message):
    cmd = (message.get("text") or "").split(" ", 1)[0].split("@", 1)[0]
    if cmd in ("/start", "/game"):
        send_private_game(message)
    elif cmd in ("/help", "/share"):
        tg("sendMessage", chat_id=message["chat"]["id"],
           text=("🍺 Хочешь отправить другу Guinness vs Sheep?\n"
                 "Открой чат с другом, набери @Guinnness_bot, "
                 "выбери предложенную игру и отправь её.\n"
                 "Или поделись ссылкой https://t.me/Guinnness_bot?start=game"))


def main():
    tg("deleteWebhook", drop_pending_updates=False)
    print("🍀 Guinness vs Sheep + Inline Mode started", flush=True)
    offset = None
    while True:
        try:
            updates = tg("getUpdates", offset=offset, timeout=25,
                         allowed_updates=["message", "callback_query", "inline_query"])
            for update in updates:
                offset = update["update_id"] + 1
                try:
                    if "callback_query" in update:
                        handle_click(update["callback_query"])
                    elif "inline_query" in update:
                        answer_inline(update["inline_query"])
                    elif "message" in update:
                        handle_message(update["message"])
                except Exception as err:
                    print("Update error:", repr(err), flush=True)
        except Exception as err:
            print("Polling error:", repr(err), flush=True)
            time.sleep(3)


if __name__ == "__main__":
    main()
