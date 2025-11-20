#!/usr/bin/env python3
"""
scaffold.py — створює каркас Telegram‑бота на aiogram 3 з базовою структурою проєкту.
"""

import argparse
from pathlib import Path
from textwrap import dedent


def create_dirs(root: Path, dirs: list[Path]) -> None:
    for d in dirs:
        full = root / d
        full.mkdir(parents=True, exist_ok=True)
        print(f"[DIR]  {full}")


def create_file(root: Path, rel_path: Path, content: str, overwrite: bool = False) -> None:
    full = root / rel_path
    if full.exists() and not overwrite:
        print(f"[SKIP] {full} (already exists)")
        return
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(content, encoding="utf-8")
    print(f"[FILE] {full}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Створити каркас Telegram‑бота (aiogram 3, .env, requirements, .gitignore)."
    )
    parser.add_argument(
        "--name",
        "-n",
        default="mt_bot",
        help="Назва кореневої папки проєкту (default: mt_bot)",
    )
    args = parser.parse_args()

    project_root = Path(args.name).resolve()
    print(f"Створюємо проєкт у: {project_root}")

    # --- директорії проєкту ---
    dir_list = [
        Path("."),               # корінь
        Path("app"),
        Path("app/config"),
        Path("app/db"),
        Path("app/models"),
        Path("app/services"),
        Path("app/handlers"),
        Path("app/handlers/user"),
        Path("app/handlers/admin"),
        Path("app/keyboards"),
        Path("app/utils"),
        Path("data"),            # сюди можна класти БД, логи, імпортовані файли
    ]
    create_dirs(project_root, dir_list)

    # --- __init__.py для пакетів ---
    init_paths = [
        Path("app/__init__.py"),
        Path("app/config/__init__.py"),
        Path("app/db/__init__.py"),
        Path("app/models/__init__.py"),
        Path("app/services/__init__.py"),
        Path("app/handlers/__init__.py"),
        Path("app/handlers/user/__init__.py"),
        Path("app/handlers/admin/__init__.py"),
        Path("app/keyboards/__init__.py"),
        Path("app/utils/__init__.py"),
    ]
    for p in init_paths:
        create_file(project_root, p, content="# Ініціалізація пакета\n", overwrite=False)

    # --- main.py: точка входу бота (поки мінімальний каркас) ---
    main_py = dedent(
        """\
        """
    ) + dedent(
        """\
        """
    ) + dedent(
        """\
        import asyncio

        from aiogram import Bot, Dispatcher
        from aiogram.enums import ParseMode
        from aiogram.types import Message
        from aiogram.filters import CommandStart

        from app.config.settings import Settings


        async def on_startup(bot: Bot) -> None:
            # Тут можна додати логіку, яка виконується при старті бота
            print("Bot started")


        async def on_shutdown(bot: Bot) -> None:
            # Тут можна закрити підключення до БД, почистити ресурси тощо
            print("Bot stopped")


        def register_basic_handlers(dp: Dispatcher) -> None:
            @dp.message(CommandStart())
            async def cmd_start(message: Message) -> None:
                await message.answer(
                    "Привіт! Це каркас бота для роботи з мертвим товаром. "
                    "Функціонал поки що не реалізований."
                )


        async def main() -> None:
            settings = Settings()
            bot = Bot(token=settings.BOT_TOKEN, parse_mode=ParseMode.HTML)
            dp = Dispatcher()

            register_basic_handlers(dp)

            dp.startup.register(on_startup)
            dp.shutdown.register(on_shutdown)

            await dp.start_polling(bot)


        if __name__ == "__main__":
            asyncio.run(main())
        """
    )
    create_file(project_root, Path("app/main.py"), main_py, overwrite=False)

    # --- config/settings.py: читання налаштувань із .env ---
    settings_py = dedent(
        """\
        from pydantic import BaseSettings, Field


        class Settings(BaseSettings):
            \"\"\"Базові налаштування застосунку (читаються з .env).\"\"\"

            BOT_TOKEN: str = Field(..., description="Telegram Bot API token")
            DB_ENGINE: str = Field("sqlite", description="Тип БД: sqlite / postgres / mysql")
            DB_URL: str = Field(
                "sqlite:///data/bot.db",
                description="Рядок підключення до БД (для sqlite — шлях до файлу)",
            )

            class Config:
                env_file = ".env"
                env_file_encoding = "utf-8"
        """
    )
    create_file(project_root, Path("app/config/settings.py"), settings_py, overwrite=False)

    # --- прості заглушки для шару БД ---
    db_base_py = dedent(
        """\
        \"\"\"Базові інтерфейси репозиторіїв та фабрика підключень до БД.

        Тут будуть:
        - абстрактні класи / протоколи для ItemsRepository, UserListsRepository тощо;
        - функція, яка за DB_ENGINE з .env повертає конкретну реалізацію (sqlite / postgres ...).
        \"\"\"
        from typing import Protocol


        class ItemsRepository(Protocol):
            \"\"\"Інтерфейс роботи з товарами (items).\"\"\"

            async def get_by_sku(self, sku: str):
                ...

            async def upsert_from_import(self, items: list[dict]):
                ...


        # Аналогічно будуть інтерфейси для UserListsRepository, ImportsRepository і т.д.
        """
    )
    create_file(project_root, Path("app/db/base.py"), db_base_py, overwrite=False)

    sqlite_py = dedent(
        """\
        \"\"\"Реалізація репозиторіїв для SQLite (локальна розробка).

        TODO:
        - підключення через aiosqlite;
        - створення таблиць, міграції (мінімально);
        - реалізація методів з base.ItemsRepository та інших репозиторіїв.
        \"\"\"
        """
    )
    create_file(project_root, Path("app/db/sqlite.py"), sqlite_py, overwrite=False)

    # --- requirements.txt ---
    requirements_txt = dedent(
        """\
        aiogram>=3.0.0
        pydantic>=2.0.0
        python-dotenv>=1.0.0
        aiosqlite>=0.19.0
        """
    )
    create_file(project_root, Path("requirements.txt"), requirements_txt, overwrite=False)

    # --- .env.example (зразок) ---
    env_example = dedent(
        """\
        # Перейменуй цей файл у .env і заповни значеннями

        BOT_TOKEN=your-telegram-bot-token-here
        DB_ENGINE=sqlite
        DB_URL=sqlite:///data/bot.db
        """
    )
    create_file(project_root, Path(".env.example"), env_example, overwrite=False)

    # --- .gitignore ---
    gitignore = dedent(
        """\
        # Python
        __pycache__/
        *.py[cod]
        *.pyo
        *.pyd

        # Venv
        .venv/
        venv/
        env/

        # Editors
        .vscode/
        .idea/

        # Env & secrets
        .env
        .env.*

        # Databases & data
        *.db
        *.sqlite
        *.sqlite3
        data/*.db
        data/*.sqlite*
        data/imports/
        data/logs/

        # OS junk
        .DS_Store
        thumbs.db
        """
    )
    create_file(project_root, Path(".gitignore"), gitignore, overwrite=False)

    # --- README.md як маленький "подарунок" ---
    readme_md = dedent(
        f"""\
        # {args.name}

        Каркас Telegram‑бота на aiogram 3 для роботи з мертвим товаром (МТ), списками збору та смарт‑імпортом.  

        ## Швидкий старт

        1. Створи та активуй віртуальне середовище (опційно).
        2. Встанови залежності:
           ```
           pip install -r requirements.txt
           ```
        3. Зроби копію `.env.example`:
           ```
           cp .env.example .env
           ```
           Заповни `BOT_TOKEN` і за потреби `DB_ENGINE` / `DB_URL`.
        4. Запусти бота:
           ```
           python -m app.main
           ```

        Далі крок за кроком будемо наповнювати цю структуру реальною логікою.
        """
    )
    create_file(project_root, Path("README.md"), readme_md, overwrite=False)

    print("\nГотово. Каркас проєкту створено.")


if __name__ == "__main__":
    main()
