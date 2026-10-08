from aiogram import Dispatcher
from .client import client_router
from .admin import admin_router

def register_routers(dp: Dispatcher):
    # Admin router registered first for high priority callback & command routing
    dp.include_router(admin_router)
    dp.include_router(client_router)
