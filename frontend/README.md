# 🖥️ Schwarz Research Intelligence - Frontend Web Application

> **Minimalist, High-Performance Web Application built with Next.js (Pages Router), TypeScript, and Tailwind CSS.**

---

## 🏛️ Directory Structure

The frontend application uses a clean, modular Pages Router architecture with 100% Tailwind CSS styling:

```
frontend/
├── Dockerfile                  # Node.js 22 LTS production container build
├── package.json                # Next.js 14, React 18, Tailwind CSS, Lucide icons
├── next.config.js              # Dynamic build IDs, security & anti-caching HTTP headers
├── tailwind.config.js          # Tailwind CSS design system tokens
├── postcss.config.js           # PostCSS configuration
├── tsconfig.json               # TypeScript configuration with @/* path aliases
├── styles/
│   └── globals.css             # Tailwind base, components, and utilities
├── pages/                      # Application routes and page views
│   ├── _app.tsx                # Global root layout, Head, AuthProvider & Navbar
│   ├── index.tsx               # Root route (LandingPage or DashboardPage)
│   ├── login/
│   │   ├── index.tsx           # /login route entrypoint
│   │   └── LoginPage.tsx       # Stealth authentication form
│   ├── dashboard/
│   │   ├── index.tsx           # /dashboard route entrypoint
│   │   ├── DashboardPage.tsx   # Authenticated SLR Workspaces dashboard
│   │   └── LandingPage.tsx     # Minimalist stealth landing hero
│   └── status/
│       ├── index.tsx           # /status route entrypoint
│       └── StatusPage.tsx      # Infrastructure & microservice health probes
├── components/                 # Reusable UI components
│   ├── Navbar.tsx              # Minimalist navigation header with profile & role badge
│   └── auth/
│       └── ProtectedRoute.tsx  # Route guard with session verification
└── lib/                        # Core application libraries
    ├── auth/                   # JWT session management
    │   ├── types.ts            # UserProfile, AuthTokens, LoginResponse interfaces
    │   ├── token-storage.ts    # SSR-safe storage & JWT expiration decoder
    │   └── auth-context.tsx    # React AuthContext & useAuth() hook
    ├── api/                    # HTTP client
    │   └── client.ts           # Typed fetch client with silent 401 token refresh interceptor
    └── services/               # Domain services
        └── workspace-service.ts# Typed workspace query & management service
```

---

## 🔐 Authentication & Session Architecture

### Dual-Channel Security
* **Web UI (JWT Tokens)**:
  * `POST /api/auth/login/`: Authenticates with username/email and password.
  * Tokens stored in local storage (`access` 60m, `refresh` 24h).
  * **Automatic 401 Refresh Interceptor**: If an API request returns `401 Unauthorized`, `apiClient` silently calls `POST /api/auth/refresh/` and replays the failed request without interrupting the user.
* **FastMCP Agent Interface (API Keys)**:
  * Agents (Cursor, OpenCode, FastMCP clients) authenticate independently via API Key (`key_id:secret`) with granular scope verification.

---

## 🎨 Design System & Aesthetics (Stealth Minimalist)

* **Tailwind CSS Only**: Zero inline styles across all components.
* **Theme**: Deep dark graphite background (`#090d16`) with subtle radial gradients (`#1e1b4b`).
* **Micro-Interactions**: Smooth hover transitions, loading skeletons, and subtle glassmorphic backdrop filters.
* **Role Indicators**:
  * 👑 **Admin**: Full control over workspace criteria, scrapers, definitions, and members.
  * 🛡️ **Manager**: Operational control over pipeline runs and screening.
  * 🔬 **Researcher**: Paper reviews, parameter extractions, and analysis exploration.

---

## 🚀 Development & Build

```bash
# Install dependencies
npm install

# Start local development server (port 3000)
npm run dev

# Build production bundle
npm run build

# Start production server
npm run start
```
