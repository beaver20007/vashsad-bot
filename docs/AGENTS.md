# AGENTS — треки воркеров (vashsad-bot)

Каждый трек = отдельный git worktree = отдельная ветка = одна строка в
этой таблице. Мержит и деплоит только Оркестратор, после подтверждения
владельца (RED-класс для прода).

## Активные треки

| Трек | Ветка | Worktree | Статус | Дата |
|---|---|---|---|---|
| add-pr-ci-workflow | `fix/t-bot-pr-ci` | `C:/Projects/_worktrees/vashsad-add-pr-ci` | PR открыт, ждёт мержа владельцем | 2026-08-21 |

## Архив (смёржено, ветка/worktree удалены)

| Трек | Ветка (была) | PR | Дата мержа |
|---|---|---|---|
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
- `origin/backup/home-copy-20260731` — технически 0 уникальных коммитов
  относительно main (была источником fast-forward мержа 04.08), но её
  уборка отмечена в docs/ORCHESTRATOR.md как «отдельное решение» —
  сознательно не удалена в этом проходе, см. ORCHESTRATOR.md.
