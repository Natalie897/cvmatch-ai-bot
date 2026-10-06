import asyncio
import os
import tempfile

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
)
from database import (
    init_db,
    save_resume,
    get_resume,
    save_analysis,
    get_last_analyses,
    get_analysis_by_id,
    get_analyses_used,
    increment_analyses_used,
    FREE_ANALYSES_LIMIT,
)

from config import BOT_TOKEN
from llm import analyze_resume
from pdf_utils import extract_text_from_pdf


dp = Dispatcher()


class Form(StatesGroup):
    waiting_resume = State()
    waiting_vacancy = State()


main_keyboard = InlineKeyboardMarkup(
    inline_keyboard=[
        [
            InlineKeyboardButton(
                text="📄 Отправить резюме",
                callback_data="send_resume"
            )
        ],
        [
            InlineKeyboardButton(
                text="🔄 Новый анализ",
                callback_data="restart"
            )
        ],
        [
            InlineKeyboardButton(
                text="📚 История анализов",
                callback_data="history"
            )
        ],
        [
            InlineKeyboardButton(
                text="ℹ️ Как это работает",
                callback_data="help"
            )
        ]
    ]
)

analysis_keyboard = InlineKeyboardMarkup(
    inline_keyboard=[
        [
            InlineKeyboardButton(
                text="🔍 Проверить другую вакансию",
                callback_data="another_vacancy"
            )
        ],
        [
            InlineKeyboardButton(
                text="📄 Загрузить другое резюме",
                callback_data="new_resume"
            )
        ],
        [
            InlineKeyboardButton(
                text="🏠 Главное меню",
                callback_data="main_menu"
            )
        ]
    ]
)


def format_analysis(result: dict) -> str:
    matching_skills = "\n".join(
        f"• {skill}"
        for skill in result["matching_skills"]
    )

    missing_skills = "\n".join(
        f"• {skill}"
        for skill in result["missing_skills"]
    )

    recommendations = "\n".join(
        f"• {item}"
        for item in result["recommendations"]
    )

    return (
        "🤖 CVMatch AI\n\n"
        f"🎯 Совпадение: {result['match_percentage']}%\n\n"

        "✅ Подходящие навыки:\n"
        f"{matching_skills}\n\n"

        "❌ Чего не хватает:\n"
        f"{missing_skills}\n\n"

        "💡 Что улучшить:\n"
        f"{recommendations}\n\n"

        "✉️ Сопроводительное письмо:\n"
        f"{result['cover_letter']}"
    )


@dp.message(CommandStart())
async def start_handler(message: Message, state: FSMContext):
    await state.clear()

    await message.answer(
        "Привет! Я CVMatch AI 🤖\n\n"
        "Я помогу сравнить твоё резюме с вакансией.\n\n"
        "Выбери действие:",
        reply_markup=main_keyboard
    )


@dp.callback_query(F.data == "send_resume")
async def send_resume_callback(
    callback: CallbackQuery,
    state: FSMContext
):
    await state.clear()
    await state.set_state(Form.waiting_resume)

    await callback.message.answer(
        "Отправь резюме текстом или PDF-файлом."
    )

    await callback.answer()


@dp.callback_query(F.data == "restart")
async def restart_callback(
    callback: CallbackQuery,
    state: FSMContext
):
    await state.clear()
    await state.set_state(Form.waiting_resume)

    await callback.message.answer(
        "Начинаем новый анализ 🔄\n\n"
        "Отправь резюме текстом или PDF-файлом."
    )

    await callback.answer()


@dp.callback_query(F.data == "help")
async def help_callback(callback: CallbackQuery):
    await callback.message.answer(
        "Как работает CVMatch AI:\n\n"
        "1. Отправь резюме текстом или PDF.\n"
        "2. Отправь текст вакансии.\n"
        "3. AI сравнит резюме с требованиями вакансии.\n"
        "4. Ты получишь процент совпадения, "
        "подходящие и недостающие навыки, "
        "рекомендации и сопроводительное письмо."
    )

    await callback.answer()


@dp.message(Command("restart"))
async def restart_handler(
    message: Message,
    state: FSMContext
):
    await state.clear()
    await state.set_state(Form.waiting_resume)

    await message.answer(
        "Начинаем заново 🔄\n\n"
        "Отправь резюме текстом или PDF-файлом."
    )


@dp.message(Form.waiting_resume, F.text)
async def resume_text_handler(
    message: Message,
    state: FSMContext
):
    await state.update_data(resume=message.text)
    save_resume(
        message.from_user.id,
        message.text
    )

    await message.answer(
        "Резюме получил ✅\n\n"
        "Теперь отправь текст вакансии."
    )

    await state.set_state(Form.waiting_vacancy)

@dp.callback_query(F.data == "history")
async def history_callback(callback: CallbackQuery):
    analyses = get_last_analyses(
        callback.from_user.id,
        limit=5
    )

    if not analyses:
        await callback.message.answer(
            "История анализов пока пустая."
        )
        await callback.answer()
        return

    keyboard = []

    for analysis_id, vacancy, result, created_at in analyses:
        vacancy_preview = vacancy[:40]

        keyboard.append([
            InlineKeyboardButton(
                text=f"#{analysis_id} — {vacancy_preview}",
                callback_data=f"analysis_{analysis_id}"
            )
        ])

    keyboard.append([
        InlineKeyboardButton(
            text="🏠 Главное меню",
            callback_data="main_menu"
        )
    ])

    history_keyboard = InlineKeyboardMarkup(
        inline_keyboard=keyboard
    )

    await callback.message.answer(
        "📚 Последние анализы:\n\n"
        "Выбери анализ, который хочешь открыть:",
        reply_markup=history_keyboard
    )

    await callback.answer()

@dp.callback_query(F.data.startswith("analysis_"))
async def analysis_details_callback(
    callback: CallbackQuery
):
    analysis_id = int(
        callback.data.split("_")[1]
    )

    result = get_analysis_by_id(
        analysis_id,
        callback.from_user.id
    )

    if not result:
        await callback.message.answer(
            "Не удалось найти этот анализ."
        )
        await callback.answer()
        return

    formatted_result = format_analysis(result)

    await callback.message.answer(
        formatted_result,
        reply_markup=main_keyboard
    )

    await callback.answer()

@dp.message(Form.waiting_resume, F.document)
async def resume_pdf_handler(
    message: Message,
    state: FSMContext
):
    document = message.document

    if not document.file_name.lower().endswith(".pdf"):
        await message.answer(
            "Пока я умею принимать только PDF-файлы."
        )
        return

    await message.answer(
        "Получил PDF 📄\n"
        "Извлекаю текст..."
    )

    bot = message.bot
    file = await bot.get_file(document.file_id)

    with tempfile.NamedTemporaryFile(
        suffix=".pdf",
        delete=False
    ) as temp_file:
        temp_path = temp_file.name

    try:
        await bot.download_file(
            file.file_path,
            destination=temp_path
        )

        resume_text = extract_text_from_pdf(temp_path)

        if not resume_text:
            await message.answer(
                "Не удалось извлечь текст из PDF."
            )
            return

        save_resume(
            message.from_user.id,
            resume_text
        )

        await state.update_data(
            resume=resume_text
        )

        await state.set_state(
            Form.waiting_vacancy
        )

        await message.answer(
            "Резюме из PDF получил ✅\n\n"
            "Теперь отправь текст вакансии."
        )

    except Exception as error:
        print("PDF error:", error)

        await message.answer(
            "Не удалось обработать PDF."
        )

    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

@dp.callback_query(F.data == "another_vacancy")
async def another_vacancy_callback(
    callback: CallbackQuery,
    state: FSMContext
):
    data = await state.get_data()

    resume = data.get("resume")

    if not resume:
        resume = get_resume(
            callback.from_user.id
        )

    if not resume:
        await callback.message.answer(
            "Сохранённого резюме пока нет.\n"
            "Загрузи его заново."
        )

        await state.set_state(
            Form.waiting_resume
        )

        await callback.answer()
        return

    await state.update_data(
        resume=resume
    )

    await state.set_state(
        Form.waiting_vacancy
    )

    await callback.message.answer(
        "Отправь текст новой вакансии."
    )

    await callback.answer()


@dp.callback_query(F.data == "new_resume")
async def new_resume_callback(
    callback: CallbackQuery,
    state: FSMContext
):
    await state.clear()
    await state.set_state(Form.waiting_resume)

    await callback.message.answer(
        "Отправь новое резюме текстом или PDF-файлом."
    )

    await callback.answer()

@dp.callback_query(F.data == "main_menu")
async def main_menu_callback(
    callback: CallbackQuery,
    state: FSMContext
):
    await state.clear()

    await callback.message.answer(
        "Главное меню CVMatch AI 🤖",
        reply_markup=main_keyboard
    )

    await callback.answer()

    
@dp.message(Form.waiting_vacancy, F.text)
async def vacancy_handler(
    message: Message,
    state: FSMContext
):
    data = await state.get_data()

    resume = data.get("resume")
    vacancy = message.text

    used = get_analyses_used(
        message.from_user.id
    )

    if used >= FREE_ANALYSES_LIMIT:
        await message.answer(
            "Бесплатные анализы закончились 😔\n\n"
            "Ты уже использовал 3 бесплатных анализа."
        )

        await state.set_state(None)
        return

    await message.answer(
        "Резюме и вакансия получены ✅\n\n"
        "Анализирую соответствие..."
    )

    try:
        result = await asyncio.to_thread(
            analyze_resume,
            resume,
            vacancy
        )
        save_analysis(
            message.from_user.id,
            vacancy,
            result
        )

        increment_analyses_used(
            message.from_user.id
        )
        formatted_result = format_analysis(
            result
        )
        await message.answer(
            formatted_result,
            reply_markup=analysis_keyboard
        )
        used = get_analyses_used(
            message.from_user.id
        )

        remaining = FREE_ANALYSES_LIMIT - used
        await message.answer(
            f"Осталось бесплатных анализов: {remaining}"
        )


    except Exception as error:
        print("Gemini error:", error)

        await message.answer(
            "Сервис AI сейчас временно недоступен.\n"
            "Попробуй позже или используй /restart.",
            reply_markup=main_keyboard
        )

    await state.set_state(None)


async def main():
    init_db()

    bot = Bot(token=BOT_TOKEN)

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())