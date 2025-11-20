-- Увімкнути підтримку зовнішніх ключів у SQLite
PRAGMA foreign_keys = ON;

----------------------------------------------------------------------
-- Таблиця користувачів
----------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS users (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    tg_user_id      INTEGER NOT NULL UNIQUE,
    username        TEXT,
    full_name       TEXT,
    role            TEXT NOT NULL DEFAULT 'user',   -- user / admin / superadmin
    created_at      TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TEXT
);

----------------------------------------------------------------------
-- Таблиця товарів (items)
----------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS items (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    sku             TEXT NOT NULL UNIQUE,           -- 8-значний артикул
    dept_code       TEXT NOT NULL,                  -- код відділу (напр. 610)
    dept_name       TEXT,                           -- назва відділу
    group_name      TEXT,                           -- група/категорія (Фреш, Опалення...)
    name            TEXT NOT NULL,                  -- назва товару
    unit            TEXT DEFAULT 'шт',              -- одиниця виміру
    mt_months       REAL,                           -- "без руху, міс." з імпорту
    base_qty        REAL DEFAULT 0,                 -- базовий залишок
    base_sum        REAL DEFAULT 0,                 -- базова сума залишку
    price           REAL,                           -- ціна за одиницю
    base_reserve    REAL DEFAULT 0,                 -- резерв з імпорту (якщо є)
    is_active       INTEGER NOT NULL DEFAULT 1,     -- 1 = активний, 0 = відключений
    created_at      TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TEXT
);

CREATE INDEX IF NOT EXISTS idx_items_dept_code ON items(dept_code);
CREATE INDEX IF NOT EXISTS idx_items_mt_months ON items(mt_months);

----------------------------------------------------------------------
-- Таблиця списків користувачів (user_lists)
-- Один список = один користувач + один відділ
----------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS user_lists (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL,
    dept_code       TEXT NOT NULL,
    dept_name       TEXT,
    mode            TEXT NOT NULL DEFAULT 'manual', -- manual / carousel_mt
    mt_filter_months REAL,                          -- фільтр МТ (2 / 3 / 5 / 6+ міс.)
    status          TEXT NOT NULL DEFAULT 'active', -- active / saved / cancelled / archived
    created_at      TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    saved_at        TEXT,
    updated_at      TEXT,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_user_lists_user ON user_lists(user_id);
CREATE INDEX IF NOT EXISTS idx_user_lists_status ON user_lists(status);

----------------------------------------------------------------------
-- Рядки списків (list_items)
-- Тут фіксуємо кількість, лишки, статуси для каруселі
----------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS list_items (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    list_id             INTEGER NOT NULL,
    item_id             INTEGER NOT NULL,

    -- знімок даних товару на момент додавання до списку
    sku_snapshot        TEXT NOT NULL,
    name_snapshot       TEXT NOT NULL,
    dept_snapshot       TEXT,
    price_snapshot      REAL,
    mt_months_snapshot  REAL,

    qty                 REAL NOT NULL DEFAULT 0,    -- основна кількість
    surplus_qty         REAL NOT NULL DEFAULT 0,    -- лишки (понад доступний залишок)
    status              TEXT NOT NULL DEFAULT 'new',-- new / done / skipped / skipped_final

    has_photo           INTEGER NOT NULL DEFAULT 0, -- 1 якщо є хоч одне фото
    has_comment         INTEGER NOT NULL DEFAULT 0, -- 1 якщо є хоч один коментар

    created_at          TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          TEXT,

    FOREIGN KEY (list_id) REFERENCES user_lists(id) ON DELETE CASCADE,
    FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_list_items_list ON list_items(list_id);
CREATE INDEX IF NOT EXISTS idx_list_items_item ON list_items(item_id);
CREATE INDEX IF NOT EXISTS idx_list_items_status ON list_items(status);

----------------------------------------------------------------------
-- Фото товарів (item_photos)
----------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS item_photos (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id         INTEGER NOT NULL,
    file_id         TEXT NOT NULL,                  -- Telegram file_id
    status          TEXT NOT NULL DEFAULT 'pending',-- pending / approved / rejected
    added_by        INTEGER,                        -- users.id
    added_at        TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    moderated_at    TEXT,

    FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE CASCADE,
    FOREIGN KEY (added_by) REFERENCES users(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_item_photos_item ON item_photos(item_id);
CREATE INDEX IF NOT EXISTS idx_item_photos_status ON item_photos(status);

----------------------------------------------------------------------
-- Коментарі до товарів (item_comments)
----------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS item_comments (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id         INTEGER NOT NULL,
    user_id         INTEGER,
    text            TEXT NOT NULL,                  -- будемо обмежувати до 100 символів на рівні коду
    active          INTEGER NOT NULL DEFAULT 1,     -- 1 = показувати, 0 = прихований/архів
    created_at      TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_item_comments_item ON item_comments(item_id);
CREATE INDEX IF NOT EXISTS idx_item_comments_active ON item_comments(active);

----------------------------------------------------------------------
-- Імпорти (sessions) + логи імпорту
----------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS imports (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at      TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at     TEXT,
    run_type        TEXT NOT NULL DEFAULT 'apply',  -- apply / dry_run
    started_by      INTEGER,                        -- users.id
    source_file_name TEXT,
    source_file_hash TEXT,                          -- для ідентифікації файлу
    items_added     INTEGER NOT NULL DEFAULT 0,
    items_updated   INTEGER NOT NULL DEFAULT 0,
    items_deactivated INTEGER NOT NULL DEFAULT 0,
    error_count     INTEGER NOT NULL DEFAULT 0,

    FOREIGN KEY (started_by) REFERENCES users(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_imports_started_at ON imports(started_at);

CREATE TABLE IF NOT EXISTS import_logs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    import_id       INTEGER NOT NULL,
    row_number      INTEGER,                        -- номер рядка у файлі
    sku_raw         TEXT,
    message         TEXT NOT NULL,                  -- опис проблеми / попередження
    created_at      TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (import_id) REFERENCES imports(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_import_logs_import ON import_logs(import_id);

----------------------------------------------------------------------
-- Профілі імпорту (мапінг колонок)
----------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS import_profiles (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,                  -- назва профілю (b.xlsx стандарт, LibreOffice тощо)
    description     TEXT,
    file_mask       TEXT,                           -- опційно: шаблон назви файлу
    created_at      TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TEXT
);

CREATE TABLE IF NOT EXISTS import_columns (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id      INTEGER NOT NULL,
    column_name_raw TEXT NOT NULL,                  -- як колонка називається у файлі
    logical_field   TEXT NOT NULL,                  -- sku / dept_code / name / qty / sum / mt_months / reserve / price / ...

    created_at      TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (profile_id) REFERENCES import_profiles(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_import_columns_profile ON import_columns(profile_id);
CREATE INDEX IF NOT EXISTS idx_import_columns_logical ON import_columns(logical_field);
----------------------------------------------------------------------