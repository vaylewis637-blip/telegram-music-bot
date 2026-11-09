from pathlib import Path

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from music_bot.config import Settings
from music_bot.handlers.menu_editor import HOME_TEXT, home_keyboard
from music_bot.i18n import LANGUAGES, translate
from music_bot.services.subscriptions import SubscriptionCheckError, find_missing_channels
from music_bot.services.user_repository import UserRepository
from music_bot.states import CaptchaState

router = Router(name="access")

# Existing CAPTCHA and channel gates remain in access handlers. The home menu is
# rendered only after these gates pass.
