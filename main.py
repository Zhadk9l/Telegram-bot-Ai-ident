import logging
import requests
import asyncio
from aiogram import Bot, Dispatcher, F, Router
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.client.session.aiohttp import AiohttpSession
from datetime import datetime, timedelta
from collections import defaultdict

# Налаштування
BOT_TOKEN = "7691437662:AAFfjvNMBBf9s91RcJ3XPcW3mZDYtac72Us"
BASE_URL = "http://127.0.0.1:8000"

# Стан FSM
class RegisterUser(StatesGroup):
    first_name = State()
    last_name = State()
    email = State()
    phone = State()

class InspectionProcess(StatesGroup):
    waiting_photo = State()

class EndRentalProcess(StatesGroup):
    waiting_photo = State()

# Кнопки
def get_main_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🚗 Моя оренда")],
            [KeyboardButton(text="📜 Історія оренд")],
            [KeyboardButton(text="🚘 Доступні машини")],
            [KeyboardButton(text="📞 Контактна інформація")]
        ],
        resize_keyboard=True
    )

def get_back_menu():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🔙 Назад до головного меню")]],
        resize_keyboard=True
    )

# Ініціалізація
bot = Bot(token=BOT_TOKEN, session=AiohttpSession())
dp = Dispatcher()
router = Router()
dp.include_router(router)
logging.basicConfig(level=logging.INFO)

# /start
@router.message(CommandStart())
async def start_handler(message: Message, state: FSMContext):
    tg_id = message.from_user.id
    response = requests.get(f"{BASE_URL}/get_users/")
    if response.status_code == 200:
        users = response.json()
        existing_user = next((user for user in users if user.get("tg_id") == tg_id), None)
        if existing_user:
            await message.answer(f"👋 Привіт, {existing_user['first_name']}!", reply_markup=get_main_menu())
        else:
            await message.answer("📝 Ви ще не зареєстровані. Введіть ваше ім’я:")
            await state.set_state(RegisterUser.first_name)
    else:
        await message.answer("❌ Помилка при запиті до сервера.")

# Реєстрація
@router.message(RegisterUser.first_name)
async def get_first_name(message: Message, state: FSMContext):
    await state.update_data(first_name=message.text)
    await message.answer("Введіть прізвище:")
    await state.set_state(RegisterUser.last_name)

@router.message(RegisterUser.last_name)
async def get_last_name(message: Message, state: FSMContext):
    await state.update_data(last_name=message.text)
    await message.answer("Введіть email:")
    await state.set_state(RegisterUser.email)

@router.message(RegisterUser.email)
async def get_email(message: Message, state: FSMContext):
    await state.update_data(email=message.text)
    await message.answer("Введіть номер телефону:")
    await state.set_state(RegisterUser.phone)

@router.message(RegisterUser.phone)
async def get_phone_and_register(message: Message, state: FSMContext):
    await state.update_data(phone=message.text)
    data = await state.get_data()
    user_payload = {
        "first_name": data["first_name"],
        "last_name": data["last_name"],
        "email": data["email"],
        "phone": data["phone"],
        "tg_id": message.from_user.id
    }
    response = requests.post(f"{BASE_URL}/create_user/", json=user_payload)
    if response.status_code == 200:
        await message.answer("✅ Ви успішно зареєстровані!", reply_markup=get_main_menu())
    else:
        await message.answer(f"❌ Помилка при реєстрації:\n{response.text}")
    await state.clear()
# Завершити оренду
@router.message(F.text == "🛑 Завершити оренду")
async def finish_rental(message: Message, state: FSMContext):
    tg_id = message.from_user.id
    rentals_resp = requests.get(f"{BASE_URL}/get_rentals_by_tg_id/{tg_id}")
    rentals = rentals_resp.json()
    now = datetime.now()
    current_rental = next((r for r in rentals if datetime.fromisoformat(r["rental_end"]) > now and not r["is_ended"]), None)
    rental_id = current_rental["rental_id"]
    
    # Порівняння ушкоджень
    result_text = await compare_damages(rental_id)
    await message.answer(result_text)
    await my_rental(message)

'''@router.message(F.text == "🛑 Завершити оренду")
async def start_end_rental(message: Message, state: FSMContext):
    await state.set_state(EndRentalProcess.waiting_photo)
    await state.update_data(photo_index=1, total_photos=8)
    await message.answer("📸 Надішліть фото 1 з 8 (після оренди):", reply_markup=ReplyKeyboardRemove())
    

# Обробка фото після оренди
@router.message(EndRentalProcess.waiting_photo, F.photo)
async def handle_end_rental_photo(message: Message, state: FSMContext):
    data = await state.get_data()
    photo_index = data["photo_index"]
    total_photos = data["total_photos"]

    photo = message.photo[-1]
    file = await bot.get_file(photo.file_id)
    file_bytes = await bot.download_file(file.file_path)

    tg_id = message.from_user.id
    rentals_resp = requests.get(f"{BASE_URL}/get_rentals_by_tg_id/{tg_id}")
    rentals = rentals_resp.json()
    now = datetime.now()
    current_rental = next((r for r in rentals if datetime.fromisoformat(r["rental_end"]) > now and not r["is_ended"]), None)
    rental_id = current_rental["rental_id"]
    user_id = current_rental["user_id"]

    # Надсилання на сервер
    files = {"image": ("photo.jpg", file_bytes.getvalue(), "image/jpeg")}
    data = {
        "rental_id": rental_id,
        "user_id": user_id,
        "photo_type": f"after_{photo_index}"
    }
    resp = requests.post(f"{BASE_URL}/process_photo/", data=data, files=files)

    if photo_index < total_photos:
        await state.update_data(photo_index=photo_index + 1)
        await message.answer(f"📸 Надішліть фото {photo_index + 1} з 8:")
    else:
        await state.clear()

        # Порівняння пошкоджень після та до оренди
        message_text = await compare_damages(rental_id)

        await message.answer(message_text)
        await my_rental(message)'''

# Моя оренда
@router.message(F.text == "🚗 Моя оренда")
async def my_rental(message: Message):
    tg_id = message.from_user.id
    try:
        response = requests.get(f"{BASE_URL}/get_rentals_by_tg_id/{tg_id}")
        rentals = response.json()
        if not rentals:
            return await message.answer("🚗 У вас немає активної оренди.", reply_markup=get_back_menu())
        now = datetime.now()
        active_rental = next((r for r in rentals if datetime.fromisoformat(r["rental_end"]) > now and not r["is_ended"]), None)
        if not active_rental:
            return await message.answer("🚗 У вас немає поточної оренди.", reply_markup=get_back_menu())

        rental_start = datetime.fromisoformat(active_rental["rental_start"])
        rental_end = datetime.fromisoformat(active_rental["rental_end"])
        damage_check = active_rental["damage_check"]
        is_ended = active_rental["is_ended"]
        rental_id = active_rental["rental_id"]
        car_id = active_rental["car_id"]

        # Авто
        car_resp = requests.get(f"{BASE_URL}/get_car/{car_id}")
        car_info = f"🚘 Авто ID {car_id}"
        if car_resp.status_code == 200:
            car = car_resp.json()
            car_info = f"🚘 {car['make']} {car['model']} ({car['year']})\nНомер: {car['license_plate']}"

        # Кнопка
        button_text = "Test"
        now_plus_day = now + timedelta(days=1)
        hours_to_end = (rental_end - now).total_seconds() / 3600

        if rental_start.date() in [now.date(), now_plus_day.date()] and not damage_check and not is_ended:
            button_text = "📸 Огляд автомобіля"
        elif 0 < hours_to_end <= 3 and not is_ended and not active_rental.get("has_new_damage", False):
            button_text = "🛑 Завершити оренду"
        elif active_rental.get("has_new_damage", True):
            button_text = "🛑 Виявлено пошкодження. Натисніть, щоб зв'язатися"
        else :
            button_text = "Оренда проходить в плановому режимі"


        keyboard = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text=button_text)],
                [KeyboardButton(text="🔙 Назад до головного меню")]
            ],
            resize_keyboard=True
        )

        await message.answer(
            f"{car_info}\n\n📅 Період оренди:\nз {rental_start.strftime('%Y-%m-%d %H:%M')} "
            f"до {rental_end.strftime('%Y-%m-%d %H:%M')}",
            reply_markup=keyboard
        )
    except Exception as e:
        await message.answer(f"⚠️ Помилка: {str(e)}", reply_markup=get_back_menu())
@router.message(F.text == "🛑 Виявлено пошкодження. Натисніть, щоб зв'язатися")
async def contact_support(message: Message):
    await message.answer("🔧 Зверніться, будь ласка, до служби підтримки:\n📞 +380501234567\n📧 support@rentacar.ua")

# Огляд автомобіля
@router.message(F.text == "📸 Огляд автомобіля")
async def start_inspection(message: Message, state: FSMContext):
    await state.set_state(InspectionProcess.waiting_photo)
    await state.update_data(photo_index=1, total_photos=8)
    await message.answer("📸 Надішліть фото 1 з 8 (огляд авто):", reply_markup=ReplyKeyboardRemove())

# Обробка фото
@router.message(InspectionProcess.waiting_photo, F.photo)
async def handle_inspection_photo(message: Message, state: FSMContext):
    data = await state.get_data()
    photo_index = data["photo_index"]
    total_photos = data["total_photos"]

    # Фото
    photo = message.photo[-1]
    file = await bot.get_file(photo.file_id)
    file_bytes = await bot.download_file(file.file_path)

    # Rental
    tg_id = message.from_user.id
    rentals_resp = requests.get(f"{BASE_URL}/get_rentals_by_tg_id/{tg_id}")
    rentals = rentals_resp.json()
    now = datetime.now()
    current_rental = next(
    (r for r in rentals if datetime.fromisoformat(r["rental_end"]) > now and not r["is_ended"]),
    None
)
    rental_id = current_rental["rental_id"]
    user_id = current_rental["user_id"]
    
    damage_check = current_rental["damage_check"]
    photo_type = f"before_{photo_index}" if not damage_check else f"after_{photo_index}"
    # Надсилання
    files = {"image": ("photo.jpg", file_bytes.getvalue(), "image/jpeg")}
    data = {
        "rental_id": rental_id,
        "user_id": user_id,
        "photo_type": photo_type
    }
    resp = requests.post(f"{BASE_URL}/process_photo/", data=data, files=files)

    if photo_index < total_photos:
        await state.update_data(photo_index=photo_index + 1)
        await message.answer(f"📸 Надішліть фото {photo_index + 1} з 8:")
    else:
        await state.clear()
        # ✅ Оновлюємо статус оренди
        requests.patch(f"{BASE_URL}/update_rental_damage_check/{rental_id}")
        await message.answer("✅ Огляд завершено! Всі 8 фото отримано.")
        await my_rental(message)

# Історія
@router.message(F.text == "📜 Історія оренд")
async def rental_history(message: Message):
    tg_id = message.from_user.id
    try:
        response = requests.get(f"{BASE_URL}/get_rentals_by_tg_id/{tg_id}")
        if response.status_code != 200:
            return await message.answer("❌ Не вдалося отримати історію оренд.", reply_markup=get_back_menu())

        rentals = response.json()
        ended_rentals = [r for r in rentals if r.get("is_ended", False)]

        if not ended_rentals:
            return await message.answer("📜 У вас ще немає завершених оренд.", reply_markup=get_back_menu())

        msg = "📜 Історія завершених оренд:\n\n"
        for rental in ended_rentals:
            rental_start = datetime.fromisoformat(rental["rental_start"])
            rental_end = datetime.fromisoformat(rental["rental_end"])
            car_resp = requests.get(f"{BASE_URL}/get_car/{rental['car_id']}")
            if car_resp.status_code == 200:
                car = car_resp.json()
                msg += f"🚘 {car['make']} {car['model']} ({car['year']}) — {car['license_plate']}\n"
            else:
                msg += "🚘 Авто: невідоме\n"
            msg += f"📅 з {rental_start.strftime('%Y-%m-%d %H:%M')} до {rental_end.strftime('%Y-%m-%d %H:%M')}\n\n"

        await message.answer(msg, reply_markup=get_back_menu())

    except Exception as e:
        await message.answer(f"⚠️ Помилка при отриманні історії: {str(e)}", reply_markup=get_back_menu())


# Доступні машини
@router.message(F.text == "🚘 Доступні машини")
async def available_cars(message: Message):
    response = requests.get(f"{BASE_URL}/get_cars/")
    cars = response.json()
    if cars:
        msg = "🚘 Доступні автомобілі:\n\n"
        for car in cars:
            status_note = " (в оренді)" if car["status"] == "in_rent" else ""
            msg += f"{car['make']} {car['model']} ({car['year']}) — {car['license_plate']}{status_note}\n"
        await message.answer(msg, reply_markup=get_back_menu())
    else:
        await message.answer("❌ Наразі немає доступних авто.", reply_markup=get_back_menu())

# Контакти
@router.message(F.text == "📞 Контактна інформація")
async def contacts(message: Message):
    await message.answer("📞 Телефон: +380501234567\n📧 Email: support@rentacar.ua", reply_markup=get_back_menu())

# Назад
@router.message(F.text == "🔙 Назад до головного меню")
async def back_to_main(message: Message):
    await message.answer("⬅️ Ви повернулись до головного меню.", reply_markup=get_main_menu())
# Порівняння пошкоджень після та до оренди
async def compare_damages(rental_id: int):
    new_damages = []

    for i in range(1, 9):
        before_resp = requests.get(f"{BASE_URL}/get_damages_by_rental/{rental_id}/before_{i}")
        after_resp = requests.get(f"{BASE_URL}/get_damages_by_rental/{rental_id}/after_{i}")

        if before_resp.status_code != 200 or after_resp.status_code != 200:
            continue

        damage_before = [d for d in before_resp.json() if d['confidence'] >= 0.5]
        damage_after = [d for d in after_resp.json() if d['confidence'] >= 0.5]

        before_boxes = [(d['damage_type'], eval(d['box'])) for d in damage_before]
        after_boxes = [(d['damage_type'], eval(d['box'])) for d in damage_after]

        for damage_type, after_box in after_boxes:
            matches = [
                iou(after_box, before_box) > 0.5
                for before_type, before_box in before_boxes
                if before_type == damage_type
            ]
            if not any(matches):
                new_damages.append(damage_type)

    if new_damages:
        requests.patch(f"{BASE_URL}/flag_rental_damage/{rental_id}")
        damage_summary = "\n".join(f"- {d}" for d in set(new_damages))
        return f"🚨 Виявлено нові пошкодження:\n{damage_summary}"
    else:
        requests.patch(f"{BASE_URL}/update_rental_end/{rental_id}")
        return "✅ Оренду завершено без нових пошкоджень."



def iou(box1, box2):
    """Intersection over Union - для оценки похожести двух боксов"""
    x1 = max(box1[0], box2[0])
    y1 = max(box1[1], box2[1])
    x2 = min(box1[2], box2[2])
    y2 = min(box1[3], box2[3])

    inter_area = max(0, x2 - x1) * max(0, y2 - y1)

    area1 = (box1[2] - box1[0]) * (box1[3] - box1[1])
    area2 = (box2[2] - box2[0]) * (box2[3] - box2[1])

    union_area = area1 + area2 - inter_area

    if union_area == 0:
        return 0
    return inter_area / union_area


# Запуск
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
