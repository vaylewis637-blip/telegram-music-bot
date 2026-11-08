from aiogram.fsm.state import State, StatesGroup


class CaptchaState(StatesGroup):
    waiting_for_answer = State()
