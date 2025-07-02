from dotenv import load_dotenv
import uuid
import os
import stripe
import json
from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel
from typing import List, Optional
from fastapi.middleware.cors import CORSMiddleware

# Импорты для Web3
from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware
from eth_account import Account

# Загружаем переменные окружения из файла .env
load_dotenv()

# Инициализируем приложение FastAPI
app = FastAPI()

# --- Конфигурация Stripe ---
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")
STRIPE_PUBLISHABLE_KEY = os.getenv("STRIPE_PUBLISHABLE_KEY")
STRIPE_PRICE_ID = os.getenv("STRIPE_PRICE_ID")
SUCCESS_URL = os.getenv("FRONTEND_SUCCESS_URL")
CANCEL_URL = os.getenv("FRONTEND_CANCEL_URL")

if not STRIPE_SECRET_KEY:
    raise RuntimeError("STRIPE_SECRET_KEY не установлен в переменных окружения")
stripe.api_key = STRIPE_SECRET_KEY

if not STRIPE_PRICE_ID:
    raise RuntimeError("STRIPE_PRICE_ID не установлен в переменных окружения")
if not SUCCESS_URL or not CANCEL_URL:
    raise RuntimeError("FRONTEND_SUCCESS_URL или FRONTEND_CANCEL_URL не установлены в переменных окружения")

# --- Конфигурация CORS ---
raw_origins = os.getenv("FRONTEND_ORIGINS", "")
origins = [origin.strip() for origin in raw_origins.split(",") if origin.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Конфигурация Web3 ---
OWNER_PRIVATE_KEY = os.getenv("OWNER_PRIVATE_KEY")
WEB3_RPC_URL = os.getenv("WEB3_RPC_URL")
NFT_CONTRACT_ADDRESS = os.getenv("NFT_CONTRACT_ADDRESS")
NFT_ABI_FILE_PATH = os.getenv("NFT_ABI_FILE_PATH")

if not OWNER_PRIVATE_KEY or not WEB3_RPC_URL or not NFT_CONTRACT_ADDRESS:
    raise RuntimeError(
        "Переменные окружения Web3 (OWNER_PRIVATE_KEY, WEB3_RPC_URL, NFT_CONTRACT_ADDRESS) не установлены. "
        "Проверьте файл .env и настройки окружения на Render."
    )

# Инициализация провайдера Web3
try:
    w3 = Web3(Web3.HTTPProvider(WEB3_RPC_URL))
    w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)

    if not w3.is_connected():
        raise ConnectionError(f"Не удалось подключиться к узлу Ethereum по URL: {WEB3_RPC_URL}. Проверьте WEB3_RPC_URL в .env")

    # Загрузка ABI из файла, если указан путь
    if NFT_ABI_FILE_PATH:
        with open(NFT_ABI_FILE_PATH, 'r') as abi_file:
            NFT_CONTRACT_ABI = json.load(abi_file)  # Предполагается, что ABI сохранен как список Python
    else:
        # Используем заглушку ABI, если файл не указан (для тестов)
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

    nft_contract = w3.eth.contract(address=w3.to_checksum_address(NFT_CONTRACT_ADDRESS), abi=NFT_CONTRACT_ABI)
    owner_account = Account.from_key(OWNER_PRIVATE_KEY)
    owner_address = owner_account.address

except Exception as e:
    print(f"Ошибка инициализации Web3: {e}")
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Ошибка инициализации Web3: {e}")

# ВРЕМЕННОЕ ХРАНИЛИЩЕ ДЛЯ СОСТОЯНИЯ БЛОКЧЕЙНА (для каждого адреса)
# В реальном приложении это должно быть в БД
user_blockchain_data = {} # { "user_address": { "completed_tasks_count": 0, "claimed_milestone_count": 0 } }

# ... (инициализация Web3) ...

# --- Модель данных для задачи ---
class TodoItem(BaseModel):
    id: Optional[str] = None
    text: str
    completed: bool = False
    user_address: str # Добавляем поле для адреса пользователя

class UpdateTodoTextPayload(BaseModel):
    text: str

# class MintRequest(BaseModel):
#     recipient_address: str
#     token_uri: str = "https://raw.githubusercontent.com/svladimir1010/blockchain-service/main/nft-metadata/tdonft1.json"

# Инициализация todos_db - теперь задачи должны быть привязаны к адресу
TEST_USER_ADDRESS = owner_address

todos_db: List[TodoItem] = [
    TodoItem(id=str(uuid.uuid4()), text="Купить молоко", completed=False, user_address="0x7c5280557c44e10d0d63a1f241293d3f85a80e35"),
    TodoItem(id=str(uuid.uuid4()), text="Прочитать книгу", completed=True, user_address="0x7c5280557c44e10d0d63a1f241293d3f85a80e35"),
    TodoItem(id=str(uuid.uuid4()), text="Написать код", completed=False, user_address="0x7c5280557c44e10d0d63a1f241293d3f85a80e35")
]

# Инициализация данных блокчейна для тестового пользователя
user_blockchain_data[TEST_USER_ADDRESS] = {
    "completed_tasks_count": sum(1 for todo in todos_db if todo.completed and todo.user_address == TEST_USER_ADDRESS),
    "claimed_milestone_count": 0 # Будем получать это из контракта
}

@app.post("/create-checkout-session")
async def create_checkout_session():
    try:
        checkout_session = stripe.checkout.Session.create(
            line_items=[{"price": STRIPE_PRICE_ID, "quantity": 1}],
            mode="payment",
            success_url=SUCCESS_URL,
            cancel_url=CANCEL_URL,
        )
        return {"url": checkout_session.url}
    except Exception as e:
        print(f"Ошибка при создании платежной сессии Stripe: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Не удалось создать платежную сессию: {e}"
        )

# Новый эндпоинт: Получение статуса NFT для пользователя
@app.get("/nft-status/{user_address}")
async def get_nft_status(user_address: str):
    if not w3.is_address(user_address):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Неверный формат адреса пользователя.")

    try:
        checksum_user_address = w3.to_checksum_address(user_address)

        # Получаем количество выполненных задач из контракта
        completed_tasks_on_chain = nft_contract.functions.completedTasks(checksum_user_address).call()
        # Получаем последний заклеймленный порог из контракта
        claimed_tasks_milestone_on_chain = nft_contract.functions.claimedTasksMilestone(checksum_user_address).call()
        # Получаем константу TASKS_PER_NFT из контракта
        tasks_per_nft = nft_contract.functions.TASKS_PER_NFT().call()

        # Рассчитываем, сколько NFT доступно для клейма
        claimable_nfts = (completed_tasks_on_chain // tasks_per_nft) - (claimed_tasks_milestone_on_chain // tasks_per_nft)

        return {
            "user_address": user_address,
            "completed_tasks_on_chain": completed_tasks_on_chain,
            "claimed_tasks_milestone_on_chain": claimed_tasks_milestone_on_chain,
            "tasks_per_nft": tasks_per_nft,
            "claimable_nfts": claimable_nfts,
            "is_claim_available": claimable_nfts > 0
        }
    except Exception as e:
        print(f"Ошибка при получении NFT статуса: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Не удалось получить статус NFT: {str(e)}"
        )


# Новый эндпоинт: Клейм NFT
@app.post("/claim-nft/{user_address}")
async def claim_nft_endpoint(user_address: str):
    if not w3.is_address(user_address):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Неверный формат адреса получателя.")

    try:
        checksum_user_address = w3.to_checksum_address(user_address)

        # Проверяем, есть ли что клеймить (можно повторно проверить на бэкенде перед отправкой транзакции)
        nft_status = await get_nft_status(user_address)
        if not nft_status["is_claim_available"]:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Недостаточно выполненных задач для клейма NFT.")

        nonce = w3.eth.get_transaction_count(owner_address)
        transaction = nft_contract.functions.claimAchievementNFT(
            checksum_user_address
        ).build_transaction({
            'chainId': w3.eth.chain_id,
            'gas': 300000, # Увеличим gas limit, т.к. может быть несколько минтов
            'gasPrice': w3.eth.gas_price,
            'from': owner_address,
            'nonce': nonce,
        })

        signed_txn = w3.eth.account.sign_transaction(transaction, private_key=OWNER_PRIVATE_KEY)
        tx_hash = w3.eth.send_raw_transaction(signed_txn.raw_transaction)
        print(f"Запрос на клейм NFT для адреса: {user_address}, хэш: {tx_hash.hex()}")
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=180) # Увеличим таймаут

        if receipt.status == 1:
            return {"message": "NFT успешно заклеймлены!", "transaction_hash": tx_hash.hex()}
        else:
            # Получаем детали ошибки из транзакции, если возможно
            revert_reason = "Неизвестная ошибка транзакции"
            try:
                # Попытка получить revert reason из отката транзакции
                # Это может потребовать geth или ganache с debug.traceTransaction
                # Или просто симуляцию вызова на локальном узле
                # Для продакшена лучше использовать Alchemy/Infura с расширенным API
                # Или обрабатывать ошибки на уровне контракта с кастомными ошибками
                pass # Пока оставим так, сложно получить revert reason без специфичных инструментов
            except Exception as e:
                print(f"Не удалось получить revert reason: {e}")

            raise Exception(f"Транзакция клейма NFT завершилась неудачно (status: 0). {revert_reason}")

    except Exception as e:
        print(f"Ошибка при клейме NFT: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Не удалось заклеймить NFT: {str(e)}"
        )


@app.get("/todos", response_model=List[TodoItem])
async def get_all_todos(completed: Optional[bool] = None):
    if completed is None:
        return todos_db
    return [todo for todo in todos_db if todo.completed == completed]


@app.post("/todos", response_model=TodoItem, status_code=status.HTTP_201_CREATED)
async def create_todo(todo: TodoItem):
    trimmed_text = todo.text.strip()
    if not trimmed_text:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Текст задачи не может быть пустым")
    if not todo.id or todo.id.strip() == "":
        todo.id = str(uuid.uuid4())

    if not w3.is_address(todo.user_address):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Неверный формат адреса пользователя для задачи.")

    todo.text = trimmed_text
    todos_db.append(todo)
    return todo

# Изменяем patch/put/delete, чтобы они тоже работали с user_address,
# и самое главное - вызывали markTaskCompleted при изменении статуса!
@app.patch("/todos/{todo_id}", response_model=TodoItem)
async def patch_todo(todo_id: str, updated_fields: dict):
    if 'text' in updated_fields:
        trimmed_text = updated_fields['text'].strip()
        if not trimmed_text:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Текст задачи не может быть пустым.")
        updated_fields['text'] = trimmed_text

    for index, todo in enumerate(todos_db):
        if todo.id == todo_id:
            original_completed_status = todo.completed
            user_of_todo = todo.user_address # Адрес пользователя, которому принадлежит задача

            # Обновляем поля задачи
            for key, value in updated_fields.items():
                setattr(todo, key, value)
            todos_db[index] = todo

            # Если статус completed изменился на True, вызываем markTaskCompleted
            if not original_completed_status and todo.completed:
                try:
                    checksum_user_address = w3.to_checksum_address(user_of_todo)
                    nonce = w3.eth.get_transaction_count(owner_address)
                    transaction = nft_contract.functions.markTaskCompleted(
                        checksum_user_address
                    ).build_transaction({
                        'chainId': w3.eth.chain_id,
                        'gas': 100000,
                        'gasPrice': w3.eth.gas_price,
                        'from': owner_address,
                        'nonce': nonce,
                    })

                    signed_txn = w3.eth.account.sign_transaction(transaction, private_key=OWNER_PRIVATE_KEY)
                    tx_hash = w3.eth.send_raw_transaction(signed_txn.raw_transaction)
                    print(f"Вызов markTaskCompleted для {user_of_todo}, хэш: {tx_hash.hex()}")
                    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)

                    if receipt.status == 1:
                        print(f"markTaskCompleted успешно выполнен для {user_of_todo}.")
                        # Обновляем локальный счетчик для проверки (для будущих доработок с БД)
                        # if user_of_todo not in user_blockchain_data:
                        #     user_blockchain_data[user_of_todo] = {"completed_tasks_count": 0, "claimed_milestone_count": 0}
                        # user_blockchain_data[user_of_todo]["completed_tasks_count"] += 1
                    else:
                        print(f"Ошибка: markTaskCompleted транзакция завершилась неудачно (status: 0) для {user_of_todo}.")
                        # Здесь можно добавить логику отката изменения статуса задачи, если транзакция не удалась
                except Exception as e:
                    print(f"Ошибка при вызове markTaskCompleted для {user_of_todo}: {e}")
                    # Здесь также можно добавить логику отката или уведомления пользователя
            return todo
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Задача не найдена")

# Эндпоинт для обновления задачи через PUT (также должен вызывать markTaskCompleted)
@app.put("/todos/{todo_id}", response_model=TodoItem)
async def update_todo(todo_id: str, payload: UpdateTodoTextPayload):
    # PUT по определению заменяет весь ресурс, но в нашем случае это скорее PATCH по полю text
    # Для простоты можно использовать логику PATCH
    return await patch_todo(todo_id, {"text": payload.text})

@app.delete("/todos/{todo_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_todo(todo_id: str):
    global todos_db
    initial_len = len(todos_db)
    # При удалении задачи, если она была выполнена, мы НЕ должны уменьшать completedTasks на блокчейне
    # Логика блокчейна - это достижения, а не "отмена" достижений.
    todos_db = [todo for todo in todos_db if todo.id != todo_id]
    if len(todos_db) == initial_len:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Задача не найдена")

