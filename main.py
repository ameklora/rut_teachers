import asyncio
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from database.database_funcs import Database
from requests.database_requests import RequestDatabase
import re

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Инициализация хранилища состояний
storage = MemoryStorage()
bot = Bot(token="8132011839:AAEd3cXvgoqG10vnIEA0MmQc21xoj8Whs8E")
dp = Dispatcher(storage=storage)

# Инициализация баз данных
db = Database()
request_db = RequestDatabase()

# Глобальная переменная для хранения последнего сообщения по chat_id
last_message_ids = {}

# Константа для пагинации
PAGE_SIZE = 6


# Определение состояний FSM
class ReviewStates(StatesGroup):
	waiting_for_rating = State()
	waiting_for_search = State()
	waiting_for_comment = State()
	confirming_comment = State()
	waiting_for_request = State()


# Главное меню
def get_main_menu():
	keyboard = InlineKeyboardBuilder()
	keyboard.button(text="🏆 ТОП-5 преподавателей", callback_data="top5_teachers")
	keyboard.button(text="📋 Полный список", callback_data="list_teachers")
	keyboard.button(text="🔍 Поиск", callback_data="search_teacher")
	keyboard.button(text="💡 Предложка", callback_data="suggestions")
	keyboard.adjust(1)
	return keyboard.as_markup()


# Функция для создания нового активного сообщения
async def create_new_active_message(chat: types.Chat, text: str, reply_markup=None, parse_mode=None):
    """
    Создает новое активное сообщение и возвращает его ID
    """
    msg = await bot.send_message(chat.id, text, reply_markup=reply_markup, parse_mode=parse_mode)
    last_message_ids[chat.id] = msg.message_id
    return msg.message_id


# Функция для обновления существующего сообщения
async def update_message(message: types.Message, text: str, reply_markup=None, parse_mode=None):
    chat_id = message.chat.id
    try:
        if chat_id in last_message_ids:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=last_message_ids[chat_id],
                text=text,
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
        else:
            msg = await message.answer(text, reply_markup=reply_markup, parse_mode=parse_mode)
            last_message_ids[message.chat.id] = msg.message_id
    except Exception as e:
        msg = await message.answer(text, reply_markup=reply_markup, parse_mode=parse_mode)
        last_message_ids[message.chat.id] = msg.message_id


# Клавиатура для карточки преподавателя
def get_teacher_keyboard(teacher_id):
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="👁 Отзывы", callback_data=f"reviews_{teacher_id}")],
            [InlineKeyboardButton(text="⭐ Оценить", callback_data=f"rate_{teacher_id}")],
            [InlineKeyboardButton(text="Меню", callback_data="back_to_main")]
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


def get_sorted_reviews(reviews: list):
    """Возвращаем только отзывы с комментарием, отсортированные по популярности (лайки+дизлайки)."""
    filtered = [r for r in reviews if r.get("comment", "").strip()]
    sorted_reviews = sorted(filtered, key=lambda r: r.get("review_likes", 0) + r.get("review_dislikes", 0),
                            reverse=True)
    return sorted_reviews


def rate_review_keyboard(teacher_id: int, reviews: list, current_index: int) -> InlineKeyboardMarkup:
    """
    Клавиатура для просмотра отзывов, лайков/дизлайков и кнопка "Вернуться".
    """
    keyboard = InlineKeyboardMarkup(inline_keyboard=[])

    if not reviews:
        return keyboard

    review = reviews[current_index]

    # Навигация
    nav_buttons = []
    if current_index > 0:
        nav_buttons.append(
            InlineKeyboardButton(text="⬅️", callback_data=f"review_prev_{teacher_id}_{current_index}"))
    if current_index < len(reviews) - 1:
        nav_buttons.append(
            InlineKeyboardButton(text="➡️", callback_data=f"review_next_{teacher_id}_{current_index}"))
    if nav_buttons:
        keyboard.inline_keyboard.append(nav_buttons)

    # Лайк / Дизлайк
    keyboard.inline_keyboard.append([
        InlineKeyboardButton(text=f"👍 {review.get('review_likes', 0)}", callback_data=f"like_{review['review_id']}"),
        InlineKeyboardButton(text=f"👎 {review.get('review_dislikes', 0)}",
                             callback_data=f"dislike_{review['review_id']}")
    ])

    # Кнопка "Вернуться"
    keyboard.inline_keyboard.append([
        InlineKeyboardButton(text="↩️ Вернуться", callback_data=f"back_to_teacher_{teacher_id}")
    ])

    return keyboard


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


# ========== УМНЫЙ ПОИСК ==========

async def show_no_results_message(chat: types.Chat, query: str):
    """Показывает сообщение о пустых результатах с кнопками"""
    text = (
        f"🔍 По запросу '{query}' ничего не найдено\n\n"
        "Попробуй:\n"
        "• Уточнить фамилию\n"
        "• Использовать формат 'Фамилия Имя'\n"
        "• Искать по кафедре"
    )

    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="🔄 Повторить поиск", callback_data="search_teacher")
    keyboard.button(text="📋 Полный список", callback_data="list_teachers")
    keyboard.button(text="🏆 ТОП-5 преподавателей", callback_data="top5_teachers")
    keyboard.button(text="Меню", callback_data="back_to_main")
    keyboard.adjust(1)

    await create_new_active_message(chat, text, keyboard.as_markup())


async def show_smart_search_results(message: types.Message, results: list, query: str):
    """Умный показ результатов поиска"""

    if not results:
        await show_no_results_message(message.chat, query)
        return

    # Случай 1: Один результат - показываем сразу
    if len(results) == 1:
        teacher = results[0]
        await show_teacher_card(message, teacher)
        return

    # Случай 2: Несколько результатов - показываем список с выбором
    await show_teachers_choice(message, results, query)


async def show_teachers_choice(message: types.Message, results: list, query: str):
    """Показывает список преподавателей для выбора"""

    text = f"🔍 По запросу '{query}' найдено {len(results)} преподавателей:\n\n"

    # Показываем топ-5 самых релевантных
    top_results = results[:5]

    for i, teacher in enumerate(top_results, 1):
        review_count = teacher['overall_rating']['count']
        rating = teacher['overall_rating']['average']

        text += (
            f"{i}. {teacher['surname']} {teacher['name']} {teacher['middlename']}\n"
            f"   🏛 {teacher['department']}\n"
            f"   ⭐ {rating:.1f} ({review_count} отзывов)\n\n"
        )

    if len(results) > 5:
        text += f"⚠️ Показаны первые 5 из {len(results)} результатов\n"

    text += "Выбери препода:"

    keyboard = InlineKeyboardBuilder()

    # Кнопки для топ результатов
    for i, teacher in enumerate(top_results, 1):
        # Формат: "Иванов И.И. (⭐4.8)"
        rating_str = f"⭐{teacher['overall_rating']['average']:.1f}" if teacher['overall_rating']['count'] > 0 else "⚪"
        btn_text = f"{teacher['surname']} {teacher['name'][0]}.{teacher['middlename'][0]}. ({rating_str})"
        keyboard.button(text=btn_text, callback_data=f"choose_teacher_{teacher['id']}")

    # Если результатов больше 5 - кнопка "Показать еще"
    if len(results) > 5:
        keyboard.button(text="📄 Показать еще...", callback_data=f"show_more_{query}")

    keyboard.button(text="🔄 Новый поиск", callback_data="search_teacher")
    keyboard.button(text="📋 Полный список", callback_data="list_teachers")
    keyboard.button(text="Меню", callback_data="back_to_main")

    keyboard.adjust(1, 1, 2)

    await create_new_active_message(message.chat, text, keyboard.as_markup())


async def show_teacher_card(message: types.Message, teacher: dict):
    """Показывает карточку преподавателя"""
    text = (
        f"👨‍🏫 {teacher['surname']} {teacher['name']} {teacher['middlename']}\n"
        f"🏛 {teacher['institute']} {teacher['department']}\n"
        f"🎓 {teacher['title']}\n"
        f"📚 {', '.join(teacher['subjects'])}\n"
        f"⭐ Рейтинг: {teacher['overall_rating']['average']:.1f}/5 ({teacher['overall_rating']['count']} отзывов)"
    )

    keyboard = InlineKeyboardBuilder()
    keyboard.row(InlineKeyboardButton(text="👁 Отзывы", callback_data=f"reviews_{teacher['id']}"))
    keyboard.row(InlineKeyboardButton(text="⭐ Оценить", callback_data=f"rate_{teacher['id']}"))
    keyboard.row(InlineKeyboardButton(text="🔍 К результатам", callback_data="back_to_search_results"))
    keyboard.row(InlineKeyboardButton(text="Меню", callback_data="back_to_main"))

    await create_new_active_message(message.chat, text, keyboard.as_markup())


async def show_search_results_page(message: types.Message, results: list, page: int, query: str):
    """Показывает страницу с результатами поиска"""
    PAGE_SIZE = 5
    start_idx = (page - 1) * PAGE_SIZE
    end_idx = start_idx + PAGE_SIZE
    page_results = results[start_idx:end_idx]

    total_pages = (len(results) + PAGE_SIZE - 1) // PAGE_SIZE

    text = f"🔍 Результаты поиска по запросу: '{query}'\n\n"
    text += f"Найдено преподавателей: {len(results)}\n\n"

    for i, teacher in enumerate(page_results, start_idx + 1):
        text += (
            f"{i}. {teacher['surname']} {teacher['name']} {teacher['middlename']}\n"
            f"   🏛 {teacher['department']}\n"
            f"   ⭐ {teacher['overall_rating']['average']:.1f} ({teacher['overall_rating']['count']} отзывов)\n\n"
        )

    text += f"Страница {page}/{total_pages}"

    keyboard = InlineKeyboardBuilder()

    # Кнопки преподавателей
    for teacher in page_results:
        btn_text = f"{teacher['surname']} {teacher['name'][0]}.{teacher['middlename'][0]}."
        keyboard.button(text=btn_text, callback_data=f"search_teacher_{teacher['id']}")

    # Пагинация
    pagination_buttons = []
    if page > 1:
        pagination_buttons.append(InlineKeyboardButton(text="⬅️",
                                                       callback_data=f"search_page_{page - 1}_{query}"))

    if page < total_pages:
        pagination_buttons.append(InlineKeyboardButton(text="➡️",
                                                       callback_data=f"search_page_{page + 1}_{query}"))

    if pagination_buttons:
        keyboard.row(*pagination_buttons)

    keyboard.row(InlineKeyboardButton(text="🔄 Новый поиск", callback_data="search_teacher"))
    keyboard.row(InlineKeyboardButton(text="Меню", callback_data="back_to_main"))

    await create_new_active_message(message.chat, text, keyboard.as_markup())


# ========== ОСНОВНЫЕ ОБРАБОТЧИКИ ==========

# Обработчик команды /start
@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()

    welcome_text = (
        "🚂 *О преподе РУТ*\n\n"
        "😤 Завалили, обидели или не отпустили пораньше за кашей? Не жалей, пиши!\n"
		"🤗 Если наоборот — дай знать другим!\n\n"
        "Выбери действие:"
    )

    # Создаем первое активное сообщение
    await create_new_active_message(
        message.chat,
        welcome_text, parse_mode="Markdown",
        reply_markup=get_main_menu()
    )


# Обработчик кнопки ТОП-5
@dp.callback_query(F.data == "top5_teachers")
async def show_top_teachers(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    top_teachers = db.get_top_teachers(5)
    if not top_teachers:
        await callback.answer("Пока нет преподавателей с оценками")
        return

    text = "🏆 *ТОП-5 преподавателей:*\n\n"
    keyboard = InlineKeyboardBuilder()
    for i, teacher in enumerate(top_teachers, 1):
        teacher_name = f"{teacher['surname']} {teacher['name']} {teacher['middlename']}"
        text += (
            f"{i}. {teacher_name}\n"
            f"   ⭐ {teacher['overall_rating']['average']:.1f} ({teacher['overall_rating']['count']} отзывов)\n"
            f"   🏛 {teacher['institute']} {teacher['department']}\n\n"
        )
        btn_text = f"{teacher['surname']} {teacher['name'][0]}.{teacher['middlename'][0]}."
        keyboard.button(text=btn_text, callback_data=f"top_teacher_{teacher['id']}")

    keyboard.row(InlineKeyboardButton(text="Меню", callback_data="back_to_main"))
    keyboard.adjust(2, 2)

    # Редактируем текущее сообщение
    await callback.message.edit_text(text, reply_markup=keyboard.as_markup(), parse_mode="Markdown")
    await callback.answer()


# Обработчик кнопки списка преподавателей
@dp.callback_query(F.data == "list_teachers")
async def show_teachers_list(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    teachers = db.get_teachers_page(1, PAGE_SIZE)
    total_teachers = db.get_teachers_count()
    total_pages = (total_teachers + PAGE_SIZE - 1) // PAGE_SIZE

    if not teachers:
        await callback.answer("В базе пока нет преподавателей")
        return

    text = "📋 *Список преподавателей:*\n\n"
    for i, teacher in enumerate(teachers, 1):
        text += (
            f"{i}. {teacher['surname']} {teacher['name']} {teacher['middlename']}\n"
            f"   🏛 {teacher['institute']} {teacher['department']}\n"
            f"   ⭐ {teacher['overall_rating']['average']:.1f} ({teacher['overall_rating']['count']} отзывов)\n\n"
        )
    text += f"Страница 1/{total_pages}"

    keyboard = InlineKeyboardBuilder()
    for teacher in teachers:
        btn_text = f"{teacher['surname']} {teacher['name'][0]}.{teacher['middlename'][0]}."
        keyboard.button(text=btn_text, callback_data=f"list_teacher_{teacher['id']}")

    if total_pages > 1:
        keyboard.button(text="➡️", callback_data="page_2")
    keyboard.adjust(2)
    keyboard.row(InlineKeyboardButton(text="Меню", callback_data="back_to_main"))

    await state.update_data(current_page=1, total_pages=total_pages)

    # Редактируем текущее сообщение
    await callback.message.edit_text(text, reply_markup=keyboard.as_markup(), parse_mode="Markdown")
    await callback.answer()


# Обработчик кнопки поиска
@dp.callback_query(F.data == "search_teacher")
async def search_teachers(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(ReviewStates.waiting_for_search)

    # Создаем новое активное сообщение для поиска
    await create_new_active_message(
        callback.message.chat,
        "Введи фамилию или имя преподавателя для поиска:"
    )
    await callback.answer()


# Обработчик поискового запроса
@dp.message(ReviewStates.waiting_for_search, F.text)
async def handle_search(message: types.Message, state: FSMContext):
    query = message.text.strip()

    if query in ["🏆 ТОП-5 преподавателей", "📋 Полный список", "🔍 Поиск"]:
        await state.clear()
        return

    # Используем умный поиск
    results = db.smart_search(query)

    if not results:
        # Показываем сообщение с кнопками
        await show_no_results_message(message.chat, query)
        # Сбрасываем состояние, так как у нас есть кнопки для навигации
        await state.clear()
        return

    # Сохраняем запрос в состоянии для навигации
    await state.update_data(last_search_query=query)

    # Умный показ результатов
    await show_smart_search_results(message, results, query)
    await state.clear()


# ========== ОБРАБОТЧИКИ ПОИСКА ==========

# Обработчик выбора конкретного преподавателя из поиска
@dp.callback_query(F.data.startswith("choose_teacher_"))
async def handle_choose_teacher(callback: types.CallbackQuery, state: FSMContext):
    teacher_id = int(callback.data.split("_")[2])
    teacher = db.get_teacher_by_id(teacher_id)

    if teacher:
        await show_teacher_card(callback.message, teacher)
    else:
        await callback.answer("Преподаватель не найден")
    await callback.answer()


# Обработчик "Показать еще"
@dp.callback_query(F.data.startswith("show_more_"))
async def handle_show_more(callback: types.CallbackQuery):
    query = callback.data.split("_", 2)[2]  # Получаем оригинальный запрос
    results = db.smart_search(query)

    # Показываем полный список с пагинацией
    await show_search_results_page(callback.message, results, 1, query)
    await callback.answer()


# Обработчик пагинации поиска
@dp.callback_query(F.data.startswith("search_page_"))
async def handle_search_pagination(callback: types.CallbackQuery):
    _, _, page_str, query = callback.data.split("_", 3)
    page = int(page_str)

    results = db.smart_search(query)
    await show_search_results_page(callback.message, results, page, query)
    await callback.answer()


# Обработчик возврата к результатам поиска
@dp.callback_query(F.data == "back_to_search_results")
async def back_to_search_results(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    last_query = data.get('last_search_query', '')

    if last_query:
        results = db.smart_search(last_query)
        await show_smart_search_results(callback.message, results, last_query)
    else:
        await callback.answer("Нет предыдущих результатов поиска")
    await callback.answer()


# ========== ОСТАЛЬНЫЕ ОБРАБОТЧИКИ ==========

# Обработчик пагинации списка
@dp.callback_query(F.data.startswith("page_"))
async def handle_pagination(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    total_pages = data.get('total_pages', 1)

    if callback.data == "page_info":
        await callback.answer(f"Страница {data.get('current_page', 1)} из {total_pages}")
        return

    page_num = int(callback.data.split("_")[1])
    teachers = db.get_teachers_page(page_num, 6)

    if not teachers:
        await callback.answer("Нет данных для этой страницы")
        return

    text = "📋 *Список преподавателей:*\n\n"
    for i, teacher in enumerate(teachers, 1):
        text += (
            f"{i}. {teacher['surname']} {teacher['name']} {teacher['middlename']}\n"
            f"   🏛 {teacher['institute']} {teacher['department']}\n"
            f"   ⭐ {teacher['overall_rating']['average']:.1f} ({teacher['overall_rating']['count']} отзывов)\n\n"
        )

    text += f"Страница {page_num}/{total_pages}"

    keyboard = InlineKeyboardBuilder()
    for teacher in teachers:
        btn_text = f"{teacher['surname']} {teacher['name'][0]}.{teacher['middlename'][0]}."
        keyboard.button(text=btn_text, callback_data=f"list_teacher_{teacher['id']}")

    pagination_buttons = []
    if page_num > 1:
        pagination_buttons.append(InlineKeyboardButton(text="⬅️", callback_data=f"page_{page_num - 1}"))
    pagination_buttons.append(InlineKeyboardButton(text=f"{page_num}/{total_pages}", callback_data="page_info"))
    if page_num < total_pages:
        pagination_buttons.append(InlineKeyboardButton(text="➡️", callback_data=f"page_{page_num + 1}"))

    keyboard.adjust(2)
    if pagination_buttons:
        keyboard.row(*pagination_buttons)

    keyboard.row(InlineKeyboardButton(text="Меню", callback_data="back_to_main"))

    await state.update_data(current_page=page_num)
    await callback.message.edit_text(text, reply_markup=keyboard.as_markup(), parse_mode="Markdown")
    await callback.answer()


# Обработчик клика по преподавателю из списка
@dp.callback_query(F.data.startswith("list_teacher_"))
async def handle_list_teacher_click(callback: types.CallbackQuery, state: FSMContext):
    teacher_id = int(callback.data.split("_")[2])
    teacher = db.get_teacher_by_id(teacher_id)

    if teacher:
        text = (
            f"👨‍🏫 {teacher['surname']} {teacher['name']} {teacher['middlename']}\n"
            f"🏛 {teacher['institute']} {teacher['department']}\n"
            f"🎓 {teacher['title']}\n"
            f"📚 {', '.join(teacher['subjects'])}\n"
            f"⭐ Рейтинг: {teacher['overall_rating']['average']:.1f}/5 ({teacher['overall_rating']['count']} отзывов)"
        )
        await callback.message.edit_text(text, reply_markup=get_teacher_keyboard(teacher_id))
    else:
        await callback.answer("Преподаватель не найден")
    await callback.answer()


# Обработчик клика по преподавателю из топа
@dp.callback_query(F.data.startswith("top_teacher_"))
async def handle_top_teacher_click(callback: types.CallbackQuery, state: FSMContext):
    teacher_id = int(callback.data.split("_")[2])
    teacher = db.get_teacher_by_id(teacher_id)

    if teacher:
        text = (
            f"👨‍🏫 {teacher['surname']} {teacher['name']} {teacher['middlename']}\n"
            f"🏛 {teacher['institute']} {teacher['department']}\n"
            f"🎓 {teacher['title']}\n"
            f"📚 {', '.join(teacher['subjects'])}\n"
            f"⭐ Рейтинг: {teacher['overall_rating']['average']:.1f}/5 ({teacher['overall_rating']['count']} отзывов)"
        )
        await callback.message.edit_text(text, reply_markup=get_teacher_keyboard(teacher_id))
    else:
        await callback.answer("Преподаватель не найден")
    await callback.answer()


# Обработчик возврата в главное меню
@dp.callback_query(F.data == "back_to_main")
async def back_to_main(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    welcome_text = (
        "🚂 *О преподе РУТ*\n\n"
        "😤 Завалили, обидели или не отпустили пораньше за кашей? Не жалей, пиши!\n"
		"🤗 Если наоборот — дай знать другим!\n\n"
        "Выбери действие:"
    )

    # Редактируем текущее сообщение
    await callback.message.edit_text(welcome_text, reply_markup=get_main_menu(), parse_mode="Markdown")
    await callback.answer()


# Обработчик возврата к преподавателю
@dp.callback_query(F.data.startswith("back_to_teacher_"))
async def back_to_teacher(callback: types.CallbackQuery):
    teacher_id = int(callback.data.split("_")[-1])
    teacher = db.get_teacher_by_id(teacher_id)
    if teacher:
        text = (
            f"👨‍🏫 {teacher['surname']} {teacher['name']} {teacher['middlename']}\n"
            f"🏛 {teacher['institute']} {teacher['department']}\n"
            f"🎓 {teacher['title']}\n"
            f"📚 {', '.join(teacher['subjects'])}\n"
            f"⭐ Рейтинг: {teacher['overall_rating']['average']:.1f}/5 ({teacher['overall_rating']['count']} отзывов)"
        )
        await callback.message.edit_text(text, reply_markup=get_teacher_keyboard(teacher_id))
    await callback.answer()


# Обработчик показа отзывов
@dp.callback_query(F.data.startswith("reviews_"))
async def show_reviews(callback: types.CallbackQuery, state: FSMContext):
    teacher_id = int(callback.data.split("_")[1])
    teacher = db.get_teacher_by_id(teacher_id)

    if not teacher:
        await callback.answer("Преподаватель не найден")
        return

    # Фильтруем только отзывы с комментарием и сортируем
    reviews = get_sorted_reviews(db.get_teacher_reviews(teacher_id))

    if not reviews:
        await callback.answer("Пока нет отзывов с комментариями")
        return

    # Сохраняем ВСЕ данные в состоянии
    await state.update_data(
        teacher_id=teacher_id,
        reviews=reviews,
        current_index=0,
        total_reviews=len(reviews)
    )

    # Показываем первый отзыв
    review = reviews[0]
    text = f'⭐️ {review["rating"]}/5\n\n💬 {review["comment"]}\n\n📅 {review["date"]}'

    await callback.message.edit_text(
        text,
        reply_markup=rate_review_keyboard(teacher_id, reviews, 0)
    )
    await callback.answer()


# Обработчики кнопок "следующий / предыдущий" для отзывов
@dp.callback_query(F.data.startswith("review_next_") | F.data.startswith("review_prev_"))
async def review_navigation(callback: types.CallbackQuery, state: FSMContext):
    data = callback.data.split("_")
    direction = data[1]  # "next" или "prev"
    teacher_id = int(data[2])
    current_index = int(data[3])

    # Получаем данные из состояния
    state_data = await state.get_data()
    reviews = state_data.get("reviews", [])

    if not reviews:
        await callback.answer("❌ Ошибка: данные отзывов не найдены")
        return

    # Определяем новый индекс
    if direction == "next":
        new_index = min(current_index + 1, len(reviews) - 1)
    else:
        new_index = max(current_index - 1, 0)

    # Обновляем состояние
    await state.update_data(current_index=new_index)

    # Показываем новый отзыв
    review = reviews[new_index]
    text = f'⭐️ {review["rating"]}/5\n\n💬 {review["comment"]}\n\n📅 {review["date"]}'

    await callback.message.edit_text(
        text,
        reply_markup=rate_review_keyboard(teacher_id, reviews, new_index)
    )
    await callback.answer()


# Обработчик начала оценки
@dp.callback_query(F.data.startswith("rate_"))
async def start_rating(callback: types.CallbackQuery, state: FSMContext):
    teacher_id = int(callback.data.split("_")[1])
    await state.update_data(teacher_id=teacher_id)
    await state.set_state(ReviewStates.waiting_for_rating)

    # Создаем новое активное сообщение с выбором оценки
    await create_new_active_message(
        callback.message.chat,
        "Выбери оценку:",
        reply_markup=get_rating_keyboard(teacher_id)
    )
    await callback.answer()


# Обработчик выбора звезд
@dp.callback_query(ReviewStates.waiting_for_rating, F.data.startswith("stars_"))
async def handle_stars(callback: types.CallbackQuery, state: FSMContext):
    rating = int(callback.data.split("_")[1])
    await state.update_data(rating=rating)
    await state.set_state(ReviewStates.waiting_for_comment)

    # Создаем новое активное сообщение для ввода комментария
    await create_new_active_message(
        callback.message.chat,
        "Напиши комментарий:",
        reply_markup=get_comment_cancel_keyboard()
    )
    await callback.answer()


# Обработчик отмены комментария (без комментария)
@dp.callback_query(ReviewStates.waiting_for_comment, F.data == "no_comment")
async def no_comment(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    db.add_review(data['teacher_id'], str(callback.from_user.id), data['rating'], "")

    # Создаем новое активное сообщение с результатом
    await create_new_active_message(
        callback.message.chat,
        "✅ Оценка сохранена без комментария",
        reply_markup=get_main_menu()
    )
    await state.clear()
    await callback.answer()


# Обработчик комментария
@dp.message(ReviewStates.waiting_for_comment, F.text)
async def handle_comment(message: types.Message, state: FSMContext):
    await state.update_data(comment=message.text)
    await state.set_state(ReviewStates.confirming_comment)
    data = await state.get_data()

    # Создаем новое активное сообщение с подтверждением
    await create_new_active_message(
        message.chat,
        f"Твой комментарий: *{message.text}*\n\nВсё верно?",
        reply_markup=get_confirm_keyboard(),
        parse_mode="Markdown"
    )


# Обработчик подтверждения комментария
@dp.callback_query(ReviewStates.confirming_comment, F.data == "confirm_yes")
async def confirm_comment(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    success = db.add_review(data['teacher_id'], str(callback.from_user.id), data['rating'], data['comment'])

    text = "✅ Отзыв сохранен" if success else "❌ Ошибка при сохранении отзыва"

    # Создаем новое активное сообщение с результатом
    await create_new_active_message(
        callback.message.chat,
        text,
        reply_markup=get_main_menu()
    )
    await state.clear()
    await callback.answer()


# Обработчик отклонения комментария ("Нет")
@dp.callback_query(ReviewStates.confirming_comment, F.data == "confirm_no")
async def reject_comment(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(ReviewStates.waiting_for_comment)

    # Создаем новое активное сообщение для повторного ввода
    await create_new_active_message(
        callback.message.chat,
        "Напиши новый комментарий:",
        reply_markup=get_comment_cancel_keyboard()
    )
    await callback.answer()


# Обработчик лайков/дизлайков
@dp.callback_query(F.data.startswith("like_") | F.data.startswith("dislike_"))
async def handle_review_rating(callback: types.CallbackQuery, state: FSMContext):
    action = "like" if callback.data.startswith("like_") else "dislike"
    review_id = int(callback.data.split("_")[1])
    user_id = str(callback.from_user.id)

    # Получаем данные из состояния
    state_data = await state.get_data()
    reviews = state_data.get("reviews", [])
    teacher_id = state_data.get("teacher_id")
    current_index = state_data.get("current_index", 0)

    if not reviews:
        await callback.answer("❌ Ошибка: данные отзывов не найдены")
        return

    # Находим текущий отзыв в списке
    current_review = None
    for i, review in enumerate(reviews):
        if review["review_id"] == review_id:
            current_review = review
            current_index = i
            break

    if not current_review:
        await callback.answer("❌ Отзыв не найден")
        return

    # Голосуем через базу данных
    if action == "like":
        success = db.rate_review(review_id, user_id, like=1)
        msg_text = "👍 Лайк учтён" if success else "❌ Ты уже голосовал"
    else:
        success = db.rate_review(review_id, user_id, dislike=1)
        msg_text = "👎 Дизлайк учтён" if success else "❌ Ты уже голосовал"

    if success:
        # Обновляем данные в состоянии из базы
        updated_review = db.get_review_by_id(review_id)
        if updated_review:
            # Обновляем счетчики в нашем списке отзывов
            reviews[current_index]["review_likes"] = updated_review.get("review_likes", 0)
            reviews[current_index]["review_dislikes"] = updated_review.get("review_dislikes", 0)
            await state.update_data(reviews=reviews, current_index=current_index)

            # Обновляем сообщение с новыми счетчиками
            review = reviews[current_index]
            text = f'⭐️ {review["rating"]}/5\n\n💬 {review["comment"]}\n\n📅 {review["date"]}'
            keyboard = rate_review_keyboard(teacher_id, reviews, current_index)

            try:
                await callback.message.edit_text(text, reply_markup=keyboard)
            except Exception as e:
                if "message is not modified" not in str(e):
                    print(f"Ошибка при редактировании сообщения: {e}")
        else:
            msg_text = "❌ Ошибка при обновлении отзыва"

    await callback.answer(msg_text)


# Обработчик отмены оценки
@dp.callback_query(ReviewStates.waiting_for_rating, F.data == "cancel_rating")
async def cancel_rating(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    # Создаем новое активное сообщение с главным меню
    await create_new_active_message(
        callback.message.chat,
        "Оценка отменена",
        reply_markup=get_main_menu()
    )
    await callback.answer()


# Обработчик информации о навигации
@dp.callback_query(F.data == "nav_info")
async def handle_nav_info(callback: types.CallbackQuery):
    await callback.answer("Навигация по отзывам")


# Обработчик отмены любого действия
@dp.message(Command("cancel"))
@dp.message(F.text.lower() == "отмена")
async def cancel_handler(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is None:
        await update_message(message, "Нечего отменять")
        return
    await state.clear()
    await update_message(message, "Действие отменено", reply_markup=get_main_menu())


# Обработчик добавления преподавателя
@dp.message(F.text.startswith(".addteacher"))
async def handle_add_teacher(message: types.Message):
    try:
        pattern = r"\.addteacher\s*(.+?),\s*(.+?),\s*(.+?),\s*(.*?),\s*(.+?),\s*(.+?),\s*\[(.*?)\]"
        match = re.match(pattern, message.text)
        if not match:
            raise ValueError(
                "Неверный формат. Пример:\n.addteacher Ф, И, О, Институт, Кафедра, Должность, [Предмет1; Предмет2]")

        surname, name, middlename, institute, department, title, subjects_str = match.groups()
        subjects = [s.strip() for s in subjects_str.split(";") if s.strip()]

        db.add_teacher(surname, name, middlename, institute if institute != '-' else '', department, title, subjects)
        await update_message(message, f"{surname} {name} {middlename} добавлен", reply_markup=get_main_menu())
    except Exception as e:
        await update_message(message, f"Ошибка при добавлении: {str(e)}", reply_markup=get_main_menu())


# Обработчик кнопки предложки
@dp.callback_query(F.data == "suggestions")
async def show_suggestions(callback: types.CallbackQuery, state: FSMContext):
	await state.set_state(ReviewStates.waiting_for_request)

	# Создаем новое активное сообщение для предложки
	await create_new_active_message(
		callback.message.chat,
		"💡 *Предложка*\n\n"
		"Предлагай преподов, пиши замечания",
		parse_mode="Markdown"
	)
	await callback.answer()


# Обработчик текста для предложки
@dp.message(ReviewStates.waiting_for_request, F.text)
async def handle_request(message: types.Message, state: FSMContext):
	request_text = message.text.strip()
	user_id = str(message.from_user.id)

	# Сохраняем запрос в БД предложки
	request_db.save_request(user_id, request_text)

	# Создаем новое активное сообщение с подтверждением
	await create_new_active_message(
		message.chat,
		"✅ Твой запрос отправлен",
		reply_markup=get_main_menu()
	)
	await state.clear()


# Обработчик отмены любого действия (обновляем)
@dp.message(Command("cancel"))
@dp.message(F.text.lower() == "отмена")
async def cancel_handler(message: types.Message, state: FSMContext):
	current_state = await state.get_state()
	if current_state is None:
		await update_message(message, "Нечего отменять")
		return

	# Если отменяем предложку - возвращаем в главное меню
	if current_state == ReviewStates.waiting_for_request.state:
		await create_new_active_message(
			message.chat,
			"❌ Создание запроса отменено",
			reply_markup=get_main_menu()
		)
	else:
		await update_message(message, "Действие отменено", reply_markup=get_main_menu())

	await state.clear()


# Общий обработчик текста
@dp.message(F.text)
async def handle_other_text(message: types.Message, state: FSMContext):
    current_state = await state.get_state()

    # Игнорируем сообщения, если пользователь в режиме предложки, поиска или комментария
    if (current_state == ReviewStates.waiting_for_request.state or
            current_state == ReviewStates.waiting_for_search.state or
            current_state == ReviewStates.waiting_for_comment.state):
        return

    # Отправляем временное сообщение только если не в специфических состояниях
    notice = await message.answer("Используй кнопки меню для навигации")
    await asyncio.sleep(3)
    await notice.delete()


# Запуск бота
async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())