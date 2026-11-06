#!/usr/bin/env python3
"""Guinness vs Sheep — Irish Pub edition, Telegram Rich Messages.

Python 3.11+, only standard library.
Bothost: BOT_TOKEN / TELEGRAM_BOT_TOKEN from the hosting dashboard.
Commands: /start, /game, /help.
"""

import html
import json
import os
import random
import time
import urllib.error
import urllib.request

TOKEN = os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise SystemExit("Set BOT_TOKEN in Bothost. Never put your token in GitHub.")

API = "https://api.telegram.org/bot" + TOKEN + "/"
GAMES = {}
WIN_LINES = (
    (0, 1, 2), (3, 4, 5), (6, 7, 8),
    (0, 3, 6), (1, 4, 7), (2, 5, 8),
    (0, 4, 8), (2, 4, 6),
)


def tg(method, **payload):
    req = urllib.request.Request(
        API + method,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as response:
            data = json.load(response)
    except urllib.error.HTTPError as exc:
        # Never echo the complete request URL: it contains the secret bot token.
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Telegram error HTTP {exc.code}: {detail}") from None
    if not data.get("ok"):
        raise RuntimeError("Telegram error: " + str(data.get("description", data)))
    return data["result"]


def winner(cells):
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
    game["cells"][random.randrange(9)] = "S"  # sheep starts at a random position
    game["outcome"] = None
    game["winning"] = ()
    game["thinking"] = False


def tile(label, action=None, style=None):
    # Telegram supports native 'success', 'primary' and 'danger' button styles.
    style_attr = f' style="{style}"' if style else ""
    if action is None:
        return f'<tg-button type="disabled"{style_attr}>{label}</tg-button>'
    return (
        f'<tg-button type="callback_data"{style_attr} '
        f'data="{html.escape(action, quote=True)}">{label}</tg-button>'
    )


def render(game):
    score = game["score"]
    outcome = game["outcome"]
    if outcome == "P":
        message = "🏆 <b>ПОБЕДА GUINNESS!</b> За это стоит поднять бокал."
    elif outcome == "S":
        message = "🐑 <b>ОВЦА ПОБЕДИЛА!</b> Требуется реванш."
    elif outcome == "D":
        message = "🤝 <b>НИЧЬЯ.</b> Никто не уходит без пинты."
    elif game["thinking"]:
        message = "🐑 <b>Овца выбирает клетку…</b>"
    else:
        message = "🍺 <b>ТВОЙ ХОД.</b> Выбери свободную клетку."

    blocks = [
        '<h2>🍀 GUINNESS × SHEEP</h2>',
        '<p><i>THE IRISH PUB CLUB  ·  TIC-TAC-TOE</i></p>',
        '<hr/>',
        '<table compact>',
        '  <tr><th align="center">🍺 GUINNESS</th>'
        '<th align="center">🤝 НИЧЬИ</th>'
        '<th align="center">🐑 SHEEP</th></tr>',
        '  <tr>'
        f'<td align="center"><b>{score["P"]}</b></td>'
        f'<td align="center"><b>{score["D"]}</b></td>'
        f'<td align="center"><b>{score["S"]}</b></td>'
        '</tr>',
        '</table>',
        f'<p>{message}</p>',
    ]

    for row in range(3):
        buttons = []
        for index in range(row * 3, row * 3 + 3):
            mark = game["cells"][index]
            is_winning = index in game["winning"]
            if mark == "P":
                buttons.append(tile("⭐🍺" if is_winning else "🍺", style="success"))
            elif mark == "S":
                buttons.append(tile("⭐🐑" if is_winning else "🐑", style="danger" if is_winning else None))
            elif outcome or game["thinking"]:
                buttons.append(tile("▫️"))
            else:
                buttons.append(tile("▫️", f'm:{game["round"]}:{index}'))
        blocks.append('<tg-button-row align="center">' + ''.join(buttons) + '</tg-button-row>')

    blocks.extend([
        '<tg-button-row align="center">'
        + tile("↻  ЕЩЁ ОДНУ ПАРТИЮ", f'n:{game["round"]}', "success")
        + '</tg-button-row>',
        '<footer>✦  Сначала ходит овца. Она выбирает клетки случайно.  ✦</footer>',
    ])
    return "\n".join(blocks)


def update_message(chat_id, message_id, game):
    return tg(
        "editMessageText",
        chat_id=chat_id,
        message_id=message_id,
        rich_message={"html": render(game)},
    )


def start_game(message):
    chat_id = message["chat"]["id"]
    user = message.get("from") or {}
    game = {
        "owner": user.get("id"),
        "round": 0,
        "score": {"P": 0, "S": 0, "D": 0},
    }
    new_round(game)
    result = tg("sendRichMessage", chat_id=chat_id, rich_message={"html": render(game)})
    GAMES[(chat_id, result["message_id"])] = game


def handle_click(callback):
    message = callback.get("message") or {}
    chat_id = (message.get("chat") or {}).get("id")
    message_id = message.get("message_id")
    game = GAMES.get((chat_id, message_id))
    reply_id = callback["id"]

    if game is None:
        tg("answerCallbackQuery", callback_query_id=reply_id, text="Отправь /game для новой игры")
        return
    if callback.get("from", {}).get("id") != game["owner"]:
        tg("answerCallbackQuery", callback_query_id=reply_id, text="Это чужая партия. Создай свою: /game")
        return
    parts = (callback.get("data") or "").split(":")
    if len(parts) < 2 or parts[1] != str(game["round"]):
        tg("answerCallbackQuery", callback_query_id=reply_id, text="Эта партия уже обновлена")
        return

    if parts[0] == "n" and len(parts) == 2:
        tg("answerCallbackQuery", callback_query_id=reply_id)
        new_round(game)
        update_message(chat_id, message_id, game)
        return

    if parts[0] != "m" or len(parts) != 3 or not parts[2].isdigit():
        tg("answerCallbackQuery", callback_query_id=reply_id, text="Неизвестная команда")
        return

    index = int(parts[2])
    if (index not in range(9) or game["cells"][index]
            or game["outcome"] or game["thinking"]):
        tg("answerCallbackQuery", callback_query_id=reply_id, text="Клетка занята")
        return

    tg("answerCallbackQuery", callback_query_id=reply_id)
    game["cells"][index] = "P"
    outcome, winning = winner(game["cells"])
    if outcome:
        game["outcome"] = outcome
        game["winning"] = winning
        game["score"][outcome] += 1
        update_message(chat_id, message_id, game)
        return

    # Tiny native-message animation: show the pint, then sheep thinks,
    # then sheep occupies a random empty cell in the *same* message.
    game["thinking"] = True
    update_message(chat_id, message_id, game)
    time.sleep(0.65)
    free = [i for i, value in enumerate(game["cells"]) if not value]
    if free:
        game["cells"][random.choice(free)] = "S"
    game["thinking"] = False
    outcome, winning = winner(game["cells"])
    if outcome:
        game["outcome"] = outcome
        game["winning"] = winning
        game["score"][outcome] += 1
    update_message(chat_id, message_id, game)


def main():
    tg("deleteWebhook", drop_pending_updates=False)
    print("🍀 Guinness Irish Pub bot running", flush=True)
    offset = None
    while True:
        try:
            updates = tg(
                "getUpdates", offset=offset, timeout=25,
                allowed_updates=["message", "callback_query"],
            )
            for update in updates:
                offset = update["update_id"] + 1
                try:
                    if "callback_query" in update:
                        handle_click(update["callback_query"])
                    elif "message" in update:
                        message = update["message"]
                        text = (message.get("text") or "").split(" ")[0].split("@")[0]
                        if text in ("/start", "/game") and message.get("from"):
                            start_game(message)
                        elif text == "/help":
                            tg("sendMessage", chat_id=message["chat"]["id"],
                               text="🍺 /game — начни Guinness против овцы.\nНажимай на свободные клетки прямо в сообщении.")
                except Exception as exc:
                    print("Event error:", repr(exc), flush=True)
        except Exception as exc:
            print("Polling error:", repr(exc), flush=True)
            time.sleep(3)


if __name__ == "__main__":
    main()
