from aiogram.fsm.state import State, StatesGroup


class OzhivlyatorState(StatesGroup):
    main_menu = State()
    waiting_for_drawing = State()
    processing_generation = State()
    showing_purchase_options = State()
    message_to_delete = State()
