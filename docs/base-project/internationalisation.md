> Historical Chatbot-USMS documentation, retained for provenance and baseline reference. Claims, metrics, links and deployment instructions below are inherited and are not RagSec guarantees. See [RagSec README](../../README.md).

# Internationalisation (i18n)

## Overview

The application supports three languages throughout the entire stack:

| Language | Code | Direction |
|----------|------|-----------|
| French | `fr` | LTR |
| English | `en` | LTR |
| Arabic | `ar` | RTL |

French is the default and the primary language of the institution.

---

## Frontend i18n

**Library:** i18next 26.0.3 + react-i18next 17.0.2

### Configuration (`lib/i18n.ts`)

```typescript
i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources: { fr, en, ar },
    fallbackLng: "fr",
    defaultNS: "translation",
    detection: {
      order: ["localStorage", "navigator"],
      caches: ["localStorage"],
    }
  });
```

Language detection order:
1. Check `localStorage` (user's saved preference)
2. Browser `navigator.language`
3. Fall back to `fr`

### Translation Files

Located in `frontend/src/locales/`:

- `fr.json` — French (base language)
- `en.json` — English
- `ar.json` — Arabic

### Translation Namespace Structure

All translation files share the same key hierarchy:

```json
{
  "common": { ... },      // Shared UI elements
  "auth": { ... },        // Login/register page
  "chat": { ... },        // Chat interface
  "admin": { ... },       // Admin dashboard
  "profile": { ... },     // Profile page
  "privacy": { ... }      // Privacy policy page
}
```

### Key Examples (`fr.json`)

```json
{
  "common": {
    "login": "Connexion",
    "logout": "Déconnexion",
    "send": "Envoyer",
    "loading": "Chargement...",
    "assistant_name": "Assistant USMS",
    "ia_operational": "IA Opérationnelle"
  },
  "auth": {
    "login_title": "Bon retour !",
    "register_title": "Créer un compte",
    "institutional_email_hint": "Utilisez votre email @usms.ac.ma",
    "password_hint": "Min. 8 caractères, un chiffre et un symbole",
    "privacy_policy_accept": "J'ai lu et j'accepte la politique de confidentialité"
  },
  "chat": {
    "welcome_msg": "Je suis votre assistant académique...",
    "placeholder": "Posez votre question..."
  }
}
```

### Usage in Components

```typescript
import { useTranslation } from "react-i18next";

const { t } = useTranslation();
<button>{t("common.send")}</button>
<p>{t("chat.welcome_msg")}</p>
```

### Language Switching

**Component:** `LanguageSwitcher.tsx`

- Calls `useAuthStore.setLanguage(lang)`:
  1. Calls `POST /api/v1/auth/me/language` to persist preference in DB
  2. Updates `localStorage` user object
  3. Calls `i18n.changeLanguage(lang)` — immediately updates UI
- Also available on the profile page

### RTL Support

When `ar` is active, the root `<html>` element receives `dir="rtl"`. Tailwind CSS uses the `rtl:` variant for layout adjustments.

---

## Backend i18n

### Language Detection

`groq_service.detect_language(text)` uses:
1. Script detection: Arabic Unicode range `[؀-ۿ]` → `"ar"`
2. CJK detection: `[一-鿿]` (excluded, not supported)
3. LLM-assisted detection for EN vs FR

### Multilingual FAQ Retrieval

Since the FAQ knowledge base is primarily in French:
1. EN/AR user queries are translated to French before embedding
2. French chunks are retrieved from Qdrant
3. Answer is generated in the user's target language (specified in the Groq system prompt)

### Multilingual Emotion Detection

The emotion detection system (`chatbot_service.detect_user_state()`) includes marker lists in all three languages:

**Example for `stressed`:**
- FR: `stressé`, `panique`, `j'arrive pas`, `tout se passe mal`, `angoissé`
- EN: `stressed`, `panic`, `overwhelmed`, `freaking out`
- AR: `متوتر`, `ضائق`, `مرهق`

### Multilingual Response Prompts

All Groq system prompts include:
```python
f"Réponds uniquement en {language}."
```

Where `language` is one of `"français"`, `"anglais"`, `"arabe"`.

---

## User Language Preference

| Storage | Value |
|---------|-------|
| Database | `users.language` column (`fr`, `en`, `ar`) |
| Frontend | `localStorage` via i18next detector |
| Cookie | Indirectly via user object in localStorage |
| Request | `Accept-Language` header (fallback if DB pref absent) |

**Priority order for language selection in chat:**
1. `users.language` from DB (most reliable — explicitly set by user)
2. `Accept-Language` HTTP header (browser default)
3. Hard-coded default: `fr`

---

## Language-Aware Features

| Feature | Multilingual? |
|---------|--------------|
| UI labels | ✅ All 3 languages |
| Error messages (frontend) | ✅ All 3 languages |
| Chat responses | ✅ Auto-detected + user pref |
| Emotion detection | ✅ Markers in FR/EN/AR |
| Conversation titles | ✅ Generated in user's language |
| FAQ retrieval | ✅ Query translated to FR, answer in user lang |
| Timetable responses | ✅ Generated in user's language |
| Backend error messages | ⚠️ French only (developer-facing) |
