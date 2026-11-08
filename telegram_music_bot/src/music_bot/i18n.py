from __future__ import annotations

LANGUAGES = {
    "ru": "🇷🇺 Русский",
    "en": "🇺🇸 English",
}

MESSAGES: dict[str, dict[str, str]] = {
    "en": {
        "choose_language": "🌐 Choose your language / Выберите язык:",
        "language_saved": "🌐 Language set to English.",
        "unsupported_language": "🌐 That language option isn't supported.",
        "captcha_prompt": (
            "🔢 Before using music search, solve this quick check:\n\n"
            "<b>{left} + {right} = ?</b>\n"
            "Tap an answer or reply with the number within {seconds} seconds."
        ),
        "captcha_passed": "🔢 CAPTCHA passed.",
        "captcha_wrong": "🔢 That answer wasn't correct. Try again ({attempts} attempt(s) left).",
        "captcha_too_many": "🔢 Too many attempts. Here's a new challenge.",
        "captcha_expired": "🔢 That challenge expired. Here's a new one.",
        "captcha_old_button": "🔢 That CAPTCHA button is no longer active.",
        "captcha_no_active": "🔢 There is no active CAPTCHA for this account.",
        "captcha_not_yours": "🔢 This CAPTCHA belongs to another user.",
        "captcha_required": "🔢 Please complete the CAPTCHA first.",
        "invalid_captcha_button": "🔢 This CAPTCHA button is invalid.",
        "join_required": (
            "✅ Join the required channel(s) to use music search:\n"
            "<b>{names}</b>\n\n"
            "After joining, tap “I've joined — check”."
        ),
        "join_channel": "✅ Join {label}",
        "check_subscription": "✅ I've joined — check",
        "membership_error": (
            "✅ I couldn't check channel membership. Please contact the bot "
            "administrator and ask them to confirm I can access every required channel."
        ),
        "membership_missing": "✅ Some required channels are still missing.",
        "membership_confirmed": "✅ Subscription confirmed.",
        "home": "🎵 Hi! Type the song name and I'll find it for you.",
        "search_prompt": (
            "🔍 Send a song title or artist after the command, for example:\n"
            "<code>/search Daft Punk</code>"
        ),
        "searching": "🔍 Searching the music catalog…",
        "search_failed": "🔍 The music catalog is temporarily unavailable. Please try again shortly.",
        "no_tracks": "🔍 No tracks found for <b>{query}</b>. Try another title or artist.",
        "search_results_page": (
            "🔍 Results for “{query}” — page {page}/{total_pages}. Choose a song:"
        ),
        "song_button": "{artist} — {title}",
        "next_page": "➡️ Next page",
        "previous_page": "⬅️ Previous page",
        "song_actions": "🎵 <b>{artist} — {title}</b>\nChoose an action:",
        "listen_button": "🎧 Listen",
        "download_button": "⬇️ Download",
        "back_results": "⬅️ Back to results",
        "selection_expired": "🔍 These results expired. Search again.",
        "downloading_preview": "⬇️ Downloading the audio preview…",
        "preview_unavailable": "⬇️ No audio preview is available for this song.",
        "download_failed": "⬇️ Couldn't download or send this audio. Please try again.",
        "audio_caption": "🎵 <b>{title}</b> — {artist}",
    },
    "ru": {
        "choose_language": "🌐 Выберите язык / Choose your language:",
        "language_saved": "🌐 Язык интерфейса — русский.",
        "unsupported_language": "🌐 Этот вариант языка не поддерживается.",
        "captcha_prompt": (
            "🔢 Чтобы начать поиск музыки, решите пример:\n\n"
            "<b>{left} + {right} = ?</b>\n"
            "Нажмите на ответ или отправьте число в течение {seconds} секунд."
        ),
        "captcha_passed": "🔢 Проверка пройдена.",
        "captcha_wrong": "🔢 Неверный ответ. Попробуйте ещё раз (осталось попыток: {attempts}).",
        "captcha_too_many": "🔢 Слишком много ошибок. Вот новое задание.",
        "captcha_expired": "🔢 Время вышло. Вот новое задание.",
        "captcha_old_button": "🔢 Эта кнопка проверки уже не действует.",
        "captcha_no_active": "🔢 Для этого аккаунта нет активной проверки.",
        "captcha_not_yours": "🔢 Эта проверка предназначена другому пользователю.",
        "captcha_required": "🔢 Сначала пройдите проверку.",
        "invalid_captcha_button": "🔢 Эта кнопка проверки недействительна.",
        "join_required": (
            "✅ Чтобы искать музыку, подпишитесь на обязательные каналы:\n"
            "<b>{names}</b>\n\n"
            "После подписки нажмите «Я подписался — проверить»."
        ),
        "join_channel": "✅ Подписаться: {label}",
        "check_subscription": "✅ Я подписался — проверить",
        "membership_error": (
            "✅ Не удалось проверить подписку. Попросите администратора бота "
            "убедиться, что бот имеет доступ ко всем обязательным каналам."
        ),
        "membership_missing": "✅ Вы подписались не на все обязательные каналы.",
        "membership_confirmed": "✅ Подписка подтверждена.",
        "home": "🎵 Привет! Напиши название песни — и я её найду.",
        "search_prompt": (
            "🔍 Укажите исполнителя или песню после команды, например:\n"
            "<code>/search Daft Punk</code>"
        ),
        "searching": "🔍 Ищу в музыкальном каталоге…",
        "search_failed": "🔍 Музыкальный каталог временно недоступен. Попробуйте чуть позже.",
        "no_tracks": "🔍 По запросу <b>{query}</b> ничего не найдено. Попробуйте другое название или имя исполнителя.",
        "search_results_page": (
            "🔍 Результаты по запросу «{query}» — страница {page}/{total_pages}. Выберите песню:"
        ),
        "song_button": "{artist} — {title}",
        "next_page": "➡️ Следующая страница",
        "previous_page": "⬅️ Предыдущая страница",
        "song_actions": "🎵 <b>{artist} — {title}</b>\nВыберите действие:",
        "listen_button": "🎧 Прослушать",
        "download_button": "⬇️ Скачать",
        "back_results": "⬅️ Назад к результатам",
        "selection_expired": "🔍 Результаты устарели. Выполните поиск ещё раз.",
        "downloading_preview": "⬇️ Загружаю аудиофрагмент…",
        "preview_unavailable": "⬇️ Для этой песни нет доступного аудиофрагмента.",
        "download_failed": "⬇️ Не удалось загрузить или отправить аудио. Попробуйте ещё раз.",
        "audio_caption": "🎵 <b>{title}</b> — {artist}",
    },
}


def translate(language: str | None, key: str, **values: str | int) -> str:
    messages = MESSAGES.get(language or "en", MESSAGES["en"])
    return messages[key].format(**values)
