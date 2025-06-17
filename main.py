import uuid
from fastapi import FastAPI, HTTPException
from pydantic  import BaseModel
from typing import List, Optional
from fastapi.middleware.cors import CORSMiddleware # Импортируем CORSMiddleware


# Инициализируем FastAPI приложение
app = FastAPI()


# --- Настройка CORS ---
origins = [
    "http://localhost:5173",  # Адрес React-приложение локально
    "https://my-todo-list-i15p.vercel.app",
    "https://my-todo-list-steel.vercel.app", # Адрес деплойнутого React-приложения
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,       # Разрешенные домены
    allow_credentials=True,      # Разрешить отправку куки и заголовков авторизации
    allow_methods=["*"],         # Разрешить все HTTP-методы (GET, POST, PUT, DELETE, PATCH, OPTIONS)
    allow_headers=["*"],         # Разрешить все заголовки
)

# --- Модель данных для задачи ---
class TodoItem(BaseModel):
    id: Optional[str] = None
    text: str
    completed: bool = False

# --- Временное хранилище для задач ---
todos_db: List[TodoItem] = [
    TodoItem(id=str(uuid.uuid4()), text="Купить молоко", completed=False),
    TodoItem(id=str(uuid.uuid4()), text="Прочитать книгу", completed=True),
    TodoItem(id=str(uuid.uuid4()), text="Написать код", completed=False)
]


# --- API Эндпоинты --- Create, Read, Update, Delete (CRUD)

# 1. Получить все задачи
@app.get("/todos", response_model=List[TodoItem])
async def get_all_todos():
    return todos_db


# 2. Добавить новую задачу
@app.post("/todos", response_model=TodoItem, status_code=201) # status_code=201 для успешного создания
async def create_todo(todo: TodoItem):

    """Создать новую задачу"""
    if not todo.id or todo.id.strip() == "":
        todo.id = str(uuid.uuid4())
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
    raise HTTPException(status_code=404, detail="Задача не найдена")


# 4. Обновить существующую задачу
@app.put("/todos/{todo_id}", response_model=TodoItem)
async def update_todo(todo_id: str, updated_todo: TodoItem):
    """
    Обновляет существующую задачу по ID.
    """
    for index, todo in enumerate(todos_db):
        if todo.id == todo_id:
            todos_db[index] = updated_todo
            return updated_todo
    raise HTTPException(status_code=404, detail="Задача не найдена")


# 5. Частично обновить существующую задачу (PATCH)
# Этот метод полезен, если нужно обновить только часть полей, например, только `completed`
@app.patch("/todos/{todo_id}", response_model=TodoItem)
async def patch_todo(todo_id: str, updated_fields: dict):
    """
    Частично обновляет поля существующей задачи по ID.
    """
    for index, todo in enumerate(todos_db):
        if todo.id == todo_id:
            # Обновляем поля, которые пришли в запросе
            for key, value in updated_fields.items():
                setattr(todo, key, value) # Обновляем атрибут объекта
            todos_db[index] = todo # Сохраняем обновленный объект
            return todo
    raise HTTPException(status_code=404, detail="Задача не найдена")


# 6. Удалить задачу
@app.delete("/todos/{todo_id}", status_code=204) # 204 No Content - успешное удаление без тела ответа
async def delete_todo(todo_id: str):
    """
    Удаляет задачу по ID.
    """
    global todos_db # Необходимо для изменения глобального списка
    initial_len = len(todos_db)
    todos_db = [todo for todo in todos_db if todo.id != todo_id]
    if len(todos_db) == initial_len:
        raise HTTPException(status_code=404, detail="Задача не найдена")