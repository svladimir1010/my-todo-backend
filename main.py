import uuid
from dotenv import load_dotenv
import os
import stripe
from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel
from typing import List, Optional
from fastapi.middleware.cors import CORSMiddleware

# Web3 imports
from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware # Используем ExtraDataToPOAMiddleware для PoA сетей
from eth_account import Account # Используется для работы с приватными ключами

# Загружаем переменные окружения из файла .env
load_dotenv()

# Инициализируем FastAPI приложение
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

# --- Web3 Configuration ---
OWNER_PRIVATE_KEY = os.getenv("OWNER_PRIVATE_KEY")
WEB3_RPC_URL = os.getenv("WEB3_RPC_URL")
NFT_CONTRACT_ADDRESS = os.getenv("NFT_CONTRACT_ADDRESS")

if not OWNER_PRIVATE_KEY or not WEB3_RPC_URL or not NFT_CONTRACT_ADDRESS:
    # Важно: Эта ошибка указывает на то, что переменные окружения не загружены или отсутствуют.
    # Проверьте ваш .env файл и настройки переменных окружения на Render.
    raise RuntimeError(
        "Web3 environment variables (OWNER_PRIVATE_KEY, WEB3_RPC_URL, NFT_CONTRACT_ADDRESS) are not set. "
        "Please check your .env file and Render environment settings."
    )

# Инициализация Web3 провайдера
try:
    w3 = Web3(Web3.HTTPProvider(WEB3_RPC_URL))
    # Добавляем middleware для Sepolia (Proof of Authority), используя ExtraDataToPOAMiddleware
    w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)

    # Проверка подключения к узлу Ethereum
    if not w3.is_connected():
        raise ConnectionError(f"Не удалось подключиться к Ethereum узлу по URL: {WEB3_RPC_URL}. Проверьте WEB3_RPC_URL в .env")

    # ABI контракта. Скопируйте его из `blockchain-service/artifacts/contracts/TodoAchievementNFT.sol/TodoAchievementNFT.json`
    # и вставьте сюда. Убедитесь, что это Python list of dicts.
    NFT_CONTRACT_ABI = [
        {
          "inputs": [],
          "stateMutability": "nonpayable",
          "type": "constructor"
        },
        {
          "inputs": [
            {
              "internalType": "address",
              "name": "sender",
              "type": "address"
            },
            {
              "internalType": "uint256",
              "name": "tokenId",
              "type": "uint256"
            },
            {
              "internalType": "address",
              "name": "owner",
              "type": "address"
            }
          ],
          "name": "ERC721IncorrectOwner",
          "type": "error"
        },
        {
          "inputs": [
            {
              "internalType": "address",
              "name": "operator",
              "type": "address"
            },
            {
              "internalType": "uint256",
              "name": "tokenId",
              "type": "uint256"
            }
          ],
          "name": "ERC721InsufficientApproval",
          "type": "error"
        },
        {
          "inputs": [
            {
              "internalType": "address",
              "name": "approver",
              "type": "address"
            }
          ],
          "name": "ERC721InvalidApprover",
          "type": "error"
        },
        {
          "inputs": [
            {
              "internalType": "address",
              "name": "operator",
              "type": "address"
            }
          ],
          "name": "ERC721InvalidOperator",
          "type": "error"
        },
        {
          "inputs": [
            {
              "internalType": "address",
              "name": "owner",
              "type": "address"
            }
          ],
          "name": "ERC721InvalidOwner",
          "type": "error"
        },
        {
          "inputs": [
            {
              "internalType": "address",
              "name": "receiver",
              "type": "address"
            }
          ],
          "name": "ERC721InvalidReceiver",
          "type": "error"
        },
        {
          "inputs": [
            {
              "internalType": "address",
              "name": "sender",
              "type": "address"
            }
          ],
          "name": "ERC721InvalidSender",
          "type": "error"
        },
        {
          "inputs": [
            {
              "internalType": "uint256",
              "name": "tokenId",
              "type": "uint256"
            }
          ],
          "name": "ERC721NonexistentToken",
          "type": "error"
        },
        {
          "inputs": [
            {
              "internalType": "address",
              "name": "owner",
              "type": "address"
            }
          ],
          "name": "OwnableInvalidOwner",
          "type": "error"
        },
        {
          "inputs": [
            {
              "internalType": "address",
              "name": "account",
              "type": "address"
            }
          ],
          "name": "OwnableUnauthorizedAccount",
          "type": "error"
        },
        {
          "anonymous": False,
          "inputs": [
            {
              "indexed": True,
              "internalType": "address",
              "name": "owner",
              "type": "address"
            },
            {
              "indexed": True,
              "internalType": "address",
              "name": "approved",
              "type": "address"
            },
            {
              "indexed": True,
              "internalType": "uint256",
              "name": "tokenId",
              "type": "uint256"
            }
          ],
          "name": "Approval",
          "type": "event"
        },
        {
          "anonymous": False,
          "inputs": [
            {
              "indexed": True,
              "internalType": "address",
              "name": "owner",
              "type": "address"
            },
            {
              "indexed": True,
              "internalType": "address",
              "name": "operator",
              "type": "address"
            },
            {
              "indexed": False,
              "internalType": "bool",
              "name": "approved",
              "type": "bool"
            }
          ],
          "name": "ApprovalForAll",
          "type": "event"
        },
        {
          "anonymous": False,
          "inputs": [
            {
              "indexed": False,
              "internalType": "uint256",
              "name": "_fromTokenId",
              "type": "uint256"
            },
            {
              "indexed": False,
              "internalType": "uint256",
              "name": "_toTokenId",
              "type": "uint256"
            }
          ],
          "name": "BatchMetadataUpdate",
          "type": "event"
        },
        {
          "anonymous": False,
          "inputs": [
            {
              "indexed": False,
              "internalType": "uint256",
              "name": "_tokenId",
              "type": "uint256"
            }
          ],
          "name": "MetadataUpdate",
          "type": "event"
        },
        {
          "anonymous": False,
          "inputs": [
            {
              "indexed": True,
              "internalType": "address",
              "name": "recipient",
              "type": "address"
            },
            {
              "indexed": False,
              "internalType": "uint256",
              "name": "tokenId",
              "type": "uint256"
            },
            {
              "indexed": False,
              "internalType": "string",
              "name": "tokenURI",
              "type": "string"
            }
          ],
          "name": "NftMinted",
          "type": "event"
        },
        {
          "anonymous": False,
          "inputs": [
            {
              "indexed": True,
              "internalType": "address",
              "name": "previousOwner",
              "type": "address"
            },
            {
              "indexed": True,
              "internalType": "address",
              "name": "newOwner",
              "type": "address"
            }
          ],
          "name": "OwnershipTransferred",
          "type": "event"
        },
        {
          "anonymous": False,
          "inputs": [
            {
              "indexed": True,
              "internalType": "address",
              "name": "from",
              "type": "address"
            },
            {
              "indexed": True,
              "internalType": "address",
              "name": "to",
              "type": "address"
            },
            {
              "indexed": True,
              "internalType": "uint256",
              "name": "tokenId",
              "type": "uint256"
            }
          ],
          "name": "Transfer",
          "type": "event"
        },
        {
          "inputs": [
            {
              "internalType": "address",
              "name": "to",
              "type": "address"
            },
            {
              "internalType": "uint256",
              "name": "tokenId",
              "type": "uint256"
            }
          ],
          "name": "approve",
          "outputs": [],
          "stateMutability": "nonpayable",
          "type": "function"
        },
        {
          "inputs": [
            {
              "internalType": "address",
              "name": "owner",
              "type": "address"
            }
          ],
          "name": "balanceOf",
          "outputs": [
            {
              "internalType": "uint256",
              "name": "",
              "type": "uint256"
            }
          ],
          "stateMutability": "view",
          "type": "function"
        },
        {
          "inputs": [
            {
              "internalType": "uint256",
              "name": "tokenId",
              "type": "uint256"
            }
          ],
          "name": "getApproved",
          "outputs": [
            {
              "internalType": "address",
              "name": "",
              "type": "address"
            }
          ],
          "stateMutability": "view",
          "type": "function"
        },
        {
          "inputs": [],
          "name": "getTotalMinted",
          "outputs": [
            {
              "internalType": "uint256",
              "name": "",
              "type": "uint256"
            }
          ],
          "stateMutability": "view",
          "type": "function"
        },
        {
          "inputs": [
            {
              "internalType": "address",
              "name": "owner",
              "type": "address"
            },
            {
              "internalType": "address",
              "name": "operator",
              "type": "address"
            }
          ],
          "name": "isApprovedForAll",
          "outputs": [
            {
              "internalType": "bool",
              "name": "",
              "type": "bool"
            }
          ],
          "stateMutability": "view",
          "type": "function"
        },
        {
          "inputs": [
            {
              "internalType": "address",
              "name": "to",
              "type": "address"
            },
            {
              "internalType": "string",
              "name": "tokenURI",
              "type": "string"
            }
          ],
          "name": "mintNft",
          "outputs": [
            {
              "internalType": "uint256",
              "name": "",
              "type": "uint256"
            }
          ],
          "stateMutability": "nonpayable",
          "type": "function"
        },
        {
          "inputs": [],
          "name": "name",
          "outputs": [
            {
              "internalType": "string",
              "name": "",
              "type": "string"
            }
          ],
          "stateMutability": "view",
          "type": "function"
        },
        {
          "inputs": [],
          "name": "owner",
          "outputs": [
            {
              "internalType": "address",
              "name": "",
              "type": "address"
            }
          ],
          "stateMutability": "view",
          "type": "function"
        },
        {
          "inputs": [
            {
              "internalType": "uint256",
              "name": "tokenId",
              "type": "uint256"
            }
          ],
          "name": "ownerOf",
          "outputs": [
            {
              "internalType": "address",
              "name": "",
              "type": "address"
            }
          ],
          "stateMutability": "view",
            "type": "function"
        },
        {
            "inputs": [],
            "name": "renounceOwnership",
            "outputs": [],
            "stateMutability": "nonpayable",
            "type": "function"
        },
        {
            "inputs": [
                {
                    "internalType": "address",
                    "name": "from",
                    "type": "address"
                },
                {
                    "internalType": "address",
                    "name": "to",
                    "type": "address"
                },
                {
                    "internalType": "uint256",
                    "name": "tokenId",
                    "type": "uint256"
                }
            ],
            "name": "safeTransferFrom",
            "outputs": [],
            "stateMutability": "nonpayable",
            "type": "function"
        },
        {
            "inputs": [
                {
                    "internalType": "address",
                    "name": "from",
                    "type": "address"
                },
                {
                    "internalType": "address",
                    "name": "to",
                    "type": "address"
                },
                {
                    "internalType": "uint256",
                    "name": "tokenId",
                    "type": "uint256"
                },
                {
                    "internalType": "bytes",
                    "name": "data",
                    "type": "bytes"
                }
            ],
            "name": "safeTransferFrom",
            "outputs": [],
            "stateMutability": "nonpayable",
            "type": "function"
        },
        {
            "inputs": [
                {
                    "internalType": "address",
                    "name": "operator",
                    "type": "address"
                },
                {
                    "internalType": "bool",
                    "name": "approved",
                    "type": "bool"
                }
            ],
            "name": "setApprovalForAll",
            "outputs": [],
            "stateMutability": "nonpayable",
            "type": "function"
        },
        {
            "inputs": [
                {
                    "internalType": "bytes4",
                    "name": "interfaceId",
                    "type": "bytes4"
                }
            ],
            "name": "supportsInterface",
            "outputs": [
                {
                    "internalType": "bool",
                    "name": "",
                    "type": "bool"
                }
            ],
            "stateMutability": "view",
            "type": "function"
        },
        {
            "inputs": [],
            "name": "symbol",
            "outputs": [
                {
                    "internalType": "string",
                    "name": "",
                    "type": "string"
                }
            ],
            "stateMutability": "view",
            "type": "function"
        },
        {
            "inputs": [
                {
                    "internalType": "uint256",
                    "name": "tokenId",
                    "type": "uint256"
                }
            ],
            "name": "tokenURI",
            "outputs": [
                {
                    "internalType": "string",
                    "name": "",
                    "type": "string"
                }
            ],
            "stateMutability": "view",
            "type": "function"
        },
        {
            "inputs": [
                {
                    "internalType": "address",
                    "name": "from",
                    "type": "address"
                },
                {
                    "internalType": "address",
                    "name": "to",
                    "type": "address"
                },
                {
                    "internalType": "uint256",
                    "name": "tokenId",
                    "type": "uint256"
                }
            ],
            "name": "transferFrom",
            "outputs": [],
            "stateMutability": "nonpayable",
            "type": "function"
        },
        {
            "inputs": [
                {
                    "internalType": "address",
                    "name": "newOwner",
                    "type": "address"
                }
            ],
            "name": "transferOwnership",
            "outputs": [],
            "stateMutability": "nonpayable",
            "type": "function"
        }
    ] # <--- Вставьте сюда ВАШ актуальный ABI, скопированный из artifacts/contracts/TodoAchievementNFT.sol/TodoAchievementNFT.json

    # Создаем объект контракта
    nft_contract = w3.eth.contract(address=w3.to_checksum_address(NFT_CONTRACT_ADDRESS), abi=NFT_CONTRACT_ABI)

    # Адрес владельца, полученный из приватного ключа
    owner_account = Account.from_key(OWNER_PRIVATE_KEY) # Исправлено: используем Account.from_key()
    owner_address = owner_account.address

except Exception as e:
    # Перехватываем ошибки инициализации Web3 и логируем их
    print(f"Ошибка инициализации Web3: {e}")
    # Можно поднять HTTP 500 ошибку, чтобы FastAPI не стартовал, если Web3 критичен
    # Или позволить приложению стартовать, но с отключенным функционалом Web3
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Ошибка инициализации Web3: {e}")


# --- Модель данных для задачи ---
class TodoItem(BaseModel):
    id: Optional[str] = None
    text: str
    completed: bool = False


# --- НОВАЯ Модель для PUT запроса (только для обновления текста) ---
class UpdateTodoTextPayload(BaseModel):
    text: str

# --- Модель для запроса на минт NFT ---
class MintRequest(BaseModel):
    recipient_address: str
    token_uri: str = "https://raw.githubusercontent.com/Anand-M-A/NFT-Metadata/main/basic-nft-metadata.json" # URI по умолчанию


# --- Временное хранилище для задач ---
todos_db: List[TodoItem] = [
    TodoItem(id=str(uuid.uuid4()), text="Купить молоко", completed=False),
    TodoItem(id=str(uuid.uuid4()), text="Прочитать книгу", completed=True),
    TodoItem(id=str(uuid.uuid4()), text="Написать код", completed=False)
]


#  Эндпоинт для создания платежной сессии Stripe
@app.post("/create-checkout-session")
async def create_checkout_session():
    """
    Создает новую платежную сессию Stripe Checkout и возвращает URL для перенаправления.
    """
    try:
        checkout_session = stripe.checkout.Session.create(
            line_items=[
                {
                    "price": STRIPE_PRICE_ID,
                    "quantity": 1,
                },
            ],
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

#  Эндпоинт для минта NFT
@app.post("/mint-nft")
async def mint_nft_endpoint(request: MintRequest):
    """
    Минтит NFT на указанный адрес получателя.
    Вызывается бэкендом, используя приватный ключ владельца контракта.
    """
    # Валидация адреса получателя
    if not w3.is_address(request.recipient_address):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Неверный формат адреса получателя.")

    try:
        # Получаем текущий nonce для транзакции
        # Важно: В продакшене для высокой нагрузки лучше использовать механизм,
        # который гарантирует уникальность nonce (например, Redis или базу данных)
        # и обрабатывать параллельные запросы. Для нашего тестового примера это ОК.
        nonce = w3.eth.get_transaction_count(owner_address)

        # Создаем транзакцию для вызова функции mintNft
        transaction = nft_contract.functions.mintNft(
            w3.to_checksum_address(request.recipient_address),
            request.token_uri
        ).build_transaction({
            'chainId': w3.eth.chain_id, # Получаем chain ID из подключенного узла
            'gasPrice': w3.eth.gas_price, # Получаем текущую цену газа
            'from': owner_address,
            'nonce': nonce,
        })

        # Подписываем транзакцию приватным ключом владельца
        signed_txn = w3.eth.account.sign_transaction(transaction, private_key=OWNER_PRIVATE_KEY)

        # Отправляем подписанную транзакцию
        tx_hash = w3.eth.send_raw_transaction(signed_txn.rawTransaction)

        # Ждем подтверждения транзакции
        # Можно увеличить таймаут, если сеть медленная
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)

        if receipt.status == 1:
            return {"message": "NFT успешно сминтирован!", "transaction_hash": tx_hash.hex()}
        else:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Транзакция минта NFT завершилась неудачно (status: 0).")

    except Exception as e:
        print(f"Ошибка при минте NFT: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Не удалось сминтировать NFT: {e}"
        )


# --- API Эндпоинты --- Create, Read, Update, Delete (CRUD)

# 1. Получить все задачи
@app.get("/todos", response_model=List[TodoItem])
async def get_all_todos(completed: Optional[bool] = None):
    """Возвращает список задач, с возможностью фильтрации по статусу выполнения.
    - `completed`: Если `True`, возвращает только выполненные задачи.
                   Если `False`, возвращает только активные задачи.
                   Если не указан, возвращает все задачи.
    """
    if completed is None:
        return todos_db
    else:
        return [todo for todo in todos_db if todo.completed == completed]


# 2. Добавить новую задачу
@app.post("/todos", response_model=TodoItem, status_code=status.HTTP_201_CREATED)
async def create_todo(todo: TodoItem):
    """Создать новую задачу"""
    trimmed_text = todo.text.strip()
    if not trimmed_text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Текст задачи не может быть пустым"
        )
    if not todo.id or todo.id.strip() == "":
        todo.id = str(uuid.uuid4())
    todo.text = trimmed_text
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
    trimmed_text = payload.text.strip()
    if not trimmed_text:
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
@app.patch("/todos/{todo_id}", response_model=TodoItem)
async def patch_todo(todo_id: str, updated_fields: dict):
    """
    Частично обновляет поля существующей задачи по ID.
    """
    if 'text' in updated_fields:
        trimmed_text = updated_fields['text'].strip()
        if not trimmed_text:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Текст задачи не может быть пустым."
            )
        updated_fields['text'] = trimmed_text

    for index, todo in enumerate(todos_db):
        if todo.id == todo_id:
            for key, value in updated_fields.items():
                setattr(todo, key, value)
            todos_db[index] = todo
            return todo
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Задача не найдена")


# 6. Удалить задачу
@app.delete("/todos/{todo_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_todo(todo_id: str):
    """
    Удаляет задачу по ID.
    """
    global todos_db
    initial_len = len(todos_db)
    todos_db = [todo for todo in todos_db if todo.id != todo_id]
    if len(todos_db) == initial_len:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Задача не найдена")
