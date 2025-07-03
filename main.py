from dotenv import load_dotenv
import uuid
import os
import stripe
import json
from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel
from typing import List, Optional
from fastapi.middleware.cors import CORSMiddleware

# Импорты для Web3-взаимодействия с блокчейном
from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware # Для Proof-of-Authority (PoA) сетей (например, Sepolia)
from eth_account import Account # Для работы с приватными ключами и подписи транзакций

# Загружаем переменные окружения из файла .env
load_dotenv()

# Инициализируем приложение FastAPI
app = FastAPI()

# --- Конфигурация Stripe ---
# Загрузка секретного ключа Stripe из переменных окружения
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")
# Загрузка публичного ключа Stripe (для фронтенда, но здесь хранится для полноты)
STRIPE_PUBLISHABLE_KEY = os.getenv("STRIPE_PUBLISHABLE_KEY")
# ID ценового плана Stripe для "премиум" подписки
STRIPE_PRICE_ID = os.getenv("STRIPE_PRICE_ID")
# URL, на который Stripe перенаправит пользователя после успешной оплаты
SUCCESS_URL = os.getenv("FRONTEND_SUCCESS_URL")
# URL, на который Stripe перенаправит пользователя в случае отмены оплаты
CANCEL_URL = os.getenv("FRONTEND_CANCEL_URL")

# Проверка наличия обязательных переменных окружения Stripe
if not STRIPE_SECRET_KEY:
    raise RuntimeError("STRIPE_SECRET_KEY не установлен в переменных окружения")
stripe.api_key = STRIPE_SECRET_KEY # Устанавливаем секретный ключ Stripe API

if not STRIPE_PRICE_ID:
    raise RuntimeError("STRIPE_PRICE_ID не установлен в переменных окружения")
if not SUCCESS_URL or not CANCEL_URL:
    raise RuntimeError("FRONTEND_SUCCESS_URL или FRONTEND_CANCEL_URL не установлены в переменных окружения")

# --- Конфигурация CORS (Cross-Origin Resource Sharing) ---
# Получаем строку разрешенных источников (доменов фронтенда) из переменных окружения
raw_origins = os.getenv("FRONTEND_ORIGINS", "")
# Преобразуем строку в список, разделяя по запятым и удаляя лишние пробелы
origins = [origin.strip() for origin in raw_origins.split(",") if origin.strip()]

# Добавляем middleware для обработки CORS-запросов
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,       # Разрешенные источники
    allow_credentials=True,      # Разрешить отправку куки и заголовков авторизации
    allow_methods=["*"],         # Разрешить все HTTP-методы (GET, POST, PUT, DELETE и т.д.)
    allow_headers=["*"],         # Разрешить все заголовки HTTP-запросов
)

# --- Конфигурация Web3 ---
# Приватный ключ владельца (owner) для подписания блокчейн-транзакций
OWNER_PRIVATE_KEY = os.getenv("OWNER_PRIVATE_KEY")
# URL узла Web3 (например, Infura, Alchemy) для взаимодействия с блокчейном
WEB3_RPC_URL = os.getenv("WEB3_RPC_URL")
# Адрес развернутого смарт-контракта NFT на блокчейне
NFT_CONTRACT_ADDRESS = os.getenv("NFT_CONTRACT_ADDRESS")
# Путь к файлу с ABI (Application Binary Interface) смарт-контракта NFT
NFT_ABI_FILE_PATH = os.getenv("NFT_ABI_FILE_PATH")

# Проверка наличия обязательных переменных окружения Web3
if not OWNER_PRIVATE_KEY or not WEB3_RPC_URL or not NFT_CONTRACT_ADDRESS:
    raise RuntimeError(
        "Переменные окружения Web3 (OWNER_PRIVATE_KEY, WEB3_RPC_URL, NFT_CONTRACT_ADDRESS) не установлены. "
        "Проверьте файл .env и настройки окружения на Render."
    )

# Инициализация провайдера Web3 для подключения к блокчейну
try:
    w3 = Web3(Web3.HTTPProvider(WEB3_RPC_URL))
    # Инжектируем middleware для поддержки PoA-сетей (например, Sepolia, Polygon)
    w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)

    # Проверка подключения к узлу блокчейна
    if not w3.is_connected():
        raise ConnectionError(f"Не удалось подключиться к узлу Ethereum по URL: {WEB3_RPC_URL}. Проверьте WEB3_RPC_URL в .env")

    # Загрузка ABI контракта из файла
    if NFT_ABI_FILE_PATH:
        with open(NFT_ABI_FILE_PATH, 'r') as abi_file:
            NFT_CONTRACT_ABI = json.load(abi_file)
    else:
        # Заглушка ABI, если файл не указан (для тестов или дебага без реального ABI)
        NFT_CONTRACT_ABI = [
            {
                "inputs": [
                    {"internalType": "address", "name": "to", "type": "address"},
                    {"internalType": "string", "name": "tokenURI", "type": "string"}
                ],
                "name": "mintNft",
                "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
                "stateMutability": "nonpayable",
                "type": "function"
            }
        ]

    # Инициализация объекта смарт-контракта
    nft_contract = w3.eth.contract(address=w3.to_checksum_address(NFT_CONTRACT_ADDRESS), abi=NFT_CONTRACT_ABI)
    # Создание объекта аккаунта владельца из приватного ключа
    owner_account = Account.from_key(OWNER_PRIVATE_KEY)
    # Получение адреса владельца
    owner_address = owner_account.address

except Exception as e:
    # Обработка ошибок при инициализации Web3
    print(f"Ошибка инициализации Web3: {e}")
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Ошибка инициализации Web3: {e}")

# ВРЕМЕННОЕ ХРАНИЛИЩЕ ДЛЯ СОСТОЯНИЯ БЛОКЧЕЙНА (для каждого адреса)
# В реальном приложении эти данные (количество выполненных задач, заклеймленные пороги)
# должны постоянно храниться в базе данных, а не в памяти.
user_blockchain_data = {} # Пример структуры: { "user_address": { "completed_tasks_count": 0, "claimed_milestone_count": 0 } }

# --- Модель данных Pydantic для задачи (TodoItem) ---
class TodoItem(BaseModel):
    id: Optional[str] = None # Уникальный ID задачи, опциональный при создании
    text: str              # Текст задачи
    completed: bool = False # Статус выполнения задачи, по умолчанию False
    user_address: str      # Адрес пользователя, которому принадлежит задача

# Модель данных для обновления текста задачи
class UpdateTodoTextPayload(BaseModel):
    text: str

# Инициализация базы данных задач (в памяти)
# ВНИМАНИЕ: TEST_USER_ADDRESS здесь используется для демонстрации
# В реальном приложении это должен быть адрес, полученный от аутентифицированного пользователя
TEST_USER_ADDRESS = owner_address # Используем адрес владельца как тестовый для удобства

todos_db: List[TodoItem] = [
    TodoItem(id=str(uuid.uuid4()), text="Купить молоко", completed=False, user_address="0x7c5280557c44e10d0d63a1f241293d3f85a80e35"),
    TodoItem(id=str(uuid.uuid4()), text="Прочитать книгу", completed=True, user_address="0x7c5280557c44e10d0d63a1f241293d3f85a80e35"),
    TodoItem(id=str(uuid.uuid4()), text="Написать код", completed=False, user_address="0x7c5280557c44e10d0d63a1f241293d3f85a80e35")
]

# Инициализация данных блокчейна для тестового пользователя (локально, для демонстрации)
# В боевом режиме эти данные всегда должны читаться из контракта
user_blockchain_data[TEST_USER_ADDRESS] = {
    "completed_tasks_count": sum(1 for todo in todos_db if todo.completed and todo.user_address == TEST_USER_ADDRESS),
    "claimed_milestone_count": 0 # Это значение всегда должно браться из контракта
}

# --- API Эндпоинты ---

# Эндпоинт для создания платежной сессии Stripe
@app.post("/create-checkout-session")
async def create_checkout_session():
    try:
        # Создаем сессию Stripe Checkout
        checkout_session = stripe.checkout.Session.create(
            line_items=[{"price": STRIPE_PRICE_ID, "quantity": 1}], # Один товар по указанной цене
            mode="payment", # Режим оплаты (единовременный платеж)
            success_url=SUCCESS_URL, # URL для перенаправления после успешной оплаты
            cancel_url=CANCEL_URL,   # URL для перенаправления в случае отмены оплаты
        )
        return {"url": checkout_session.url} # Возвращаем URL для редиректа на страницу Stripe
    except Exception as e:
        print(f"Ошибка при создании платежной сессии Stripe: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Не удалось создать платежную сессию: {e}"
        )

# Эндпоинт для получения статуса NFT для конкретного пользователя
@app.get("/nft-status/{user_address}")
async def get_nft_status(user_address: str):
    if not w3.is_address(user_address):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Неверный формат адреса пользователя.")

    try:
        checksum_user_address = w3.to_checksum_address(user_address)

        # Вызываем методы смарт-контракта для получения данных
        completed_tasks_on_chain = nft_contract.functions.completedTasks(checksum_user_address).call()
        claimed_tasks_milestone_on_chain = nft_contract.functions.claimedTasksMilestone(checksum_user_address).call()
        tasks_per_nft = nft_contract.functions.TASKS_PER_NFT().call()

        # Рассчитываем, сколько NFT доступно для клейма
        claimable_nfts = (completed_tasks_on_chain // tasks_per_nft) - (claimed_tasks_milestone_on_chain // tasks_per_nft)

        return {
            "user_address": user_address,
            "completed_tasks_on_chain": completed_tasks_on_chain,
            "claimed_tasks_milestone_on_chain": claimed_tasks_milestone_on_chain,
            "tasks_per_nft": tasks_per_nft,
            "claimable_nfts": claimable_nfts,
            "is_claim_available": claimable_nfts > 0 # Флаг, указывающий, доступен ли клейм
        }
    except Exception as e:
        print(f"Ошибка при получении NFT статуса: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Не удалось получить статус NFT: {str(e)}"
        )


# Эндпоинт для клейма (получения) NFT
@app.post("/claim-nft/{user_address}")
async def claim_nft_endpoint(user_address: str):
    if not w3.is_address(user_address):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Неверный формат адреса получателя.")

    try:
        checksum_user_address = w3.to_checksum_address(user_address)

        # Дополнительная проверка на бэкенде: есть ли что клеймить
        nft_status = await get_nft_status(user_address)
        if not nft_status["is_claim_available"]:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Недостаточно выполненных задач для клейма NFT.")

        # Получаем текущий nonce для аккаунта владельца
        nonce = w3.eth.get_transaction_count(owner_address)
        # Строим транзакцию для вызова функции claimAchievementNFT на контракте
        transaction = nft_contract.functions.claimAchievementNFT(
            checksum_user_address
        ).build_transaction({
            'chainId': w3.eth.chain_id, # ID цепочки (например, 11155111 для Sepolia)
            'gas': 300000,              # Максимальный лимит газа для транзакции
            'gasPrice': w3.eth.gas_price, # Цена газа (можно получить динамически)
            'from': owner_address,      # Адрес отправителя транзакции (владелец контракта)
            'nonce': nonce,             # Уникальный номер транзакции для предотвращения повторов
        })

        # Подписываем транзакцию приватным ключом владельца
        signed_txn = w3.eth.account.sign_transaction(transaction, private_key=OWNER_PRIVATE_KEY)
        # Отправляем подписанную транзакцию в блокчейн
        tx_hash = w3.eth.send_raw_transaction(signed_txn.raw_transaction)
        print(f"Запрос на клейм NFT для адреса: {user_address}, хэш: {tx_hash.hex()}")
        # Ожидаем подтверждения транзакции (с увеличенным таймаутом)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=180)

        # Проверяем статус транзакции
        if receipt.status == 1:
            return {"message": "NFT успешно заклеймлены!", "transaction_hash": tx_hash.hex()}
        else:
            # Если транзакция не удалась (статус 0)
            revert_reason = "Неизвестная ошибка транзакции"
            # В реальном приложении здесь можно попытаться получить причину отката (revert reason)
            # через отладку транзакции, но это требует дополнительных инструментов/сервисов.
            print(f"Транзакция клейма NFT завершилась неудачно (status: 0).")
            raise Exception(f"Транзакция клейма NFT завершилась неудачно (status: 0). {revert_reason}")

    except Exception as e:
        print(f"Ошибка при клейме NFT: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Не удалось заклеймить NFT: {str(e)}"
        )

# Эндпоинт для получения всех задач (с возможностью фильтрации по статусу)
@app.get("/todos", response_model=List[TodoItem])
async def get_all_todos(completed: Optional[bool] = None):
    if completed is None:
        # Если фильтр не указан, возвращаем все задачи
        return todos_db
    # Фильтруем задачи по статусу выполнения
    return [todo for todo in todos_db if todo.completed == completed]

# Эндпоинт для создания новой задачи
@app.post("/todos", response_model=TodoItem, status_code=status.HTTP_201_CREATED)
async def create_todo(todo: TodoItem):
    trimmed_text = todo.text.strip()
    if not trimmed_text:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Текст задачи не может быть пустым")
    if not todo.id or todo.id.strip() == "":
        todo.id = str(uuid.uuid4()) # Генерируем уникальный ID для новой задачи

    # Проверяем формат адреса пользователя
    if not w3.is_address(todo.user_address):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Неверный формат адреса пользователя для задачи.")

    todo.text = trimmed_text # Обновляем текст на очищенный
    todos_db.append(todo) # Добавляем новую задачу в список
    return todo

# Эндпоинт для частичного обновления задачи (PATCH)
@app.patch("/todos/{todo_id}", response_model=TodoItem)
async def patch_todo(todo_id: str, updated_fields: dict):
    if 'text' in updated_fields:
        trimmed_text = updated_fields['text'].strip()
        if not trimmed_text:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Текст задачи не может быть пустым.")
        updated_fields['text'] = trimmed_text

    for index, todo in enumerate(todos_db):
        if todo.id == todo_id:
            original_completed_status = todo.completed # Сохраняем исходный статус выполнения
            user_of_todo = todo.user_address # Адрес пользователя, которому принадлежит задача

            # Обновляем поля задачи на основе полученных данных
            for key, value in updated_fields.items():
                setattr(todo, key, value)
            todos_db[index] = todo # Обновляем задачу в списке

            # Если статус задачи изменился с False на True (задача стала выполненной)
            if not original_completed_status and todo.completed:
                try:
                    checksum_user_address = w3.to_checksum_address(user_of_todo)
                    # Получаем nonce для отправки транзакции
                    nonce = w3.eth.get_transaction_count(owner_address)
                    # Строим транзакцию для вызова функции markTaskCompleted на контракте
                    transaction = nft_contract.functions.markTaskCompleted(
                        checksum_user_address
                    ).build_transaction({
                        'chainId': w3.eth.chain_id,
                        'gas': 100000,
                        'gasPrice': w3.eth.gas_price,
                        'from': owner_address,
                        'nonce': nonce,
                    })

                    # Подписываем и отправляем транзакцию
                    signed_txn = w3.eth.account.sign_transaction(transaction, private_key=OWNER_PRIVATE_KEY)
                    tx_hash = w3.eth.send_raw_transaction(signed_txn.raw_transaction)
                    print(f"Вызов markTaskCompleted для {user_of_todo}, хэш: {tx_hash.hex()}")
                    # Ожидаем подтверждения транзакции
                    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)

                    if receipt.status == 1:
                        print(f"markTaskCompleted успешно выполнен для {user_of_todo}.")
                        # Здесь можно было бы обновить локальный счетчик или БД, если бы они были постоянными
                    else:
                        print(f"Ошибка: markTaskCompleted транзакция завершилась неудачно (status: 0) для {user_of_todo}.")
                        # В реальном приложении здесь можно добавить логику отката изменения статуса задачи
                        # или уведомления пользователя об ошибке блокчейн-транзакции.
                except Exception as e:
                    print(f"Ошибка при вызове markTaskCompleted для {user_of_todo}: {e}")
                    # Обработка исключений при взаимодействии с блокчейном
            return todo # Возвращаем обновленную задачу
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Задача не найдена")

# Эндпоинт для полного обновления задачи (PUT)
@app.put("/todos/{todo_id}", response_model=TodoItem)
async def update_todo(todo_id: str, payload: UpdateTodoTextPayload):
    # PUT по определению заменяет весь ресурс. Здесь для простоты реализовано как PATCH по полю text,
    # что логически эквивалентно изменению текста задачи.
    return await patch_todo(todo_id, {"text": payload.text})

# Эндпоинт для удаления задачи
@app.delete("/todos/{todo_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_todo(todo_id: str):
    global todos_db # Объявляем, что будем изменять глобальную переменную
    initial_len = len(todos_db) # Сохраняем исходное количество задач
    # Удаляем задачу из списка.
    # Важно: При удалении задачи, если она была выполнена, мы НЕ уменьшаем счетчик completedTasks на блокчейне.
    # Логика блокчейна - это неизменяемые "достижения", а не отмена выполненных действий.
    todos_db = [todo for todo in todos_db if todo.id != todo_id]
    if len(todos_db) == initial_len:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Задача не найдена")