# AGENTS — треки воркеров (vashsad-bot)

Каждый трек = отдельный git worktree = отдельная ветка = одна строка в
этой таблице. Мержит и деплоит только Оркестратор, после подтверждения
владельца (RED-класс для прода).

## Активные треки

Ночь 2026-09-09 (бот→miniapp-thin-layer, 7 треков брифа) — все PR
подготовлены, worktree ниже. Ничего не смёржено, миграция (#31) не
применена — ждут владельца. Полная сводка: docs/ORCHESTRATOR.md,
запись «2026-09-09».

| Трек | Ветка | PR | Статус |
|---|---|---|---|
| remove-dead-code-and-hardcodes | `chore/t-remove-dead-code-and-hardcodes` | #29 | открыт, не смёржен — ждёт владельца |
| portfolio-designer2-notify-gate | `fix/t-portfolio-designer2-notify-gate` | #30 | открыт, не смёржен — ждёт владельца |
| design-content-texts-migration | `feat/t-design-content-texts-migration` | #31 | открыт, не смёржен — миграция НЕ применена (дизайн) |
| content-texts-reads | `feat/t-content-texts-reads` | #32 | открыт, не смёржен — код неактивен до наката #31 |
| fix-claude-md-redis-var | `docs/t-fix-claude-md-redis-var` | #33 | открыт, не смёржен — ждёт владельца |
| (рекомендация, не трек) | vashsad-miniapp/bot/ — удалить | — | не PR, текст владельцу — чужой репозиторий |

## Архив (смёржено, ветка/worktree удалены)

| Трек | Ветка (была) | PR | Дата мержа |
|---|---|---|---|
| ruff-line-length-120 | `chore/t-ruff-line-length-120` | #28, `bd0c27b` | 2026-09-07 |
| ruff-wave3-fstring-cleanup | `chore/t-ruff-wave3-fstring-cleanup` | #27, `2d3f9bb` | 2026-09-07 |
| ruff-wave2-py312-syntax | `chore/t-ruff-wave2-py312-syntax` | #26, `7990212` | 2026-09-07 |
| ruff-wave1-import-hygiene | `chore/t-ruff-wave1-import-hygiene` | #25, `00b65e5` | 2026-09-07 |
| welcome-b-informal-text | `fix/t-welcome-b-informal-text` | #24, `fe92022` | 2026-08-31 |
| remove-docker-hub-deploy-job | `chore/t-remove-docker-hub-deploy-job` | #23, `c2c2d54` | 2026-08-26 |
| ruff-setup | `chore/t-ruff-setup` | #22, `04fa35b` | 2026-08-26 |
| sentry-scrub-locals | `fix/t-sentry-scrub-locals` | #21, `2d6f1cd` | 2026-08-25 |
| bot-consent-booking | `fix/t-bot-consent-booking` | #20, `02bddd1` | 2026-08-25 |
| bot-consent-start | `fix/t-bot-consent-start` | #19, `b540951` | 2026-08-25 |
| welcome-ab-test-real | `feat/t-welcome-ab-test-real` | #18, `1e7f9a0` | 2026-08-25 |
| fix-welcome-text-update | `fix/t-welcome-text-update` | #17, `581eed1` | 2026-08-24 |
| add-pr-ci-workflow | `fix/t-bot-pr-ci` | #16, `0aa6bab` | 2026-08-21 |
| cleanup-admin-dupes | `chore/t-cleanup-admin-dupes` | #15, `3468f80` | 2026-08-21 |
| fix-broadcast-region-segments | `fix/t-broadcast-region-segments` | #14, `2c02c18` | 2026-08-21 |
| admin-bot-layer-a-workflow | `feat/t-adminbot-layer-a` | #13, `cb74a3a` | 2026-08-21 |
| scaffold-admin-bot | `feat/t-scaffold-admin-bot` | #12, `871f38e` | 2026-08-21 |
| fix-quick-profile-and-broadcast | `fix/t-quick-profile-broadcast-sql` | #4, `c753f2c` | 2026-08-18 |
| redirect-order-to-miniapp | `fix/t-f32-order-redirect-miniapp` | #5, `5492d59` | 2026-08-18 |
| remove-bot-price-sources | `fix/t-f33-remove-bot-prices` | #6, `a7f0828` | 2026-08-18 |
| remove-chat-faq-prices | `fix/t-f34-remove-chat-faq-prices` | #7, `a0bba97` | 2026-08-18 |
| cleanup-dead-order-code | `fix/t-cleanup-dead-order-code` | #8, `b5bee8d` | 2026-08-18 |
| fix-plan-full-name-bug | `fix/t-plan-full-name` | #9, `45c133e` | 2026-08-19 |
| fix-nurseries-full-name-bug | `fix/t-nurseries-full-name` | #10, `e61104f` | 2026-08-19 |
| fix-export-plant-name-bug | `fix/t-export-plant-name` | #11, `857844a` | 2026-08-20 |
| (допроектные, до конвенции треков) | `fix/idempotent-create-tables` | #1 | 2026-08-11 |
| (допроектные, до конвенции треков) | `fix/pool-import-pattern` | #2 | 2026-08-11 |
| (допроектные, до конвенции треков) | `fix/await-get-pool` | #3 | 2026-08-11 |

## Не тронуто чисткой (не смёржено или отдельное решение)

- `feat/max-integration` — на СТОПе по решению владельца, не смёржена в main
  (`git branch --no-merged main`). Не удалять, не мержить.
- `origin/rescue/pre-orchestrator-20260725` — не смёржена в main. Не трогать.
- `origin/backup/home-copy-20260731` — **удалена** 2026-08-26 после повторной
  проверки (`git merge-base` = tip ветки, 0 уникальных коммитов, тот же
  результат, что и в старой записи). См. docs/ORCHESTRATOR.md.
