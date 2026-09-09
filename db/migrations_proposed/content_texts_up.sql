-- ВашСад · content_texts_up.sql (ДИЗАЙН, не применена — см. README.md рядом)
--
-- Общий текстовый слой для строк, которые сейчас продублированы между
-- vashsad-full (бот) и vashsad-miniapp: лейблы/тексты статуса заявки
-- (было по 2 копии в handlers/admin_bot_handlers.py + 1 в miniapp's
-- orders/[id]/status/route.ts) и позиционирование дизайнера ("дипломированный
-- ландшафтный дизайнер" в setup_bot.py/pdf_generator.py/export.py против
-- честной формулировки в miniapp's ChatScreen.tsx).
--
-- Простой key-value, а не отдельные таблицы на статус/дизайнера: обе строки
-- содержания -- по сути "именованный кусок текста", разной структуры не
-- требуют. Если позже понадобится локализация -- добавить колонку locale
-- и включить её в PRIMARY KEY, не меняя форму строк.

BEGIN;

CREATE TABLE IF NOT EXISTS content_texts (
    key         VARCHAR(96) PRIMARY KEY,
    body        TEXT NOT NULL,
    updated_at  TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_by  VARCHAR(64)  -- кто последний правил (для будущей админки Ани); NULL = сидирование этой миграцией
);

-- Статусы заявки: лейбл (для /orders и карточки заявки) + client_text
-- (пуш клиенту при смене статуса). "new" не шлёт пуш -- это исходный статус,
-- клиент и так знает, что заявку создал.
INSERT INTO content_texts (key, body) VALUES
    ('order_status.new.label',            '🆕 Новая'),
    ('order_status.in_progress.label',     '🔄 В работе'),
    ('order_status.in_progress.client_text', '🔄 Ваша заявка <b>принята в работу</b>! Дизайнер уже занимается вашим проектом.'),
    ('order_status.review.label',          '👀 На согласовании'),
    ('order_status.review.client_text',    '👀 Ваша заявка <b>на согласовании</b>. Ожидайте обратной связи.'),
    ('order_status.done.label',            '✅ Выполнена'),
    ('order_status.done.client_text',      '✅ Ваша заявка <b>выполнена</b>! Свяжитесь с дизайнером для получения результатов.'),
    ('order_status.canceled.label',        '❌ Отменена'),
    ('order_status.canceled.client_text',  '❌ Ваша заявка <b>отменена</b>. Если есть вопросы — напишите нам.')
ON CONFLICT (key) DO UPDATE SET
    body = EXCLUDED.body, updated_at = NOW();

-- Позиционирование дизайнера -- буквальная копия ТЕКУЩЕГО текста бота.
-- ТРЕБУЕТ ВЫЧИТКИ Аней перед реальным накатом (см. README.md) -- эта
-- миграция не решает спор "дипломированный" vs честная формулировка,
-- только даёт одно место, которое можно поправить одной строкой вместо
-- четырёх файлов.
INSERT INTO content_texts (key, body) VALUES
    ('designer.qualification_line', 'Дипломированный ландшафтный дизайнер')
ON CONFLICT (key) DO UPDATE SET
    body = EXCLUDED.body, updated_at = NOW();

COMMIT;
