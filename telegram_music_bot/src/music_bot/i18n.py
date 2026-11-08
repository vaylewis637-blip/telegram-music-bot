from __future__ import annotations

LANGUAGES = {
    "en": "English",
    "ru": "Русский",
}

MESSAGES: dict[str, dict[str, str]] = {
    "en": {
        "choose_language": "Choose your language / Выберите язык:",
        "language_saved": "Language set to English.",
        "captcha_prompt": (
            "Before using music search, solve this quick check:\n\n"
            "<b>{left} + {right} = ?</b>\n"
            "Tap an answer or reply with the number within {seconds} seconds."
        ),
        "captcha_passed": "CAPTCHA passed.",
        "captcha_wrong": "That answer wasn't correct. Try again ({attempts} attempt(s) left).",
        "captcha_too_many": "Too many attempts. Here's a new challenge.",
        "captcha_expired": "That challenge expired. Here's a new one.",
        "captcha_old_button": "That CAPTCHA button is no longer active.",
        "captcha_no_active": "There is no active CAPTCHA for this account.",
        "captcha_not_yours": "This CAPTCHA belongs to another user.",
        "captcha_required": "Please complete the CAPTCHA first.",
        "join_required": (
            "Join the required channel(s) to use music search:\n"
            "<b>{names}</b>\n\n"
            "After joining, tap “I've joined — check”."
        ),
        "join_channel": "Join {label}",
        "check_subscription": "I've joined — check",
        "membership_error": (
            "I couldn't check channel membership. Please contact the bot "
            "administrator and ask them to confirm I can access every required channel."
        ),
        "membership_missing": "Some required channels are still missing.",
        "membership_confirmed": "Subscription confirmed.",
        "home": (
            "You're all set. Send a song title or artist name to search.\n"
            "You can also use <code>/search artist or song</code>."
        ),
        "search_prompt": (
            "Send a song title or artist after the command, for example:\n"
            "<code>/search Daft Punk</code>"
        ),
        "searching": "Searching the music catalog…",
        "search_failed": "The music catalog is temporarily unavailable. Please try again shortly.",
        "no_tracks": "No tracks found for <b>{query}</b>. Try another title or artist.",
        "results_for": "Results for <b>{query}</b>:",
        "album_unavailable": "Album unavailable",
        "open_track": "Open track {number}",
        "preview_track": "Preview {number}",
    },
    "ru": {
        "choose_language": "Выберите язык / Choose your language:",
        "language_saved": "Язык интерфейса — русский.",
        "captcha_prompt": (
            "Чтобы начать поиск музыки, решите пример:\n\n"
            "<b>{left} + {right} = ?</b>\n"
            "Нажмите на ответ или отправьте число в течение {seconds} секунд."
        ),
        "captcha_passed": "Проверка пройдена.",
        "captcha_wrong": "Неверный ответ. Попробуйте ещё раз (осталось попыток: {attempts}).",
        "captcha_too_many": "Слишком много ошибок. Вот новое задание.",
        "captcha_expired": "Время вышло. Вот новое задание.",
        "captcha_old_button": "Эта кнопка проверки уже не действует.",
        "captcha_no_active": "Для этого аккаунта нет активной проверки.",
        "captcha_not_yours": "Эта проверка предназначена другому пользователю.",
        "captcha_required": "Сначала пройдите проверку.",
        "join_required": (
            "Чтобы искать музыку, подпишитесь на обязательные каналы:\n"
            "<b>{names}</b>\n\n"
            "После подписки нажмите «Я подписался — проверить»."
        ),
        "join_channel": "Подписаться: {label}",
        "check_subscription": "Я подписался — проверить",
        "membership_error": (
            "Не удалось проверить подписку. Попросите администратора бота "
            "убедиться, что бот имеет доступ ко всем обязательным каналам."
        ),
        "membership_missing": "Вы подписались не на все обязательные каналы.",
        "membership_confirmed": "Подписка подтверждена.",
        "home": (
            "Готово. Отправьте название песни или имя исполнителя для поиска.\n"
            "Также можно использовать <code>/search исполнитель или песня</code>."
        ),
        "search_prompt": (
            "Укажите исполнителя или песню после команды, например:\n"
            "<code>/search Daft Punk</code>"
        ),
        "searching": "Ищу в музыкальном каталоге…",
        "search_failed": "Музыкальный каталог временно недоступен. Попробуйте чуть позже.",
        "no_tracks": "По запросу <b>{query}</b> ничего не найдено. Попробуйте другое название или имя исполнителя.",
        "results_for": "Результаты по запросу <b>{query}</b>:",
        "album_unavailable": "Альбом не указан",
        "open_track": "Открыть трек {number}",
        "preview_track": "Прослушать {number}",
    },
}


def translate(language: str | None, key: str, **values: str | int) -> str:
    messages = MESSAGES.get(language or "en", MESSAGES["en"])
    return messages[key].format(**values)
