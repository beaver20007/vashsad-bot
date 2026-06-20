# Changelog

## [1.0.0-rc] - 2026-06-20

### Bot Features Added
- AI chat with Claude Sonnet (conversation history, FAQ patterns)
- Photo diagnosis with Claude Vision
- Plant selection FSM (climate + conditions)
- Garden plan generation FSM (area/style/budget)
- Seasonal plan for the full year
- Booking system with reminders
- YooKassa payments (link + webhook)
- Telegram Stars payments (3 tiers)
- Referral program + promo codes
- Onboarding with region selection
- Admin panel: stats, broadcast, A/B testing
- Broadcast segments (7 types)
- Notifications: Telegram + Email + SMS
- Scheduler: seasonal broadcasts, newsletter
- Rate limiting middleware
- Channel subscription bonus
- Saved reply templates for designer

### Miniapp Features Added
- 22+ screens: plants, order, garden, diary, map, chat, profile, etc.
- Real-time designer chat (polling 5s)
- Push notifications (Web Push + VAPID)
- PWA: Service Worker, offline page, install prompt
- Infinite scroll for plant catalog
- Plant search with highlight
- Garden map with 4 marker types + zoom
- Before/After slider in Portfolio
- Weather widget with watering advice
- Quote of the day
- PDF plan export, CSV export
- Redis caching (plants + weather)
- Skeleton loading placeholders
- ErrorBoundary for all screens
- Bookmarks system
- Google Calendar ICS export

### Infrastructure
- PostgreSQL (Neon) via asyncpg
- Redis (Upstash) caching  
- Docker + docker-compose production
- GitHub Actions CI/CD
- Sentry error tracking
- Versioned DB migrations
- Pre-deploy check script
- Deploy + rollback scripts
- nginx config with SSL
- YooKassa webhook hardening
