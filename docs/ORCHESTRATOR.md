# ORCHESTRATOR — состояние проекта vashsad-bot

Единый файл состояния для Оркестратора. Обновлять после каждого значимого
действия. Формат дат: YYYY-MM-DD.

## Текущее состояние main
- main = `74c9c77376517bda184bee32dc1ac987ee4f45e4` (v1.0.0-rc), синхронизирован
  с origin (проверено `git ls-remote`).
- Обновлено: 2026-08-04, трек t-vrc-merge.

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

## Активные воркеры
- Нет.

## Ждёт человека
- Нет открытых пунктов на момент записи.

## Карантин / инциденты
- Нет.

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
