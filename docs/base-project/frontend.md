> Historical Chatbot-USMS documentation, retained for provenance and baseline reference. Claims, metrics, links and deployment instructions below are inherited and are not RagSec guarantees. See [RagSec README](../../README.md).

# Frontend — Next.js Application

## Framework & Setup

| Property | Value |
|----------|-------|
| Framework | Next.js 15.5.15 |
| Router | App Router (Next.js 13+ layout system) |
| Language | TypeScript 5.8.2 |
| Styling | Tailwind CSS 3.4.17 |
| Node.js | ≥18 |
| Output mode | `standalone` (Docker-friendly) |

---

## Directory Structure

```
frontend/src/
├── app/                    # Next.js App Router pages
│   ├── layout.tsx          # Root layout: ThemeProvider + I18nProvider
│   ├── page.tsx            # Home/landing page → redirects to /login
│   ├── login/page.tsx      # Login & registration form
│   ├── chat/page.tsx       # Main chat interface (SSE streaming)
│   ├── admin/page.tsx      # Admin dashboard
│   ├── profile/page.tsx    # User profile & GDPR options
│   └── privacy/page.tsx    # Privacy policy page
├── components/
│   ├── chat/
│   │   ├── ChatInput.tsx   # Message input + send button
│   │   ├── MessageBubble.tsx # Message rendering with Markdown
│   │   ├── TimetableGrid.tsx # Visual timetable table
│   │   └── TypingDots.tsx  # Animated typing indicator
│   ├── admin/
│   │   └── EdtForm.tsx     # Timetable JSON upload/validation form
│   ├── providers/
│   │   ├── I18nProvider.tsx
│   │   └── ThemeProvider.tsx
│   ├── Modal.tsx
│   ├── LanguageSwitcher.tsx
│   └── PrivacyPolicies.tsx
├── lib/
│   ├── api.ts              # All API calls (Axios + Fetch for SSE)
│   ├── i18n.ts             # i18next configuration
│   └── timetable.ts        # Timetable data parsing utilities
├── store/
│   ├── useAuthStore.ts     # Zustand: auth state, login/logout
│   └── useChatStore.ts     # Zustand: conversation history, streaming state
├── locales/
│   ├── fr.json             # French translations
│   ├── en.json             # English translations
│   └── ar.json             # Arabic translations
└── types/
    └── index.ts            # TypeScript interfaces
```

---

## Pages

### `/login`
- Login form and registration tab (toggle)
- Validates email domain client-side before submit
- Privacy policy checkbox required for registration
- On success: stores token + user in localStorage, sets cookies, redirects

### `/chat`
- Main conversational interface
- Conversation sidebar (history list)
- Streaming chat display with SSE
- Message feedback buttons (thumbs up/down)
- Class selector modal if class not set
- Timetable grid renderer when response contains timetable data
- Typing indicator during generation

### `/admin`
- Statistics cards: total users, conversations, messages
- Top questions / weak questions tables
- User list with search
- FAQ file management (upload, preview, download, delete)
- Timetable publisher (upload JSON → validate → publish to DB)
- Published timetable management (view, delete)
- Class change request review (approve/reject)
- Cache flush button
- Old data cleanup (180-day purge)

### `/profile`
- User info display (email, role, class, language)
- Activity dashboard chart (messages per day)
- Language switcher (FR/EN/AR)
- Class change request form
- GDPR: Export data button (downloads JSON)
- GDPR: Delete account button (with confirmation)

### `/privacy`
- Full privacy policy page

---

## State Management — Zustand

### `useAuthStore`

```typescript
{
  user: User | null;
  token: string | null;
  hydrated: boolean;       // true after localStorage read on mount
  hydrate(): void;         // reads token/user from localStorage
  login(email, password): Promise<void>;
  register(email, password, classLabel, acceptedPrivacy): Promise<void>;
  setLanguage(lang): Promise<void>; // syncs to backend + i18n
  logout(): void;          // clears localStorage, cookies, chat state
  isAdmin(): boolean;
}
```

**Token persistence:** localStorage + cookie  
**Cookie attributes:** `samesite=strict`, `secure` on HTTPS, `max-age=86400`

### `useChatStore`

Manages:
- List of conversations
- Active conversation + messages
- Streaming state (in-progress, chunk buffer)
- Class label selection

---

## HTTP Client — `lib/api.ts`

### Axios Instance
Base URL: `process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"`

**Request interceptor:** Reads token from localStorage → sets `Authorization: Bearer <token>`

**Response interceptor (401 handler):**
1. Attempt `POST /api/v1/auth/refresh`
2. If success → update localStorage token → retry original request
3. If failure → redirect to `/login`

### SSE Streaming — `streamMessage()`
Uses the **native `fetch` API** (not Axios) to handle SSE:
```typescript
async function* streamMessage(question, class_label, conversation_id?)
```
- Reads the response body as a `ReadableStream`
- Decodes `data: <chunk>` lines
- Yields `{type: "text", content}` for text chunks
- Yields `{type: "metadata", ...}` for `__metadata__:` chunks
- Terminates on `data: [DONE]`

---

## Internationalization (i18n)

**Library:** i18next 26.0.3 + react-i18next 17.0.2

**Configuration file:** `lib/i18n.ts`

| Property | Value |
|----------|-------|
| Default language | `fr` |
| Supported languages | `fr`, `en`, `ar` |
| Translation files | `src/locales/{lang}.json` |
| Detection | Browser language detector (`i18next-browser-languagedetector`) |
| Namespace | `translation` (default) |

**Language persistence:**
- Stored in `localStorage` by i18next detector
- Synced with backend `language` field per user
- Applied on login/register from user profile

**RTL support:** Arabic (`ar`) requires RTL layout. The root layout applies `dir="rtl"` based on active language.

---

## Theming

**Library:** next-themes 0.4.4

- Light / Dark mode toggle
- System preference respected by default
- CSS class strategy (`class` on `<html>`)
- Tailwind CSS dark mode classes

---

## Routing & Auth Guard

**File:** `middleware.ts`

Next.js middleware reads the `token` and `role` cookies to protect routes:

| Route | Access |
|-------|--------|
| `/login` | Public (redirects to `/chat` if already logged in) |
| `/chat` | Requires `token` cookie |
| `/admin` | Requires `role=admin` cookie |
| `/profile` | Requires `token` cookie |
| `/privacy` | Public |

---

## Forms

Using **React Hook Form** 7.56.4 + **Zod** 3.24.2 for validation.

Example validations:
- Login: `email` (string), `password` (min 1)
- Register: email domain regex, password strength (≥8, digit, special char), privacy checkbox
- Class change request: `requested_class_label` (min 2 chars)

---

## Key Components

### `MessageBubble.tsx`
Renders chat messages:
- User messages: right-aligned, colored bubble
- Assistant messages: left-aligned, with Markdown rendering (react-markdown)
- Feedback thumbs (👍/👎) below assistant messages
- Source file badge if metadata available
- RAG confidence badge (`high`, `medium`, `low`)

### `TimetableGrid.tsx`
Renders structured timetable data returned in message metadata:
- Grid layout by day and time slot
- Color-coded by course type (Cours/TD/TP)
- Professor and room annotations

### `ChatInput.tsx`
- Textarea with `Enter` to send, `Shift+Enter` for new line
- Disabled during streaming
- Character limit display

### `EdtForm.tsx` (Admin)
- JSON paste area for timetable data
- Real-time validation of timetable slot schema
- Preview before publishing
- `POST /api/v1/admin/edt/publish` on confirm

---

## Dependencies Summary

| Package | Version | Purpose |
|---------|---------|---------|
| `next` | 15.5.15 | Framework |
| `react` | 18.3.1 | UI library |
| `typescript` | 5.8.2 | Type safety |
| `tailwindcss` | 3.4.17 | Utility CSS |
| `zustand` | 5.0.3 | State management |
| `axios` | 1.15.0 | HTTP client |
| `i18next` | 26.0.3 | i18n engine |
| `react-i18next` | 17.0.2 | React bindings for i18next |
| `i18next-browser-languagedetector` | 8.2.1 | Auto-detect browser language |
| `react-hook-form` | 7.56.4 | Form state management |
| `zod` | 3.24.2 | Schema validation |
| `react-markdown` | 9.1.0 | Markdown renderer |
| `sonner` | 1.7.4 | Toast notifications |
| `react-dropzone` | 14.3.8 | Drag-and-drop file upload |
| `next-themes` | 0.4.4 | Dark/light mode |
| `lucide-react` | 0.469.0 | Icon set |
| `html-to-image` | 1.11.13 | Screenshot export |
| `@hookform/resolvers` | 3.10.0 | Zod resolver for React Hook Form |
| `@tailwindcss/typography` | 0.5.19 | Prose styling for Markdown |

---

## Docker Build

**File:** `frontend/Dockerfile`

Multi-stage build:
1. `deps` — install node_modules
2. `builder` — `next build` with `output: "standalone"`
3. `runner` — minimal production image

**Environment variable at build time:** `NEXT_PUBLIC_API_URL=http://backend:8000`
