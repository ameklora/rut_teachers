import asyncio
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from database_funcs import Database

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Инициализация хранилища состояний
storage = MemoryStorage()
bot = Bot(token="8132011839:AAEd3cXvgoqG10vnIEA0MmQc21xoj8Whs8E")
dp = Dispatcher(storage=storage)

# Инициализация базы данных
db = Database()


# Определение состояний FSM
class ReviewStates(StatesGroup):
    waiting_for_rating = State()  # Ожидание выбора звезд
    waiting_for_comment = State()  # Ожидание комментария
    confirming_comment = State()  # Ожидание подтверждения
    waiting_for_review_rating = State() # ожидание оценки отзыва


# Главное меню
def get_main_menu():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🏆 ТОП-5 преподавателей")],
            [KeyboardButton(text="📋 Список преподавателей"), KeyboardButton(text="🔍 Поиск")]
        ],
        resize_keyboard=True
    )
    return keyboard


# Клавиатура для карточки преподавателя
def get_teacher_keyboard(teacher_id):
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="👁 Посмотреть отзывы", callback_data=f"reviews_{teacher_id}")],
            [InlineKeyboardButton(text="⭐ Оценить", callback_data=f"rate_{teacher_id}")]
        ]
    )
    return keyboard


# Клавиатура со звездами для оценки
def get_rating_keyboard(teacher_id):
    keyboard = InlineKeyboardBuilder()
    for i in range(1, 6):
        keyboard.button(text=f"{i}⭐", callback_data=f"stars_{i}")
    keyboard.button(text="❌ Отмена", callback_data="cancel_rating")
    keyboard.adjust(3, 2)
    return keyboard.as_markup()


def rate_review_keyboard(review_id):
    review = db.get_review_by_id(review_id)
    if not review:
        # Если отзыв не найден, возвращаем пустую клавиатуру
        return InlineKeyboardBuilder().as_markup()

    keyboard = InlineKeyboardBuilder()
    keyboard.button(text=f"👍 {review['review_likes']}", callback_data=f"review_like-{review_id}")
    keyboard.button(text=f"👎 {review['review_dislikes']}", callback_data=f"review_dislike-{review_id}")
    keyboard.adjust(2)
    return keyboard.as_markup()

# Клавиатура с крестиком для отмены комментария
def get_comment_cancel_keyboard():
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="❌ Без комментария", callback_data="no_comment")]]
    )
    return keyboard


# Клавиатура подтверждения комментария
def get_confirm_keyboard():
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Да", callback_data="confirm_yes"),
             InlineKeyboardButton(text="❌ Нет", callback_data="confirm_no")]
        ]
    )
    return keyboard


# Обработчик команды /start
@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    # Очищаем любое предыдущее состояние
    await state.clear()

    welcome_text = (
        "👋 Добро пожаловать в рейтинг преподавателей!\n\n"
        "Здесь вы можете:\n"
        "• Смотреть рейтинги преподавателей\n"
        "• Читать и оставлять отзывы\n"
        "• Оценивать качество преподавания\n\n"
        "Выберите действие:"
    )
    await message.answer(welcome_text, reply_markup=get_main_menu())


# Обработчик кнопки ТОП-5
@dp.message(F.text == "🏆 ТОП-5 преподавателей")
async def show_top_teachers(message: types.Message, state: FSMContext):
    await state.clear()
    top_teachers = db.get_top_teachers(5)

    if not top_teachers:
        await message.answer("Пока нет преподавателей с оценками")
        return

    text = "🏆 ТОП-5 преподавателей:\n\n"
    for i, teacher in enumerate(top_teachers, 1):
        text += f"{i}. {teacher['surname']} {teacher['name']} {teacher['middlename']}\n"
        text += f"   ⭐ {teacher['overall_rating']['average']:.1f} ({teacher['overall_rating']['count']} отзывов)\n"
        text += f"   🏛 {teacher['institute']}, {teacher['department']}\n\n"

    await message.answer(text)


# Обработчик кнопки списка преподавателей
@dp.message(F.text == "📋 Список преподавателей")
async def show_teachers_list(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Функция списка преподавателей в разработке...")


# Обработчик кнопки поиска
@dp.message(F.text == "🔍 Поиск")
async def search_teachers(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Введите фамилию или имя преподавателя для поиска:")


# Обработчик поискового запроса
@dp.message(F.text)
async def handle_search(message: types.Message, state: FSMContext):
    # Проверяем, что это не команда и не кнопка главного меню
    if message.text in ["🏆 ТОП-5 преподавателей", "📋 Список преподавателей", "🔍 Поиск"]:
        return

    await state.clear()
    results = db.search_teachers(message.text)

    if not results:
        await message.answer("Преподаватели не найдены")
        return

    # Показываем первого найденного преподавателя
    teacher = results[0]
    await show_teacher_card(message, teacher)


# Показать карточку преподавателя
async def show_teacher_card(message: types.Message, teacher):
    text = (
        f"👨‍🏫 {teacher['surname']} {teacher['name']} {teacher['middlename']}\n"
        f"🏛 {teacher['institute']}, {teacher['department']}\n"
        f"🎓 {teacher['title']}\n"
        f"📚 {', '.join(teacher['subjects'])}\n"
        f"⭐ Рейтинг: {teacher['overall_rating']['average']:.1f}/5 ({teacher['overall_rating']['count']} отзывов)"
    )

    await message.answer(text, reply_markup=get_teacher_keyboard(teacher['id']))


# Обработчик нажатия на кнопку "Посмотреть отзывы"
@dp.callback_query(F.data.startswith("reviews_"))
async def show_reviews(callback: types.CallbackQuery, state: FSMContext):
    teacher_id = int(callback.data.split("_")[1])
    teacher = db.get_teacher_by_id(teacher_id)

    if not teacher or not teacher['reviews']:
        await callback.answer("Пока нет отзывов")
        return

    # Получаем отзывы
    reviews = db.get_teacher_reviews(teacher_id)

    # Сохраняем данные для пагинации (если нужно)
    await state.update_data(teacher_id=teacher_id, current_review_index=0)

    # Показываем первый отзыв
    review = reviews[0]
    text = (
        f'⭐️ {review["rating"]}/5\n\n'
        f'💬 {review["comment"]}\n\n'
    )

    await callback.message.answer(text, reply_markup=rate_review_keyboard(review["review_id"]))
    await callback.answer()


# Обработчик начала оценки
@dp.callback_query(F.data.startswith("rate_"))
async def start_rating(callback: types.CallbackQuery, state: FSMContext):
    teacher_id = int(callback.data.split("_")[1])

    # Сохраняем данные в состоянии
    await state.update_data(teacher_id=teacher_id)
    # Переходим в состояние ожидания оценки
    await state.set_state(ReviewStates.waiting_for_rating)

    await callback.message.answer(
        "Выберите оценку:",
        reply_markup=get_rating_keyboard(teacher_id)
    )
    await callback.answer()


# Отмена оценки
@dp.callback_query(ReviewStates.waiting_for_rating, F.data == "cancel_rating")
async def cancel_rating(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.answer("Оценка отменена")
    await callback.answer()


# Обработчик выбора звезд
@dp.callback_query(ReviewStates.waiting_for_rating, F.data.startswith("stars_"))
async def handle_stars(callback: types.CallbackQuery, state: FSMContext):
    rating = int(callback.data.split("_")[1])

    # Сохраняем оценку
    await state.update_data(rating=rating)
    # Переходим в состояние ожидания комментария
    await state.set_state(ReviewStates.waiting_for_comment)

    await callback.message.answer(
        "Напишите комментарий (или нажмите 'Без комментария'):",
        reply_markup=get_comment_cancel_keyboard()
    )
    await callback.answer()


# Обработчик отмены комментария
@dp.callback_query(ReviewStates.waiting_for_comment, F.data == "no_comment")
async def no_comment(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()

    # Сохраняем отзыв без комментария
    db.add_review(data['teacher_id'], str(callback.from_user.id), data['rating'], "")

    await callback.message.answer("✅ Оценка сохранена без комментария!")
    await state.clear()
    await callback.answer()

# Обработчик комментария
@dp.message(ReviewStates.waiting_for_comment, F.text)
async def handle_comment(message: types.Message, state: FSMContext):
    # Сохраняем комментарий
    await state.update_data(comment=message.text)
    # Переходим в состояние подтверждения
    await state.set_state(ReviewStates.confirming_comment)

    # Получаем все сохраненные данные
    data = await state.get_data()

    await message.answer(
        f"Ваш комментарий: *{message.text}*\n\nВсё верно?",
        parse_mode="Markdown",
        reply_markup=get_confirm_keyboard()
    )


# Обработчик подтверждения комментария
@dp.callback_query(ReviewStates.confirming_comment, F.data == "confirm_yes")
async def confirm_comment(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()

    # Сохраняем отзыв
    success = db.add_review(data['teacher_id'], str(callback.from_user.id), data['rating'], data['comment'])

    if success:
        await callback.message.answer("✅ Отзыв успешно сохранен!")
    else:
        await callback.message.answer("❌ Ошибка при сохранении отзыва")

    await state.clear()
    await callback.answer()


# Обработчик отмены комментария
@dp.callback_query(ReviewStates.confirming_comment, F.data == "confirm_no")
async def reject_comment(callback: types.CallbackQuery, state: FSMContext):
    # Возвращаемся к ожиданию комментария
    await state.set_state(ReviewStates.waiting_for_comment)

    await callback.message.answer(
        "Напишите новый комментарий:",
        reply_markup=get_comment_cancel_keyboard()
    )
    await callback.answer()

# обработчик лайков/дизлайков
@dp.callback_query(F.data.startswith("review_"))
async def handle_review_rating(callback: types.CallbackQuery):
    action, review_id_str = callback.data.split("-")
    review_id = int(review_id_str)
    user_id = str(callback.from_user.id)

    if "dislike" in action:
        success = db.rate_review(review_id, user_id, dislike=1)
        message = "👎" if success else "❌ Вы уже голосовали за этот отзыв"
    else:
        success = db.rate_review(review_id, user_id, like=1)
        message = "👍" if success else "❌ Вы уже голосовали за этот отзыв"

    # Обновляем сообщение только если голос был успешно учтен
    if success:
        review = db.get_review_by_id(review_id)
        if review:
            text = (
                f'⭐️ {review["rating"]}/5\n\n'
                f'💬 {review["comment"]}\n\n'
            )
            try:
                await callback.message.edit_text(text, reply_markup=rate_review_keyboard(review_id))
            except Exception as e:
                # Игнорируем ошибку "message is not modified"
                if "message is not modified" not in str(e):
                    print(f"Ошибка при редактировании сообщения: {e}")

    await callback.answer(message)

# Обработчик отмены любого действия
@dp.message(Command("cancel"))
@dp.message(F.text.lower() == "отмена")
async def cancel_handler(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is None:
        await message.answer("Нечего отменять")
        return

    await state.clear()
    await message.answer("Действие отменено", reply_markup=get_main_menu())


# Запуск бота
async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())