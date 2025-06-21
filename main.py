import uuid
from dotenv import load_dotenv
import os
import stripe
from fastapi import FastAPI, HTTPException, status  # Импортируем status для более читаемых кодов состояния
from pydantic import BaseModel
from typing import List, Optional
from fastapi.middleware.cors import CORSMiddleware  # Импортируем CORSMiddleware


# Загружаем переменные окружения из файла .env
load_dotenv()

# Инициализируем FastAPI приложение
app = FastAPI()

# Получаем переменные
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")
STRIPE_PUBLISHABLE_KEY = os.getenv("STRIPE_PUBLISHABLE_KEY")

# Для CORS
raw_origins = os.getenv("FRONTEND_ORIGINS", "") # Получаем список доменов из переменной окружения
origins = [origin.strip() for origin in raw_origins.split(",") if origin.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,  # Разрешенные домены
    allow_credentials=True,  # Разрешить отправку куки и заголовков авторизации
    allow_methods=["*"],  # Разрешить все HTTP-методы (GET, POST, PUT, DELETE, PATCH, OPTIONS)
    allow_headers=["*"],  # Разрешить все заголовки
)

# --- Настройка Stripe ---
# Получаем секретный ключ Stripe из переменных окружения
# Если ключ не найден, это критическая ошибка, так как без него Stripe работать не будет
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
if not stripe.api_key:
    raise RuntimeError("STRIPE_SECRET_KEY не установлен в переменных окружения")

# Получаем ID цены из переменных окружения
STRIPE_PRICE_ID = os.getenv("STRIPE_PRICE_ID")
if not STRIPE_PRICE_ID:
    raise RuntimeError("STRIPE_PRICE_ID не установлен в переменных окружения")

# URL-адреса для перенаправления после платежа
SUCCESS_URL = os.getenv("FRONTEND_SUCCESS_URL")
CANCEL_URL = os.getenv("FRONTEND_CANCEL_URL")

if not SUCCESS_URL or not CANCEL_URL:
    raise RuntimeError("FRONTEND_SUCCESS_URL или FRONTEND_CANCEL_URL не установлены в переменных окружения")


# --- Модель данных для задачи ---
class TodoItem(BaseModel):
    id: Optional[str] = None
    text: str
    completed: bool = False


# --- НОВАЯ Модель для PUT запроса (только для обновления текста) ---
class UpdateTodoTextPayload(BaseModel):
    text: str


# --- Временное хранилище для задач ---
todos_db: List[TodoItem] = [
    TodoItem(id=str(uuid.uuid4()), text="Купить молоко", completed=False),
    TodoItem(id=str(uuid.uuid4()), text="Прочитать книгу", completed=True),
    TodoItem(id=str(uuid.uuid4()), text="Написать код", completed=False)
]


# НОВЫЙ Эндпоинт для создания платежной сессии Stripe
@app.post("/create-checkout-session") # Изменил название для ясности
async def create_checkout_session():
    """
    Создает новую платежную сессию Stripe Checkout и возвращает URL для перенаправления.
    """
    try:
        checkout_session = stripe.checkout.Session.create(
            line_items=[
                {
                    "price": STRIPE_PRICE_ID, # Используем ID цены, полученный из Stripe Dashboard
                    "quantity": 1,
                },
            ],
            mode="payment", # Указываем, что это одноразовый платеж
            success_url=SUCCESS_URL, # URL для перенаправления после успешной оплаты
            cancel_url=CANCEL_URL,   # URL для перенаправления после отмены оплаты
        )
        # Возвращаем URL сессии фронтенду
        return {"url": checkout_session.url}
    except Exception as e:
        # Логируем ошибку и возвращаем HTTP 500
        print(f"Ошибка при создании платежной сессии Stripe: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Не удалось создать платежную сессию: {e}"
        )

# --- API Эндпоинты --- Create, Read, Update, Delete (CRUD)

# 1. Получить все задачи
@app.get("/todos", response_model=List[TodoItem])
async def get_all_todos(completed: Optional[bool] = None):
    """Возвращает список задач, с возможностью фильтрации по статусу выполнения.
    - `completed`: Если `true`, возвращает только выполненные задачи.
                   Если `false`, возвращает только активные задачи.
                   Если не указан, возвращает все задачи.
    """
    if completed is None:
        return todos_db
    else:
        return [todo for todo in todos_db if todo.completed == completed]


# 2. Добавить новую задачу
@app.post("/todos", response_model=TodoItem, status_code=status.HTTP_201_CREATED)  # Используем status.HTTP_201_CREATED
async def create_todo(todo: TodoItem):
    """Создать новую задачу"""
    # --- ВАЛИДАЦИЯ ---
    trimmed_text = todo.text.strip()  # Удаляем пробелы в начале и конце
    if not trimmed_text:  # Проверяем, что текст не пустой после удаления пробелов
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Текст задачи не может быть пустым"
        )
    if not todo.id or todo.id.strip() == "":
        todo.id = str(uuid.uuid4())
    todo.text = trimmed_text  # Обновляем текст задачи очищенным значением
    todos_db.append(todo)
    return todo


# 3. Получить задачу по ID
@app.get("/todos/{todo_id}", response_model=TodoItem)
async def get_todo_by_id(todo_id: str):
    """
    Возвращает задачу по указанному ID.
    Если задача не найдена, возвращает 404.
    """
    for todo in todos_db:
        if todo.id == todo_id:
            return todo
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Задача не найдена")


# 4. Обновить существующую задачу
@app.put("/todos/{todo_id}", response_model=TodoItem)
async def update_todo(todo_id: str, payload: UpdateTodoTextPayload):
    """
    Обновляет существующую задачу по ID.
    """
    # --- ВАЛИДАЦИЯ ---
    trimmed_text = payload.text.strip()  # Удаляем пробелы в начале и конце
    if not trimmed_text:  # Проверяем, что текст не пустой после удаления пробелов
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Текст задачи не может быть пустым."
        )

    for index, todo in enumerate(todos_db):
        if todo.id == todo_id:
            todos_db[index].text = payload.text
            return todos_db[index]
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Задача не найдена")


# 5. Частично обновить существующую задачу (PATCH)
# Этот метод полезен, если нужно обновить только часть полей, например, только `completed`
@app.patch("/todos/{todo_id}", response_model=TodoItem)
async def patch_todo(todo_id: str, updated_fields: dict):
    """
    Частично обновляет поля существующей задачи по ID.
    """
    # Если в обновляемых полях есть 'text', выполняем валидацию
    if 'text' in updated_fields:
        trimmed_text = updated_fields['text'].strip()
        if not trimmed_text:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Текст задачи не может быть пустым."
            )
        updated_fields['text'] = trimmed_text  # Обновляем поле очищенным значением

    for index, todo in enumerate(todos_db):
        if todo.id == todo_id:
            # Обновляем поля, которые пришли в запросе
            for key, value in updated_fields.items():
                print(f"Обновление поля {key} на значение {value}")  # Для отладки
                setattr(todo, key, value)  # Обновляем атрибут объекта
            todos_db[index] = todo  # Сохраняем обновленный объект
            return todo
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Задача не найдена")


# 6. Удалить задачу
@app.delete("/todos/{todo_id}",
            status_code=status.HTTP_204_NO_CONTENT)  # 204 No Content - успешное удаление без тела ответа
async def delete_todo(todo_id: str):
    """
    Удаляет задачу по ID.
    """
    global todos_db  # Необходимо для изменения глобального списка
    initial_len = len(todos_db)
    todos_db = [todo for todo in todos_db if todo.id != todo_id]
    if len(todos_db) == initial_len:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Задача не найдена")
