from aiogram.fsm.state import State, StatesGroup


class CaptchaState(StatesGroup):
    waiting_for_answer = State()


class SearchState(StatesGroup):
    waiting_for_query = State()


class EditorState(StatesGroup):
    editing = State()
    waiting_for_tags = State()
    waiting_for_speed = State()
    waiting_for_cover = State()
    waiting_for_trim = State()
