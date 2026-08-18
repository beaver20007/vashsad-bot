# ORCHESTRATOR — состояние проекта vashsad-bot

Единый файл состояния для Оркестратора. Обновлять после каждого значимого
действия. Формат дат: YYYY-MM-DD.

## Текущее состояние main
- main = `c753f2c212144ef64cbdd5bc5f47e54ef3a05fec` (merge PR #4:
  quick_profile ImportError + broadcast_personalized_seasonal SQL),
  синхронизирован с origin (`git rev-parse HEAD` == `git rev-parse
  origin/main` после `git merge --ff-only origin/main`).
- Обновлено: 2026-08-18, PR #4 смёржен по подтверждению владельца.
- Ветка `fix/t-quick-profile-broadcast-sql` и её worktree
  (`C:/Projects/_worktrees/vashsad-fix-quick-profile-broadcast-sql`) НЕ
  удалены (`gh pr merge --delete-branch=false`) — уборка отдельным
  решением, как заведено для прочих веток в этом репо.
- Railway CLI на этой машине настроен и подтверждён рабочим: `railway
  link -p vashsad` → сервис `vashsad-bot`, окружение `production`.
  `railway logs --since <N>h --lines <M>` и `railway run -- <cmd>`
  (подставляет prod env, включая DATABASE_URL, в дочерний процесс без
  вывода значения) — рабочий канал для live-recon и read-only проверок
  без доступа к панели Railway. Полезно для будущих сессий.
- ⚠️ Локальная ветка ранее разошлась с origin (см. запись 2026-08-11 в
  журнале, «git reset --mixed»): локальные коммиты `4fdbafc`/`241de35`
  (не запушенные) дублировали содержимое, которое отдельно попало в origin
  через PR #1/#2/#3 (веб-редактор GitHub, другие SHA). Локальная ветка
  синхронизирована через `git reset --mixed origin/main` — рабочее дерево
  не пострадало (проверено `git diff origin/main` — пусто для всех
  затронутых файлов до ресета).

## Активные ветки
- `feat/max-integration` (локально `6181400...` на момент проверки) — на СТОПе
  по решению владельца. Не трогать, не мержить, не запускать.
- `backup/home-copy-20260731` (`74c9c77`) — источник только что влитого
  fast-forward мержа в main. НЕ удалять — уборка веток отдельным решением.

## Очередь мержей
- Пусто. Последний мерж: t-vrc-merge (см. журнал ниже).

## Деплой-очередь / деплой-риски
- **ВНИМАНИЕ**: main теперь содержит `.github/workflows/deploy.yml`
  (триггер `push: branches: [main]`, job `deploy`: сборка+push Docker-образа
  в Docker Hub → SSH-деплой на VPS через `appleboy/ssh-action`).
- На момент мержа (2026-08-04) в репозитории `beaver20007/vashsad-bot`
  **не настроено ни одного secret** (`gh secret list` — пусто, exit 0;
  `gh api .../actions/workflows` — было `total_count:0` до мержа).
  Значит после push job `deploy` упадёт на шаге логина в Docker Hub —
  реального прод-деплоя не произошло.
- ⚠️ Если владелец добавит секреты (`DOCKER_USERNAME`, `DOCKER_PASSWORD`,
  `VPS_HOST`, `VPS_USER`, `VPS_KEY`) — СЛЕДУЮЩИЙ push в main запустит
  реальный деплой на VPS. Это RED-класс задачи — не headless, требует
  подтверждения владельца непосредственно перед моментом появления секретов
  / следующего push.
- docker-compose.yml, nginx.conf, Dockerfile, scripts/deploy.sh,
  scripts/rollback.sh, scripts/pre_deploy_check.py — влиты, но НЕ запускались
  и не тестировались (вне рамок задачи t-vrc-merge).

## Итерация F1.2 — бот как точка входа в Mini App (recon, t-f12-recon)

### Карта `/order` и кнопок «заказать» (текущее состояние, до правок)
- Точки входа: `/order` (Command), `menu:order` (главное меню, handlers/start.py),
  `order:start` / `order:project` (несколько мест в keyboards.py и handlers/start.py,
  включая портфолио-экран). Все ведут в `handlers/order.py`.
- Две независимые FSM-ветки, **обе** внутри `handlers/order.py`:
  - Ветка «стартовая услуга» (`order:start` → выбор услуги → `confirm:<key>`):
    `OrderForm.contact_phone → contact_extra(email) → contact_location` —
    3 текстовых/интерактивных шага.
  - Ветка «индивидуальный проект» (`order:project`):
    `OrderForm.brief_area → brief_existing → brief_style → brief_wishes →
    brief_phone → brief_extra(email) → brief_location` — 7 шагов
    (4 брифа + телефон + email + геолокация). Задание описывало это как
    «пятишаговая анкета» — фактически шагов больше и веток две; для
    t-f12-entry ориентироваться на код, не на число в задании.
  - Стиль сада в текстовой ветке выбирается из фиксированного списка
    (`STYLE_KB_TEXT`, callback `style:<code>`) — это НЕ выбор картинками;
    выбор стилей картинками уже реализован в Mini App профиле (по брифу).
- Обе ветки заканчиваются в `_finish_contact` / `_finish_brief`:
  `save_order()` в БД → `insert_analytics_event()` → **синхронно тут же**
  `asyncio.gather(notify_all(...), notify_email_new_*(...), notify_sms_new_*(...))`.

### Уведомления дизайнеру — где живут (важно для блокера)
- `notify_all()` (Telegram), `notify_email_new_order/project` (Resend),
  `notify_sms_new_order/project` (smsc.ru) вызываются **только** изнутри
  `handlers/order.py`, синхронно в конце FSM. Код проверен построчно.
- `services/notifications.py` — только рассылки/напоминания (сезонные советы,
  task reminder), НЕ триггер уведомления о новой заявке.
- `services/webhook_server.py` — только эндпоинт `/webhook/yookassa`
  (оплата). Нет никакого HTTP-входа, которым Mini App могла бы дёрнуть бота
  для уведомления о новой заявке.
- **ФАКТ**: в репозитории `vashsad-full` нет ни одного пути, которым заявка,
  созданная через Mini App API (`/api/order` в vashsad-miniapp), могла бы
  вызвать `notify_all` / email / SMS дизайнеру. Если на стороне miniapp
  собственного уведомления нет — упразднение текстовой анкеты **оборвёт
  уведомления дизайнеру полностью**. Это и есть блокер, который бриф просил
  доложить до правок. Код `vashsad-miniapp` не читал (граница «одна сессия =
  один репозиторий», см. вне рамок брифа) — установить факт может только
  владелец или Оркестратор miniapp.

### Готовый паттерн для web_app-кнопки (уже есть в кодовой базе)
- `handlers/start.py`: `SCREEN_LINKS['screen_order'] = ('📋 Заказать услугу',
  'order')`, используется в deep-link обработке `/start screen_order` →
  `InlineKeyboardButton(web_app=WebAppInfo(url=f'{miniapp_url}?screen=order'))`.
  Экран `order` в Mini App, судя по всему, уже адресуется этим URL-параметром.
  Для t-f12-entry разумно переиспользовать ровно этот паттерн для `/order` и
  для всех кнопок `menu:order` / `order:start` / `order:project`, а не
  изобретать новый.
- `MINI_APP_URL` (config.py, default `https://vashsad.vercel.app`) vs
  `MINIAPP_URL` (start.py, тот же default) — два разных имени переменной
  окружения для одного и того же URL в разных модулях. Не блокер, но при
  правках в t-f12-entry стоит не плодить третье имя.

### Хостинг / деплой — НЕ установлено фактом, требует владельца
- README.md: «Деплой (бот) | Docker, Railway». docs/DEVELOPER.md и
  scripts/deploy.sh описывают ручной деплой на VPS (git pull + docker compose
  build/up, SSH). Ни railway.json, ни Procfile, ни nixpacks.toml в репозитории
  нет — Railway-путь ничем не подтверждён из кода.
- `.github/workflows/deploy.yml` (влит мержем 74c9c77) — единственный
  формальный CI/CD путь, но он **упал на обоих push** (`gh run list`:
  `30938785107`, `30939131327`, оба `failure`, job `deploy`, шаг Docker Hub
  login — секретов нет). То есть CI сейчас НЕ является реальным механизмом
  деплоя.
- Вывод: реальный способ обновления прод-бота на хостинге сейчас неизвестен
  из репозитория (ручной SSH? Railway из отдельного коннекта? что-то ещё?).
  Нужно спросить владельца напрямую — это отдельный факт, не выводимый из
  кода.
- Бот работает через long polling (`dp.start_polling`, bot.py:147), не через
  webhook — значит `getWebhookInfo` Telegram Bot API ничего не скажет о
  живости процесса. Единственный надёжный способ проверить, что бот жив
  после мержей 74c9c77/620219d — живой `/start` в реальном Telegram
  (инструмента Telegram у этой сессии нет, нужен владелец).

## Активные воркеры
- Нет (владелец ведёт проект самостоятельно с 2026-08-11, брифы через
  координатора — только по его запросу).

## Ждёт человека
1. ~~**Живая проверка бота**~~ — подтверждена владельцем 2026-08-11:
   `/start` без опроса, self_ping-тревоги прекратились. Закрыто.
2. ~~**Факт хостинга/деплоя**~~ — установлено 2026-08-18: **Railway**,
   проект `vashsad`, сервис `vashsad-bot`, окружение `production`. CLI
   подтверждён рабочим на этой машине. Закрыто.
3. **Блокер уведомлений miniapp** — статус не менялся с 2026-08-05,
   владелец ведёт эту часть самостоятельно вне координатора.
4. ~~**Решение по PR #4**~~ — владелец подтвердил 2026-08-18, смёржено
   (`gh pr merge 4 --merge`, merge commit `c753f2c`). Закрыто. Railway
   должен подхватить автодеплоем — живая проверка `/profile` и
   собственно `broadcast_personalized_seasonal` (следующий реальный
   прогон — 1 октября) отдельно не выполнялась этой сессией.
5. **НОВОЕ — вне рамок PR #4, отдельная находка**: `handlers/export.py:88`
   (`SELECT plant_name, latin_name, care_tips, added_at FROM user_plants`)
   — та же ошибка колонки, что была в `broadcast_personalized_seasonal`
   (`user_plants` не имеет `plant_name`, только `name`). Обнаружено при
   разведке 2026-08-18, НЕ входило в scope задачи (только quick_profile +
   broadcast), не тронуто. Сработает при экспорте пользователем PDF со
   своими растениями (`/export`) — нужен отдельный трек, когда владелец
   решит взяться.

## Карантин / инциденты
### 2026-08-05 — INC-1: бот не отвечает на /start (Railway)
- Обнаружено: живая проверка владельцем в рамках t-f12-recon — `/start`
  не даёт ответа вообще.
- Диагностика (владелец, доступа к Railway у сессии нет):
  1. Краш аутентификации в Railway — устранён обновлением пароля Railway.
  2. Следующий краш из логов: `asyncpg.exceptions.DuplicateColumnError:
     column "garden_area" of relation "users" already exists` в
     `_create_tables()` (services/database.py:212), рестарт-луп.
- Root cause (установлено чтением кода): `DO $$ ... RENAME COLUMN
  plot_size TO garden_area` (было — services/database.py:212-221)
  срабатывал по условию «`plot_size` существует», без проверки, что
  `garden_area` уже НЕ существует. Колонка `garden_area` реально добавлена
  миграцией 010 со стороны vashsad-miniapp 05.08 (общая БД, см. 74c9c77) —
  она нужна, трогать её нельзя. Если `plot_size` при этом тоже осталась
  (старый бот-путь) — RENAME бьётся о занятое имя цели → DuplicateColumnError
  → краш при каждом старте.
- Фикс: добавлено условие `AND NOT EXISTS garden_area` в rename-блок
  (корневая причина) + `try/except DuplicateColumnError/DuplicateTableError`
  вокруг всех DDL-вызовов в `_create_tables()` как страховка. Данные и
  колонка `plot_size` не тронуты — только защита инициализации от
  повторного запуска. См. коммит с этим изменением ниже в журнале.
- Статус: патч закоммичен и запушен в main; **живое подтверждение, что бот
  поднялся на Railway и отвечает на `/start`, ещё не получено** — открытый
  пункт «Ждёт человека» №4.

## Журнал решений
### 2026-08-04 — t-vrc-merge: fast-forward backup/home-copy-20260731 → main
- Задача: смержить `backup/home-copy-20260731` (v1.0.0-rc) в main как
  fast-forward целиком, включая `max-integration/*` (неактивные файлы).
- Проверка перед мержем: `git merge-base main origin/backup/home-copy-20260731`
  == `git rev-parse main` (`f221feb`) → чистый fast-forward подтверждён.
  Диффстат (3-точечный) — 79 файлов, +9997/-237.
- **Обнаружен риск**: новый `.github/workflows/deploy.yml` триггерится на
  push в main и делает реальный прод-деплой. Эскалировано владельцу
  ДО push (см. правило «ограничения выкатки» в исходном задании).
- Проверка секретов: `gh auth status` — залогинен, scopes `repo`+`workflow`;
  `gh secret list --repo beaver20007/vashsad-bot` — пусто, exit 0;
  `gh api repos/.../actions/workflows` — `total_count:0` (до мержа, т.к. в
  main workflow-файлов ещё не было). Вывод: секретов нет → реального
  деплоя не будет, job упадёт на логине в Docker Hub.
- Владелец подтвердил вариант «мержить и пушить как есть» (не отключать
  триггер, не откладывать).
- Выполнено: `git checkout main` → `git merge --ff-only
  origin/backup/home-copy-20260731` → Fast-forward, без merge-коммита →
  `git push origin main`.
- Приёмка фактом: `git rev-parse main` == хеш backup-ветки == `74c9c77...`;
  `git ls-remote origin refs/heads/main` вернул тот же хеш (сервер
  подтвердил); `git status --short` чист; `feat/max-integration` не тронута;
  `backup/home-copy-20260731` не удалена.
- Результат: main = `74c9c77376517bda184bee32dc1ac987ee4f45e4`, синхронизирован
  с origin. Задача t-vrc-merge закрыта.

### 2026-08-05 — t-f12-recon: карта /order, уведомления, хостинг (read-only)
- Задача: разведка перед заменой `/order` на кнопку открытия Mini App
  (итерация F1.2). Без правок в код.
- Построена карта FSM `/order` (две ветки, обе в handlers/order.py) —
  подробности в разделе «Итерация F1.2» выше.
- Обнаружен блокер: уведомления дизайнеру (Telegram+email+SMS) вызываются
  только из handlers/order.py; нет HTTP-входа для триггера из Mini App API.
  Не проверено, дублирует ли это сама miniapp — репозиторий vashsad-miniapp
  не читал по границе «одна сессия = один репозиторий». Эскалировано
  владельцу, ждёт ответа.
- Проверена живость CI-деплоя: `gh run list --repo beaver20007/vashsad-bot`
  — оба прогона `Deploy VashSad Bot` (push 74c9c77 и 620219d) завершились
  `failure` на шаге Docker Hub login (секретов нет, как и предсказывалось
  при мерже). Реальный механизм деплоя бота на прод не установлен фактом —
  README упоминает Railway, docs/DEVELOPER.md и scripts/deploy.sh описывают
  ручной VPS-путь; ни один способ не подтверждён из кода однозначно.
- Живая проверка `/start` в реальном Telegram НЕ выполнена этой сессией —
  инструмента Telegram нет. Вынесено в «Ждёт человека».
- Статус трека: recon завершён, отчёт передан владельцу. t-f12-entry не
  начат — заблокирован до ответа по пункту уведомлений (и желательно —
  по хостингу/деплою и живости бота).

### 2026-08-05 — INC-1-fix: идемпотентная инициализация БД (database.py)
- Триггер: живая проверка `/start` (см. INC-1 выше) — бот в рестарт-лупе
  на Railway, `DuplicateColumnError` на переименовании `plot_size` →
  `garden_area` в `_create_tables()`.
- Root cause подтверждён чтением кода (не догадка): rename-блок не проверял
  отсутствие целевой колонки `garden_area` перед `RENAME COLUMN`; после
  миграции 010 со стороны miniapp `garden_area` уже существует в `users`,
  из-за чего rename гарантированно падал при каждом старте.
- Изменения в `services/database.py` (`_create_tables()`):
  1. rename-DO-блок — добавлено `AND NOT EXISTS (... column_name='garden_area')`;
  2. весь исходный `CREATE TABLE ...` execute обёрнут в
     `try/except (DuplicateTableError, DuplicateColumnError)`;
  3. цикл `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` — каждый вызов
     обёрнут в `try/except DuplicateColumnError`;
  4. rename-блок — обёрнут в `try/except DuplicateColumnError` (доп. страховка
     сверх фикса из п.1).
- Данные не менялись, колонка `plot_size` не удалялась — только защита
  инициализации от race/повторного запуска. `python -m py_compile` —
  синтаксис ок.
- Владелец видел полный `git diff` перед решением, подтвердил пуш одним
  коммитом вместе с обновлением этого файла.
- Приёмка: см. факты коммита/push ниже; **живое подтверждение `/start`
  после деплоя на Railway ещё не получено** (Railway использует, по всей
  видимости, автодеплой из git — механизм не подтверждён владельцем, см.
  «Ждёт человека» №2).
- **⚠️ PUSH НЕ ПРОШЁЛ (закрыто обходным путём, см. ниже)**: коммит
  `4fdbafc` создан локально, но `git push origin main` дважды не прошёл —
  сначала `ssh: connect to host github.com port 22: Connection timed out`,
  затем известный баг Unix-подсистемы Git for Windows (`add_item ...
  errno 1`, задокументирован в машинных правилах). По регламенту — не
  повторять push пятикратно в одной сессии, чинится только новым
  окном/перезапуском. **main на GitHub всё ещё на `620219d`, фикса там
  нет.** Требуется новое окно/сессия для завершения push коммита
  `4fdbafc`.

### 2026-08-11 — INC-1-fix: push закрыт обходным путём (новая сессия)
- Новая сессия (после сбоя errno 1 из предыдущей) подтвердила: коммиты
  `4fdbafc`/`241de35` на месте локально, working tree чист, ветка на
  2 коммита впереди `origin/main`.
- SSH push из этой сессии тоже не прошёл — но по НОВОЙ причине, не errno 1:
  `Test-NetConnection github.com -Port 22` → `TcpTestSucceeded: False`,
  чистый TCP-таймаут. Обходной путь `ssh.github.com:443` (GitHub официально
  держит его для заблокированного 22) — тоже `Connection timed out`.
  `Test-NetConnection github.com -Port 443` (обычный HTTPS) → `True`. Вывод:
  сеть этой машины сейчас пропускает только HTTPS до github.com, SSH
  заблокирован полностью (не только 22). HTTPS-push при этом отдельно
  сломан на уровне git-клиента (см. машинные правила, errno 1 в Unix-
  подсистеме Git for Windows) — оба штатных пути push недоступны
  одновременно.
- По просьбе владельца: правки внесены НАПРЯМУЮ через веб-редактор GitHub
  (`beaver20007`, PersonalChrome), минуя git полностью. Функция
  `_create_tables()` в `services/database.py` заменена целиком (строки
  46–222 неотредактированной `main`) на версию, идентичную локальному
  `4fdbafc`/`241de35`. Технически: правка вставлена через синтетическое DOM
  `paste`-событие (не через посимвольный ввод) — прямой ввод текста
  проверен тестом и ломает отступы (редактор GitHub добавляет свой
  auto-indent поверх набираемого текста); системный буфер обмена был
  недоступен (`navigator.clipboard`/`execCommand` заблокированы политикой
  браузера) — обойдено конструированием `ClipboardEvent` с ручным
  `DataTransfer` и `dispatchEvent` напрямую на `.cm-content`. Диапазон
  выделения подтверждён визуально построчно (46–222 на неотредактированной
  базе `620219d`, короче патченной локальной версии на 13 строк из-за
  добавленных try/except).
- Прямой коммит в `main` через веб-редактор ОТКЛОНЁН GitHub: «There was an
  error committing your changes: File could not be edited» — похоже на
  branch protection (владелец подтвердил: трогать защиту не будем).
- Вместо этого: создана ветка `fix/idempotent-create-tables` с тем же
  коммитом (`0c8aebe`, verified), открыт PR #1
  (`github.com/beaver20007/vashsad-bot/pull/1`), смёржен без блокеров (0
  required checks, 0 required reviews, "No conflicts with base branch") —
  **владелец явно разрешил нажать Merge, если кнопка активна**.
- **Факт**: `main` = `fdd22bc` (merge commit PR #1, поверх `0c8aebe`, поверх
  `620219d`). Итоговое содержимое `_create_tables()` в `main` идентично
  локальным коммитам `4fdbafc`/`241de35` — но SHA другие (новый коммит
  через веб-редактор + merge-коммит, не оригинальные локальные коммиты).
  Ветка `fix/idempotent-create-tables` не удалена (не запрошено).
- Открытый пункт «Ждёт человека» №4 (живой `/start` после деплоя на
  Railway) остаётся: Railway должен подхватить `fdd22bc` автодеплоем — не
  подтверждено фактом из этой сессии, инструмента Telegram нет.

### 2026-08-11 — INC-1: продолжение, PR #2 и #3 (реконструкция из git log)
- ⚠️ **Оговорка**: эта запись восстановлена из `git log`/`git show` после
  того, как контекст сессии был сжат суммаризацией — живой памяти диалога
  об этих решениях у меня нет, только факты из истории git. Формулировки
  «диагностировано», «решено» ниже основаны на содержимом коммитов, не на
  воспоминании разговора с владельцем.
- После деплоя `fdd22bc` (PR #1) на Railway обнаружился следующий класс
  крашей: несколько хендлеров импортировали `_pool` из
  `services.database` **на уровне модуля** (`from services.database import
  _pool`) — на момент импорта `_pool` ещё `None` (устанавливается позже,
  внутри `init_db()`), значение навсегда остаётся `None` в этих модулях.
- PR #2 (`fix/pool-import-pattern`, коммиты `bd306eb…b49eb2b`, merge
  `74e066a`): в `feedback.py`, `booking.py`, `promo.py`, `moderation.py`,
  `admin.py`, `export.py` — замена `from services.database import _pool`
  на `from services.database import get_pool`, вызовы `_pool.acquire()` →
  `get_pool().acquire()`.
- Это, в свою очередь, вскрыло следующий баг: `get_pool()` — асинхронная
  функция, `get_pool().acquire()` без `await` перед `get_pool()` не работает
  (`.acquire()` вызывается на объекте corotine, а не на пуле).
- PR #3 (`fix/await-get-pool`, коммиты `443c419…5ad5f8e`, merge `3b891f4`):
  та же группа файлов — `get_pool().acquire()` → `pool = await
  get_pool(); pool.acquire()`. Отдельно исправлен пропущенный `_pool`
  в `cmd_whitelist` (`handlers/moderation.py`), не пойманный PR #2.
- Все коммиты PR #2/#3 автор `beaver20007` — судя по всему, тот же обход
  через веб-редактор GitHub (SSH/HTTPS push с этой машины были сломаны,
  см. запись выше), либо владелец правил напрямую. Локальная сессия
  этого не выполняла и не может подтвердить механику применения фактом
  собственных действий — только по содержимому коммитов.
- **Текущее состояние main**: `3b891f4` (после merge PR #3). Локальная
  ветка синхронизирована с этим состоянием через `git reset --mixed
  origin/main` (см. запись выше в этом разделе, «Текущее состояние main»).
  Проверено: рабочее дерево для всех 6 затронутых файлов было побайтово
  идентично `origin/main` ДО ресета (`git diff origin/main -- <файлы>` —
  пусто) — то есть либо эти же правки были сделаны локально независимо
  и совпали, либо working tree синхронизировался с origin каким-то путём
  в сжатой части разговора. Ресет не потерял никаких данных фактически
  (diff пуст) и не отменял ничего не запушенного в этих 6 файлах.
- Открытый вопрос: подтверждено ли живым `/start`, что бот на Railway
  наконец стабильно стартует после PR #1+#2+#3 — не установлено фактом
  этой сессией, нужен владелец.

### 2026-08-11 — новый баг: TypeError в quick_order (не связан с F1.2)
- По запросу владельца проверены два пункта read-only: (1) происхождение
  onboarding-квиза при `/start`, (2) новый краш из логов Railway
  (`TypeError: cmd_order() takes 1 positional argument but 2 were given`,
  `handlers/start.py:349`).
- Факт по онбордингу: `git log -S "maybe_start_onboarding" --
  handlers/start.py` → единственный коммит `b4db648` (20.06.2026). Не
  связано ни с F1.2, ни с инцидентом — код полутора-месячной давности,
  впервые реально исполняется на бою только сейчас (main не содержал этой
  функциональности до мержа `74c9c77` 04.08, а после мержа бот падал в
  рестарт-луп до сегодняшних фиксов).
- Факт по `quick_order`: `git log -S "def cmd_order"` → сигнатура
  `cmd_order(message: Message)` не менялась НИКОГДА, с самого первого
  коммита `346c39d` (13.05.2026). `git log -S "def quick_order"` →
  `quick_order(message, state)` (handlers/start.py:347) появилась в
  `b4db648` (20.06.2026) и с тех пор звала `cmd_order(message, state)` —
  на один аргумент больше, чем сигнатура принимает. Тоже родовой баг
  фиче-ветки от 20.06, не имеющий отношения к работе этой сессии над
  F1.2 (t-f12-entry ещё не начинался).
- Фикс: `handlers/start.py:349` — `await cmd_order(message, state)` →
  `await cmd_order(message)`. Единственная строка, `python -m py_compile`
  — синтаксис ок. Других вызовов `cmd_order(...)` в кодовой базе нет
  (проверено `Grep`).
- Статус: закоммичено вместе с этой записью, push — см. факты ниже.

### 2026-08-11 — F1.2-STOP: отключение onboarding-квиза, фикс self_ping и MINI_APP_URL
- Триггер: живая проверка владельцем — после ответа на регион бот сразу
  спрашивает «Площадь участка?» (многошаговая текстовая FSM-анкета). Прямое
  противоречие решению F1.2 и закону №1 Стратегии v2 («тыкает пальцем, не
  отвечает на вопросы»). Решение владельца: не чинить по полю — отключить
  целиком, профиль брать из Mini App через общую БД.
- Read-only разведка перед правкой: `Grep "onboarding"` по всему репо —
  единственный вызывающий `maybe_start_onboarding` это `cmd_start`
  (handlers/start.py:177-178); `onboarding_router` в bot.py подключает
  только сами FSM-хендлеры квиза, больше никто их не запускает.
  `tests/test_e2e_flow.py:140` патчит `handlers.start.maybe_start_onboarding`
  (несуществующий атрибут модуля — импорт был локальный внутри функции) —
  этот тест уже был хрупким независимо от моей правки, не трогал (вне
  задачи).
- Правка: закомментированы 3 строки вызова в `cmd_start`
  (handlers/start.py:176-178) с пояснением. `handlers/onboarding.py` и его
  роутер в bot.py НЕ удалены — оставлены мёртвым, но безопасным кодом.
  `/start` теперь сразу идёт к приветствию + кнопке `mini_app_keyboard()`
  для всех пользователей, новых и старых.
- **self_ping_check** (services/scheduler.py:363-380): root cause
  подтверждён фактом — `curl http://localhost:3000/api/health` с этой
  машины → `exit 7` (connection refused); бот на Railway, miniapp на
  Vercel, разные хосты, на `localhost:3000` в контейнере бота никогда
  ничего не слушало. Любое исключение в `self_ping_check` → alert
  «Miniapp не отвечает!», значит алерт гарантирован на каждом из 10-минутных
  прогонов независимо от реального состояния miniapp. Проверен реальный
  эндпоинт: `curl https://vashsad-miniapp-pi.vercel.app/api/health` → HTTP
  200, `{"status":"ok","checks":{"database":{"ok":true},"claude_api":
  {"ok":true},"redis":{"ok":true},"yookassa":{"ok":false}}}` — miniapp
  реально жив. Фикс: URL заменён на `f'{MINI_APP_URL}/api/health'`,
  `MINI_APP_URL` импортирован из `config` (не был импортирован раньше).
- **Дефолтный домен MINI_APP_URL был неверным**: `config.py` и
  `services/notifications.py` использовали дефолт
  `https://vashsad.vercel.app` — `curl` этого домена → HTTP 404, не тот
  адрес. Заменено на реально живой `https://vashsad-miniapp-pi.vercel.app`
  в обоих местах (сработает, только если env-переменная `MINI_APP_URL` в
  Railway не задана явно — если задана, дефолт не используется).
- **Обнаружен молчаливый читатель того же неверного дефолта под другим
  именем переменной**: `handlers/start.py:154` (deep-link `?screen=...`)
  делал собственный `os.getenv('MINIAPP_URL', 'https://vashsad.vercel.app')`
  — другое имя env-переменной (`MINIAPP_URL` без подчёркивания вместо
  `MINI_APP_URL`), тот же неверный дефолт. Если в Railway задан только
  `MINI_APP_URL` (как везде в остальном коде), эта конкретная кнопка молча
  падала бы на 404-домен. Исправлено: строка теперь использует уже
  импортированную константу `MINI_APP_URL` из config.py вместо отдельного
  чтения переменной окружения — убирает и дублирование, и рассинхрон имён.
- `scripts/pre_deploy_check.py:27` сверен под то же единое имя
  (`MINIAPP_URL` → `MINI_APP_URL`), иначе deploy-чеклист проверял бы
  наличие переменной, которую код больше нигде не читает.
- `python -m py_compile` — синтаксис ок для всех 5 изменённых файлов
  (handlers/start.py, services/scheduler.py, config.py,
  services/notifications.py, scripts/pre_deploy_check.py).
- Владелец видел полный `git diff` перед решением, подтвердил один коммит.
- Приёмка: см. факты коммита/push ниже.

### 2026-08-18 — bot-live-recon (read-only): статус бота через 6 дней самостоятельной работы владельца
- Задача владельца (без брифа координатора, напрямую): снять живой статус
  бота — логи Railway 48-72ч, self_ping, очередь модерации, масштаб
  активности. Read-only, без правок.
- Настроен и подтверждён Railway CLI (`railway link -p vashsad`) — первое
  использование в этом проекте, задокументировано выше в «Текущее
  состояние main».
- Логи (`railway logs --since 72h --lines 5000`, реально покрыло
  2026-08-15 04:46 → 2026-08-18 04:36): процесс стабилен, без
  restart-loop. Три находки:
  1. `ImportError` на кнопке «Профиль» (`handlers/start.py:365`,
     `quick_profile`) — импортирует `cmd_profile` из `handlers.price`,
     функция реально в `handlers/start.py:277`. Тот же класс бага, что
     `quick_order` (чинили 11.08), соседнюю кнопку тогда не проверили.
     2026-08-17 19:49:11, один случай.
  2. `broadcast_personalized_seasonal` (services/scheduler.py) упал
     2026-08-15 07:00:01 — `UndefinedTableError`, `FROM users` без
     алиаса `u`, на который ссылается остальной запрос. Cron на 4 даты
     в году, следующая — 1 октября.
  3. Внешний блип Telegram (`Bad Gateway`/timeout на `getUpdates`,
     2026-08-16 01:16-01:19) — самовосстановился штатным ретраем
     aiogram за ~3 минуты, не наш баг, не трогали.
- self_ping: 334 запуска/342 завершения (расхождение — краевой эффект
  окна логов), 0 алертов «Miniapp не отвечает» — фикс от 11.08 держится.
- Очередь модерации: архитектурно нет отдельной таблицы, только флаги
  `is_banned`/`is_whitelist`. Проверено запросом к prod БД (read-only,
  через `railway run` с production DATABASE_URL, значение никуда не
  выводилось): `banned_users=0`, `whitelisted_users=0`.
- Масштаб активности (read-only агрегаты той же БД): `total_users=6`,
  `users_created_7d=4`, `users_created_48h=0` (последний — 14.08),
  `total_orders=2`, `orders_created_7d/48h=0` (последний — 05.08).
  Трафик реально маленький, не признак проблемы.
- Статус: отчёт передан владельцу тем же сообщением, без PR (read-only
  трек). По находкам 1 и 2 владелец сразу поставил задачу fix — см.
  следующую запись.

### 2026-08-18 — PR #4: фикс quick_profile ImportError + SQL-баг broadcast
- Трек `fix-quick-profile-and-broadcast`, ветка/worktree
  `fix/t-quick-profile-broadcast-sql`
  (`C:/Projects/_worktrees/vashsad-fix-quick-profile-broadcast-sql`).
  Первым коммитом заведён `docs/AGENTS.md` (не существовал) — конвенция
  «трек = worktree = ветка = строка в таблице».
- `quick_profile`: убран неверный импорт `from handlers.price import
  cmd_profile` — `cmd_profile` уже в области видимости модуля
  (`handlers/start.py:277`), отдельный импорт не нужен.
- `broadcast_personalized_seasonal`: добавлен алиас `u` к `FROM users`
  (root cause прод-краша 15.08). При живой проверке всплыл ВТОРОЙ,
  ещё не сработавший баг в том же запросе: подзапрос обращался к
  `plant_name`, а в `user_plants` колонка называется `name` — с одним
  только алиасом запрос всё равно упал бы 1 октября. Исправлено и то,
  и другое.
- Живая проверка (production DB через `railway run`, без изменения
  данных, message.answer замокан — реальным пользователям ничего не
  отправлялось):
  - `quick_profile` «до»: `git stash` фикса → воспроизведён тот же
    `ImportError`, что в логах прода 17.08. «После»: `git stash pop` →
    `quick_profile()` отработал без исключения, `message.answer` вызван
    1 раз с корректным текстом профиля реального пользователя (имя,
    статус, дата регистрации, лимиты).
  - `broadcast` SQL прогнан в трёх состояниях против prod БД:
    оригинал → `UndefinedTableError` (совпадает с прод-крашем);
    только-алиас → `UndefinedColumnError` (доказывает второй баг);
    оба фикса → `OK, 6 rows returned`, включая пользователя с реальными
    данными по растениям.
- `python -m py_compile` — синтаксис ок для обоих файлов.
- Побочная находка вне scope: `handlers/export.py:88` — та же ошибка
  колонки (`plant_name` вместо `name`) в другом месте, не трогали,
  вынесено в «Ждёт человека» отдельным пунктом.
- `git show --stat HEAD` — только 3 файла (handlers/start.py,
  services/scheduler.py, docs/AGENTS.md), ничего лишнего.
- Push ветки: `git push -u origin fix/t-quick-profile-broadcast-sql` —
  прошёл с первого раза. PR создан: `gh pr create` →
  github.com/beaver20007/vashsad-bot/pull/4, `mergeable: MERGEABLE`.
- **НЕ смёржено** — RED-класс (прод), ждёт решения владельца.

### 2026-08-18 — PR #4 смёржен
- Владелец подтвердил мерж прямым текстом («мержи PR #4 в main»).
- Проверка перед мержем: `gh pr view 4` — `mergeStateStatus: CLEAN`,
  `mergeable: MERGEABLE`. `git merge-base origin/main
  origin/fix/t-quick-profile-broadcast-sql` = `330a34b` (точка ветвления
  ветки); `origin/main` с тех пор ушёл вперёd на docs-коммит `e668057`
  (не пересекается по файлам). Трёхточечный `git diff --stat
  origin/main...origin/fix/t-quick-profile-broadcast-sql` — те же 3
  файла, что в PR, без неожиданных довесков.
- Выполнено: `gh pr merge 4 --merge --delete-branch=false` → merge commit
  `c753f2c212144ef64cbdd5bc5f47e54ef3a05fec`. Ветка НЕ удалена.
- Приёмка фактом: `git fetch` → `git merge --ff-only origin/main` в
  локальном `main` — fast-forward `e668057..c753f2c` без конфликтов;
  `git rev-parse HEAD` == `git rev-parse origin/main` ==
  `c753f2c...`; `git status --short` чист.
- Открыто: живое подтверждение `/profile` без ошибки и фактического
  прогона `broadcast_personalized_seasonal` на бою этой сессией не
  делалось (broadcast реально сработает только 1 октября; `/profile`
  можно проверить в реальном Telegram в любой момент — не выполнено,
  т.к. владелец не просил).
