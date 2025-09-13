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

# Глобальная переменная для хранения последнего сообщения
last_message_id = None


# Определение состояний FSM
class ReviewStates(StatesGroup):
	waiting_for_rating = State()
	waiting_for_search = State()
	waiting_for_comment = State()
	confirming_comment = State()


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
			[InlineKeyboardButton(text="⭐ Оценить", callback_data=f"rate_{teacher_id}")],
			[InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_main")]
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


# Клавиатура для отзывов с навигацией
def rate_review_keyboard(review_id, teacher_id, current_index, total_reviews):
	review = db.get_review_by_id(review_id)
	if not review:
		return InlineKeyboardBuilder().as_markup()

	keyboard = InlineKeyboardBuilder()
	keyboard.button(text=f"👍 {review['review_likes']}", callback_data=f"review_like-{review_id}")
	keyboard.button(text=f"👎 {review['review_dislikes']}", callback_data=f"review_dislike-{review_id}")

	# Добавляем навигацию если отзывов больше 1
	if total_reviews > 1:
		nav_buttons = []
		if current_index > 0:
			nav_buttons.append(InlineKeyboardButton(text="⬅️", callback_data=f"nav_prev-{teacher_id}-{current_index}"))
		if current_index < total_reviews - 1:
			nav_buttons.append(InlineKeyboardButton(text="➡️", callback_data=f"nav_next-{teacher_id}-{current_index}"))
		keyboard.row(*nav_buttons)

	keyboard.row(InlineKeyboardButton(text="Вернуться", callback_data=f"back_to_teacher_{teacher_id}"))
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


# Функция для обновления сообщения
async def update_message(message: types.Message, text: str, reply_markup=None, parse_mode=None):
	global last_message_id
	try:
		if last_message_id:
			await bot.edit_message_text(
				chat_id=message.chat.id,
				message_id=last_message_id,
				text=text,
				reply_markup=reply_markup,
				parse_mode=parse_mode
			)
		else:
			msg = await message.answer(text, reply_markup=reply_markup, parse_mode=parse_mode)
			last_message_id = msg.message_id
	except Exception as e:
		# Если сообщение нельзя отредактировать, отправляем новое
		msg = await message.answer(text, reply_markup=reply_markup, parse_mode=parse_mode)
		last_message_id = msg.message_id


# Обработчик команды /start
@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
	await state.clear()
	global last_message_id

	welcome_text = (
		"👋 Добро пожаловать в рейтинг преподавателей!\n\n"
		"Здесь вы можете:\n"
		"• Смотреть рейтинги преподавателей\n"
		"• Читать и оставлять отзывы\n"
		"• Оценивать качество преподавания\n\n"
		"Выберите действие:"
	)

	msg = await message.answer(welcome_text, reply_markup=get_main_menu())
	last_message_id = msg.message_id


# Обработчик кнопки ТОП-5
@dp.message(F.text == "🏆 ТОП-5 преподавателей")
async def show_top_teachers(message: types.Message, state: FSMContext):
	await state.clear()

	top_teachers = db.get_top_teachers(5)
	if not top_teachers:
		await update_message(message, "Пока нет преподавателей с оценками")
		return

	text = "🏆 ТОП-5 преподавателей:\n\n"
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

	keyboard.button(text="⬅️ Назад", callback_data="back_to_main")
	keyboard.adjust(2, 2)

	await update_message(message, text, keyboard.as_markup())


# Обработчик кнопки списка преподавателей
@dp.message(F.text == "📋 Список преподавателей")
async def show_teachers_list(message: types.Message, state: FSMContext):
	await state.clear()

	teachers = db.get_teachers_page(1, 6)
	total_teachers = db.get_teachers_count()
	total_pages = (total_teachers + 5) // 6

	if not teachers:
		await update_message(message, "В базе пока нет преподавателей")
		return

	text = "📋 Список преподавателей:\n\n"
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

	pagination_buttons = []
	if total_pages > 1:
		pagination_buttons.append(InlineKeyboardButton(text="➡️ Вперед", callback_data="page_2"))

	keyboard.adjust(2)
	if pagination_buttons:
		keyboard.row(*pagination_buttons)

	keyboard.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_main"))

	await state.update_data(current_page=1, total_pages=total_pages)
	await update_message(message, text, keyboard.as_markup())


# Обработчик кнопки поиска
@dp.message(F.text == "🔍 Поиск")
async def search_teachers(message: types.Message, state: FSMContext):
	await state.set_state(ReviewStates.waiting_for_search)
	await update_message(message, "Введите фамилию или имя преподавателя для поиска:")


# Обработчик пагинации
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

	text = "📋 Список преподавателей:\n\n"
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
		pagination_buttons.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"page_{page_num - 1}"))
	pagination_buttons.append(InlineKeyboardButton(text=f"{page_num}/{total_pages}", callback_data="page_info"))
	if page_num < total_pages:
		pagination_buttons.append(InlineKeyboardButton(text="➡️ Вперед", callback_data=f"page_{page_num + 1}"))

	keyboard.adjust(2)
	if pagination_buttons:
		keyboard.row(*pagination_buttons)

	keyboard.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_main"))

	await state.update_data(current_page=page_num)
	await callback.message.edit_text(text, reply_markup=keyboard.as_markup())
	await callback.answer()


# Обработчик клика по преподавателю
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
		"👋 Добро пожаловать в рейтинг преподавателей!\n\n"
		"Здесь вы можете:\n"
		"• Смотреть рейтинги преподавателей\n"
		"• Читать и оставлять отзывы\n"
		"• Оценивать качество преподавания\n\n"
		"Выберите действие:"
	)
	await callback.message.edit_text(welcome_text, reply_markup=get_main_menu())
	await callback.answer()


# Обработчик возврата к преподавателю
@dp.callback_query(F.data.startswith("back_to_teacher_"))
async def back_to_teacher(callback: types.CallbackQuery):
	teacher_id = int(callback.data.split("_")[3])
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


# Обработчик нажатия на кнопку "Посмотреть отзывы"
@dp.callback_query(F.data.startswith("reviews_"))
async def show_reviews(callback: types.CallbackQuery, state: FSMContext):
	teacher_id = int(callback.data.split("_")[1])
	teacher = db.get_teacher_by_id(teacher_id)

	if not teacher or not teacher['reviews']:
		await callback.answer("Пока нет отзывов")
		return

	reviews = db.get_teacher_reviews(teacher_id)
	total_reviews = len(reviews)
	await state.update_data(teacher_id=teacher_id, current_review_index=0, total_reviews=total_reviews)

	review = reviews[0]
	text = f'⭐️ {review["rating"]}/5\n\n💬 {review["comment"]}\n\n📅 {review["date"]}'

	await callback.message.edit_text(
		text,
		reply_markup=rate_review_keyboard(review["review_id"], teacher_id, 0, total_reviews)
	)
	await callback.answer()


# Обработчик навигации по отзывам
@dp.callback_query(F.data.startswith("nav_"))
async def handle_review_navigation(callback: types.CallbackQuery, state: FSMContext):
	data = callback.data.split("-")
	action = data[0]
	teacher_id = int(data[1])
	current_index = int(data[2])

	reviews = db.get_teacher_reviews(teacher_id)
	total_reviews = len(reviews)

	if "prev" in action:
		new_index = current_index - 1
	elif "next" in action:
		new_index = current_index + 1
	else:
		await callback.answer()
		return

	if 0 <= new_index < total_reviews:
		review = reviews[new_index]
		text = f'⭐️ {review["rating"]}/5\n\n💬 {review["comment"]}\n\n📅 {review["date"]}'

		await callback.message.edit_text(
			text,
			reply_markup=rate_review_keyboard(review["review_id"], teacher_id, new_index, total_reviews)
		)
		await state.update_data(current_review_index=new_index)

	await callback.answer()


# Обработчик начала оценки
@dp.callback_query(F.data.startswith("rate_"))
async def start_rating(callback: types.CallbackQuery, state: FSMContext):
	teacher_id = int(callback.data.split("_")[1])
	await state.update_data(teacher_id=teacher_id)
	await state.set_state(ReviewStates.waiting_for_rating)
	await callback.message.edit_text("Выберите оценку:", reply_markup=get_rating_keyboard(teacher_id))
	await callback.answer()


# Обработчик выбора звезд
@dp.callback_query(ReviewStates.waiting_for_rating, F.data.startswith("stars_"))
async def handle_stars(callback: types.CallbackQuery, state: FSMContext):
	rating = int(callback.data.split("_")[1])
	await state.update_data(rating=rating)
	await state.set_state(ReviewStates.waiting_for_comment)
	await callback.message.edit_text(
		"Напишите комментарий (или нажмите 'Без комментария'):",
		reply_markup=get_comment_cancel_keyboard()
	)
	await callback.answer()


# Обработчик отмены комментария
@dp.callback_query(ReviewStates.waiting_for_comment, F.data == "no_comment")
async def no_comment(callback: types.CallbackQuery, state: FSMContext):
	data = await state.get_data()
	db.add_review(data['teacher_id'], str(callback.from_user.id), data['rating'], "")
	await callback.message.edit_text("✅ Оценка сохранена без комментария!", reply_markup=get_main_menu())
	await state.clear()
	await callback.answer()


# Обработчик комментария
@dp.message(ReviewStates.waiting_for_comment, F.text)
async def handle_comment(message: types.Message, state: FSMContext):
	await state.update_data(comment=message.text)
	await state.set_state(ReviewStates.confirming_comment)
	data = await state.get_data()

	await update_message(
		message,
		f"Ваш комментарий: *{message.text}*\n\nВсё верно?",
		reply_markup=get_confirm_keyboard(),
		parse_mode="Markdown"
	)


# Обработчик поискового запроса
@dp.message(ReviewStates.waiting_for_search, F.text)
async def handle_search(message: types.Message, state: FSMContext):
	query = message.text.strip()

	if query in ["🏆 ТОП-5 преподавателей", "📋 Список преподавателей", "🔍 Поиск"]:
		await state.clear()
		return

	results = db.search_teachers(query)

	if not results:
		await update_message(message, "Преподаватели не найдены")
	else:
		teacher = results[0]
		text = (
			f"👨‍🏫 {teacher['surname']} {teacher['name']} {teacher['middlename']}\n"
			f"🏛 {teacher['institute']} {teacher['department']}\n"
			f"🎓 {teacher['title']}\n"
			f"📚 {', '.join(teacher['subjects'])}\n"
			f"⭐ Рейтинг: {teacher['overall_rating']['average']:.1f}/5 ({teacher['overall_rating']['count']} отзывов)"
		)
		await update_message(message, text, reply_markup=get_teacher_keyboard(teacher['id']))

	await state.clear()


# Обработчик подтверждения комментария
@dp.callback_query(ReviewStates.confirming_comment, F.data == "confirm_yes")
async def confirm_comment(callback: types.CallbackQuery, state: FSMContext):
	data = await state.get_data()
	success = db.add_review(data['teacher_id'], str(callback.from_user.id), data['rating'], data['comment'])

	if success:
		await callback.message.edit_text("✅ Отзыв успешно сохранен!", reply_markup=get_main_menu())
	else:
		await callback.message.edit_text("❌ Ошибка при сохранении отзыва", reply_markup=get_main_menu())

	await state.clear()
	await callback.answer()


# Обработчик отмены комментария
@dp.callback_query(ReviewStates.confirming_comment, F.data == "confirm_no")
async def reject_comment(callback: types.CallbackQuery, state: FSMContext):
	await state.set_state(ReviewStates.waiting_for_comment)
	await callback.message.edit_text(
		"Напишите новый комментарий:",
		reply_markup=get_comment_cancel_keyboard()
	)
	await callback.answer()


# обработчик лайков/дизлайков
@dp.callback_query(F.data.startswith("review_"))
async def handle_review_rating(callback: types.CallbackQuery, state: FSMContext):
	action, review_id_str = callback.data.split("-")
	review_id = int(review_id_str)
	user_id = str(callback.from_user.id)

	state_data = await state.get_data()
	teacher_id = state_data.get('teacher_id')
	current_index = state_data.get('current_review_index', 0)
	total_reviews = state_data.get('total_reviews', 1)

	if "dislike" in action:
		success = db.rate_review(review_id, user_id, dislike=1)
		message = "👎 Ваш дизлайк учтен!" if success else "❌ Вы уже голосовали за этот отзыв"
	else:
		success = db.rate_review(review_id, user_id, like=1)
		message = "👍 Ваш лайк учтен!" if success else "❌ Вы уже голосовали за этот отзыв"

	if success:
		review = db.get_review_by_id(review_id)
		if review:
			text = f'⭐️ {review["rating"]}/5\n\n💬 {review["comment"]}\n\n📅 {review["date"]}'
			try:
				await callback.message.edit_text(
					text,
					reply_markup=rate_review_keyboard(review_id, teacher_id, current_index, total_reviews)
				)
			except Exception as e:
				if "message is not modified" not in str(e):
					print(f"Ошибка при редактировании сообщения: {e}")

	await callback.answer(message)


# Обработчик отмены оценки
@dp.callback_query(ReviewStates.waiting_for_rating, F.data == "cancel_rating")
async def cancel_rating(callback: types.CallbackQuery, state: FSMContext):
	await state.clear()
	await callback.message.edit_text("Оценка отменена", reply_markup=get_main_menu())
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
		entered_info = message.text.split(', ')
		name = entered_info[0][11:].strip()
		surname = entered_info[1].strip()
		middlename = entered_info[2].strip()
		institute = '' if entered_info[3] == '-' else entered_info[3].strip()
		department = entered_info[4].strip()
		title = entered_info[5].strip()
		subjects = entered_info[6][1:-1].strip().split('; ')

		db.add_teacher(surname, name, middlename, institute, department, title, subjects)
		await update_message(message, f"{surname} {name} {middlename} добавлен", reply_markup=get_main_menu())
	except Exception as e:
		await update_message(message, f"Ошибка при добавлении: {str(e)}", reply_markup=get_main_menu())


# Общий обработчик текста
@dp.message(F.text)
async def handle_other_text(message: types.Message, state: FSMContext):
	current_state = await state.get_state()
	if current_state != ReviewStates.waiting_for_search.state:
		await update_message(message, "Используйте кнопки меню для навигации", reply_markup=get_main_menu())


# Запуск бота
async def main():
	await dp.start_polling(bot)


if __name__ == "__main__":
	asyncio.run(main())