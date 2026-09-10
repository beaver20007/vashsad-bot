-- ВашСад · content_strings_up.sql (ДИЗАЙН, не применена — см. README.md рядом)
--
-- Схема сверена 09.09.2026 с параллельным предложением vashsad-miniapp
-- (PR #120, db/migrations/020_content_strings_{up,down}.sql) — тот же
-- ночной брифинг спроектировал одну и ту же таблицу с двух сторон.
-- Таблица/колонки здесь — БУКВАЛЬНАЯ копия схемы miniapp (namespace/key/
-- jsonb value), не отдельный вариант: одно имя, одна форма, как просил
-- владелец, вместо двух параллельных content_texts/content_strings.
--
-- Изменения относительно первой версии этого файла (content_texts,
-- flat key VARCHAR + body TEXT):
--   1. Имя таблицы: content_texts -> content_strings (принято имя miniapp).
--   2. PK: было key VARCHAR(96) один столбец; стало (namespace, key) —
--      namespace группирует вид контента (designer_bio, order_status),
--      key — конкретный элемент внутри вида. Позволяет добавлять новые
--      виды контента без новых миграций.
--   3. Тип значения: было body TEXT (одна строка); стало value JSONB —
--      один key может нести несколько полей сразу (пример ниже:
--      designer_bio.default несёт name+role+education+status одной
--      строкой, а не четырьмя отдельными key).
--   4. updated_by (было в content_texts) — ОТБРОШЕН, в схеме miniapp
--      его нет. Если понадобится аудит "кто правил" — можно добавить
--      как поле внутри JSONB value без новой миграции; отдельной
--      колонкой не заводим, чтобы не расходиться со стороной miniapp.
--
-- НЕ УЛАЖЕНО (называю явно, не молчу): большинство значений namespace
-- 'order_status' — см. блок ниже. Единственное исключение: 'done'
-- (решение владельца от 10.09.2026, см. INSERT ниже).

BEGIN;

CREATE TABLE content_strings (
  namespace   VARCHAR(64) NOT NULL,
  key         VARCHAR(64) NOT NULL,
  value       JSONB NOT NULL,
  updated_at  TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW(),
  PRIMARY KEY (namespace, key)
);

COMMENT ON TABLE content_strings IS 'Общий контент-слой между vashsad-miniapp и vashsad-bot (схема сверена 09.09.2026 с miniapp PR #120). namespace группирует вид контента (напр. designer_bio, order_status), key — конкретный элемент внутри вида, value — произвольный jsonb под конкретный вид.';

-- designer_bio.default — ОКОНЧАТЕЛЬНОЕ решение владельца (09.09.2026, в
-- ответ на этот же ночной брифинг): понижение с "дипломированный
-- ландшафтный дизайнер" (setup_bot.py/pdf_generator.py/export.py) до
-- честной формулировки. Значения идентичны черновику из miniapp PR#120
-- (там помечены как черновик до приёмки) — владелец их же и утвердил
-- как финальные, поэтому здесь они уже не черновик.
INSERT INTO content_strings (namespace, key, value) VALUES
  ('designer_bio', 'default', '{
    "name": "Аня",
    "role": "ландшафтный дизайнер",
    "education": "Garden Group, ТГУ — программы переподготовки «Ландшафтный дизайнер»",
    "status": "Беру первые проекты"
  }'::jsonb)
ON CONFLICT (namespace, key) DO UPDATE SET
  value = EXCLUDED.value, updated_at = NOW();

-- order_status.done — РЕШЕНИЕ ВЛАДЕЛЬЦА (10.09.2026): единая
-- формулировка на всех поверхностях (бот + miniapp) для этого статуса.
-- Заменяет и текущий текст бота ("Свяжитесь с дизайнером для получения
-- результатов.", handlers/admin_bot_handlers.py::ORDER_STATUS_INFO —
-- поправлено тем же решением в PR#29), и черновик miniapp PR#120
-- ("Ваш проект готов. Пожалуйста, оставьте отзыв в приложении — это
-- важно для нас! 🌿"). Это единственный статус, где текст решён —
-- остальные ниже остаются нерешённым расхождением.
INSERT INTO content_strings (namespace, key, value) VALUES
  ('order_status', 'done', '{
    "admin_label": "✅ Выполнена",
    "notify_text": "✅ Ваша заявка <b>выполнена</b>! Пожалуйста, оставьте отзыв в приложении."
  }'::jsonb)
ON CONFLICT (namespace, key) DO UPDATE SET
  value = EXCLUDED.value, updated_at = NOW();

-- order_status.{new,in_progress,review,canceled} — СОЗНАТЕЛЬНО НЕ
-- ЗАСЕЯНО здесь. TODO: не финально, ждёт отдельного решения владельца
-- по каждому статусу (явно отложено 10.09.2026, "не блокирует
-- остальное").
--
-- Причина: бот и miniapp расходятся не только именем таблицы (уже
-- сведено выше), но и содержанием этого namespace для этих статусов.
-- Бот несёт свою продовую формулировку (ORDER_STATUS_INFO в
-- handlers/admin_bot_handlers.py: label + client_text для каждого
-- статуса — тексты, которые реально уходят клиенту сегодня). miniapp
-- PR#120 сеет ДРУГОЙ черновой текст для тех же статусов
-- (client_label/notify_text в db/migrations/020_content_strings_up.sql)
-- — например для "review" бот шлёт "Ваша заявка на согласовании.
-- Ожидайте обратной связи.", а черновик miniapp — "Проект на
-- согласовании. Мы подготовили материалы для вашего проекта.". Разные
-- тексты для одного и того же (namespace, key).
--
-- Обе миграции целятся в один и тот же PRIMARY KEY (namespace, key) на
-- одной физической БД. Если засеять здесь ещё раз те же ключи —
-- порядок применения (эта миграция раньше/позже 020 в miniapp) решит,
-- чей текст останется, тихо и без сигнала кому-либо. Это решение не
-- моё и не Оркестратора miniapp — окончательную формулировку по каждому
-- статусу должен утвердить владелец, как он уже сделал для designer_bio
-- и order_status.done выше. До этого явного решения эти ключи здесь не
-- трогаю, чтобы не создать скрытую гонку миграций.
--
-- Когда решение будет: добавить сюда INSERT с ON CONFLICT DO UPDATE
-- (как designer_bio/order_status.done выше) и синхронно поправить/убрать
-- конфликтующие строки в miniapp's 020 — координировать оба
-- репозитория одним PR-окном.

COMMIT;
