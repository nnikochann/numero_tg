"""
Модуль для обработки вебхуков платежей ЮKassa.
Предоставляет функции для проверки и обработки платежей.
"""

import logging
import json
import hmac
import hashlib
import os
from aiohttp import web
from datetime import datetime, timedelta
from typing import Dict, Any

# Импортируем необходимые модули
try:
    from database_sqlite import Database  # Сначала пробуем импортировать SQLite версию
except ImportError:
    from database import Database  # Если нет, используем оригинальную

# Настройка логгирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Секретный ключ для проверки подписи уведомлений от ЮKassa
YUKASSA_SECRET_KEY = os.getenv("YUKASSA_SECRET_KEY", "your_yukassa_secret_key")
TEST_MODE = os.getenv("TEST_MODE", "false").lower() == "true"

# Инициализация базы данных
db = Database()


async def verify_yukassa_payment(request):
    """
    Проверяет подлинность вебхука от ЮKassa.
    
    Args:
        request: aiohttp Request объект
        
    Returns:
        bool: True если вебхук подлинный, False в противном случае
    """
    # В тестовом режиме всегда возвращаем True
    if TEST_MODE:
        return True
        
    try:
        # Проверка наличия заголовка X-Signature
        if 'X-Signature' not in request.headers:
            logger.warning("Missing X-Signature header")
            return False
        
        # Получение подписи из заголовка
        signature = request.headers['X-Signature']
        
        # Получение тела запроса
        body = await request.read()
        
        # Вычисление HMAC-SHA256 подписи
        calculated_signature = hmac.new(
            YUKASSA_SECRET_KEY.encode(),
            body,
            hashlib.sha256
        ).hexdigest()
        
        # Проверка подписи
        if not hmac.compare_digest(signature, calculated_signature):
            logger.warning("Invalid signature")
            return False
            
        return True
    except Exception as e:
        logger.error(f"Error verifying payment: {e}")
        return False


async def handle_successful_payment(payment_data: Dict[str, Any]) -> bool:
    """
    Обрабатывает успешный платеж от ЮKassa.
    
    Args:
        payment_data: Данные платежа от ЮKassa
        
    Returns:
        bool: True если обработка прошла успешно, False в противном случае
    """
    try:
        # Инициализация базы данных
        await db.init()
        
        # Проверяем статус платежа
        if payment_data.get('status') != 'succeeded':
            logger.info(f"Payment not succeeded, status: {payment_data.get('status')}")
            return False
        
        # Извлечение необходимых данных
        payment_id = payment_data.get('id')
        amount = payment_data.get('amount', {}).get('value')
        currency = payment_data.get('amount', {}).get('currency')
        
        # Получение метаданных заказа
        metadata = payment_data.get('metadata', {})
        order_id = metadata.get('order_id')
        
        if not order_id:
            logger.error("No order_id in payment metadata")
            return False
        
        try:
            order_id = int(order_id)
        except ValueError:
            logger.error(f"Invalid order ID in metadata: {order_id}")
            return False
        
        # Получение заказа из БД
        order = await db.get_order(order_id)
        if not order:
            logger.error(f"Order not found: {order_id}")
            return False
            
        # Обновление статуса заказа в БД
        await db.update_order_status(order_id, 'paid')
        
        # Обработка различных типов продуктов
        if order['product'] == 'full_report':
            # Генерация и отправка PDF отчета
            await process_full_report_payment(order)
            
        elif order['product'] == 'compatibility':
            # Генерация и отправка отчета о совместимости
            await process_compatibility_payment(order)
            
        elif order['product'] == 'subscription_month':
            # Активация подписки
            await process_subscription_payment(order)
        
        return True
        
    except Exception as e:
        logger.error(f"Error processing successful payment: {e}")
        return False


async def process_full_report_payment(order: Dict[str, Any]):
    """
    Обрабатывает оплату полного отчета.
    
    Args:
        order: Данные заказа
    """
    # Здесь должен быть код для генерации и отправки PDF-отчета
    # В рамках этого файла мы только логируем событие
    logger.info(f"Processing full report payment for order: {order['id']}")
    
    # В реальном коде здесь должен быть вызов функций из bot.py для отправки отчета


async def process_compatibility_payment(order: Dict[str, Any]):
    """
    Обрабатывает оплату отчета о совместимости.
    
    Args:
        order: Данные заказа
    """
    logger.info(f"Processing compatibility report payment for order: {order['id']}")
    
    # В реальном коде здесь должен быть вызов функций из bot.py для отправки отчета


async def process_subscription_payment(order: Dict[str, Any]):
    """
    Обрабатывает оплату подписки.
    
    Args:
        order: Данные заказа
    """
    logger.info(f"Processing subscription payment for order: {order['id']}")
    
    # Активация подписки в БД
    now = datetime.now().date()
    next_charge = now + timedelta(days=30)
    
    # Получение пользователя
    user_id = order['user_id']
    
    # Создание записи о подписке
    await db.create_subscription(user_id, "active")
    
    # В реальном коде здесь должен быть вызов функций из bot.py для отправки уведомления


async def handle_payment_webhook(request: web.Request) -> web.Response:
    """
    Обрабатывает вебхуки от ЮKassa.
    
    Args:
        request: aiohttp Request объект
        
    Returns:
        aiohttp.web.Response
    """
    # Проверка подлинности вебхука
    if not await verify_yukassa_payment(request):
        return web.Response(status=401, text="Unauthorized")
        
    try:
        # Получение данных запроса
        data = await request.json()
        logger.info(f"Received payment webhook: {data}")
        
        # В тестовом режиме всегда возвращаем успешный ответ
        if TEST_MODE:
            logger.info("Test mode: Simulating successful payment processing")
            return web.Response(status=200, text="Payment webhook processed in test mode")
        
        # Проверка типа уведомления
        event = data.get('event')
        if event == 'payment.succeeded':
            payment_data = data.get('object')
            
            if await handle_successful_payment(payment_data):
                return web.Response(status=200, text="Payment processed successfully")
            else:
                return web.Response(status=500, text="Error processing payment")
        
        # Обрабатываем другие типы уведомлений
        return web.Response(status=200, text="Notification received")
        
    except Exception as e:
        logger.error(f"Error in payment webhook handler: {e}")
        return web.Response(status=500, text=f"Error: {str(e)}")


async def setup_payment_webhook_server(host='0.0.0.0', port=8080):
    """
    Настраивает и запускает веб-сервер для обработки вебхуков платежей.
    
    Args:
        host: Хост для веб-сервера
        port: Порт для веб-сервера
    """
    # Инициализация базы данных
    await db.init()
    
    app = web.Application()
    app.router.add_post('/payment', handle_payment_webhook)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    
    logger.info(f"Starting payment webhook server on {host}:{port}")
    await site.start()
    
    return runner
