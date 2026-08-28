# Tech Preferences

| Category                      | Choice                | Notes                                                    |
| ----------------------------- | --------------------- | -------------------------------------------------------- |
| **Observability**             | Langfuse              | LLM tracing & analytics                                  |
| **Backend**                   | Django REST           | Fixed; `schwarz-research-intelligence` repo, same-origin |
| **Package Manager / Runtime** | Bun                   | Used instead of npm/pnpm                                 |
| **Cache / Rate Limiting**     | Upstash               | Serverless Redis                                         |
| **Auth**                      | Django SimpleJWT      | JWT pair in httpOnly cookies, refreshed in proxy.ts      |
| **Charts**                    | Recharts              | React charting library                                   |
| **Hosting**                   | STACKIT Cloud Foundry | Docker image, path-routed beside the backend             |
| **Fonts**                     | Self-hosted           | Switzer + IBM Plex Mono via next/font/local              |
