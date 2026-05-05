# ReelMind Phase 1 — Backlog

Deferred features and enhancements for future phases.

## Database & Security

### Advanced RLS Policies (Phase 2)
- Implement granular row-level access control beyond basic user isolation
- Support for future sharing features (user-to-user reel sharing)
- Category-level permissions if needed
- Consider: public library profiles, collaborative collections

**Current State:** Basic RLS only — users see/modify only their own data + service role bypass for backend processing.

## Features

### Public & Sharing (Phase 2+)
- Allow users to make categories/reels public
- Share reels with other users
- Collaborative collections
- Public profiles

**Current State:** Everything private by default. No sharing mechanism.

## Infrastructure

### Migrate Redis to Cloud Before Production Deployment
- Currently running Redis locally via Docker for development
- **Before final deployment**, must point to a managed cloud Redis instance
- Options to evaluate: Upstash Redis, Redis Cloud (Redis Labs), Railway Redis add-on, AWS ElastiCache
- Update `REDIS_URL` env var in production environment to cloud endpoint
- Ensure TLS/auth is configured for cloud Redis
- Verify Celery workers can connect to cloud Redis from production server

**Current State:** Docker Redis on localhost:6379 for development.

## IOS targeted app versions

### Current IOS app is build for 16+
- Make sure to check weather this means that users with older iphone versions wouldn't be able to use your app?



## Save Reels by Users

### Few decesions that needs to be re iterated
- We should save the reels that are in the uncategorised state by our llm/backend. This can be used for adding new default reels or to understand the parts of our LLM that still needs to get trained

## Share Extension UX

### Show error to user when no URL is found (Phase 2)
- Currently if the Share Extension receives something that isn't a valid Instagram reel URL (e.g. a photo, a story, a profile link), we silently do nothing
- User should see a clear error message: "This doesn't look like an Instagram reel. Only public reel links are supported."
- Helps user understand why nothing happened instead of thinking the app is broken

---

*Last updated: 2026-05-05*
