import uuid
from fastapi import FastAPI, HTTPException, status  # Импортируем status для более читаемых кодов состояния
from pydantic import BaseModel
from typing import List, Optional
from fastapi.middleware.cors import CORSMiddleware  # Импортируем CORSMiddleware

# Инициализируем FastAPI приложение
app = FastAPI()

# --- Настройка CORS ---
origins = [
    "http://localhost:5173",  # Адрес React-приложение локально
    "https://my-todo-list-i15p.vercel.app",
    "https://my-todo-list-steel.vercel.app",  # Адрес деплойнутого React-приложения
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,  # Разрешенные домены
    allow_credentials=True,  # Разрешить отправку куки и заголовков авторизации
    allow_methods=["*"],  # Разрешить все HTTP-методы (GET, POST, PUT, DELETE, PATCH, OPTIONS)
    allow_headers=["*"],  # Разрешить все заголовки
)


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
