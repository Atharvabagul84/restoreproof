# Design System

Recorded 2026-10-27 from `app/globals.css`, `app/layout.tsx` and the active components (`FeatureWorkspace`, `FeatureReview*`, `components/team/`). These are the values in use; follow them, don't invent new ones.

## 01 Brand Identity
Calm, precise, honest, dark, focused.

## 02 Colour Palette
Dark theme only. Tokens are Tailwind `@theme` colours in `app/globals.css`; use the token name (e.g. `bg-primary`), never a raw hex in components.

| Token | Hex | Use for |
|---|---|---|
| `background` | #09090b | Page background, inputs (team) |
| `surface` / `surface-dim` | #0c0c0f | Base panels |
| `surface-container-low` | #0f0f12 | Subtle panels |
| `surface-container` | #121215 | Cards, secondary button background |
| `surface-container-high` | #18181b | Raised cards |
| `surface-container-highest` | #1e1e22 | Highest elevation |
| `on-surface` | #fafafa | Main text |
| `on-surface-variant` | #a1a1aa | Secondary text, helper text |
| `secondary` | #71717a | Muted text, labels |
| `outline` | #52525b | Hover borders |
| `outline-variant` | #27272a | Default borders, dividers |
| `primary` | #a78bfa | Primary buttons, links, focus rings |
| `primary-fixed-dim` | #c4b5fd | Primary button hover |
| `primary-container` | #7c3aed | Text selection background, strong accents |
| `on-primary` | #0a0012 | Text on primary buttons |
| `tertiary` | #34d399 | Success states |
| `tertiary-container` | #065f46 | Success backgrounds |
| `error` | #ef4444 | Errors, destructive actions |
| `error-container` | #3b1111 | Error backgrounds |
| `on-error-container` | #fca5a5 | Text on error backgrounds |

## 03 Typography
- **Font:** Geist (Google Fonts), Geist Mono for code and technical values
- **H1:** `text-4xl` (36px) → `sm:text-5xl` (48px), semibold, `tracking-tight`, `leading-tight`
- **H2:** `text-3xl` (30px), semibold
- **H3 / brand:** `text-xl` (20px), semibold
- **Body:** `text-base` (16px), `leading-7`, colour `on-surface-variant` for intro copy
- **UI text and inputs:** `text-sm` (14px), `leading-6`
- **Caption / labels:** `text-xs` (12px)

## 04 Spacing
- Tailwind 4px scale. Common: 8, 12, 16, 20, 24, 32, 48px (`2, 3, 4, 5, 6, 8, 12`)
- Page gutter: `px-5` (20px) on mobile, `sm:px-8` (32px) from 640px
- Max content width: 1440px (`max-w-[1440px]`); reading width `max-w-2xl`

## 05 Border Radius
- Buttons, inputs, cards: 12px (`rounded-xl`)
- Small controls and chips: 8px (`rounded-lg`)
- Large panels: 16px (`rounded-2xl`)
- Pills and avatars: `rounded-full`

## 06 Components
- **Primary button:** `teamPrimary` in `components/team/team-client.ts`: `bg-primary`, `text-on-primary`, 12px radius, `px-4 py-2.5 text-sm font-semibold`, hover `bg-primary-fixed-dim`, disabled 40% opacity
- **Secondary button:** `teamSecondary`: `bg-surface-container`, 1px `outline-variant` border, hover border `primary/60`
- **Inputs:** `teamInput` / `inputStyle` in `FeatureReviewFields.tsx`: 1px `outline-variant` border, 12px radius, focus border `primary` plus `ring-primary/20`
- **Focus:** every interactive element shows `outline-2 outline-offset-2 outline-primary` on `focus-visible`
- **Notices:** `rounded-xl bg-primary/5 px-4 py-3` for info; error colours for failures. Errors are always visible text, never silent

## 07 Icons
- Material Symbols Outlined (Google Fonts), 20px default, via the `.material-symbols-outlined` class
- Decorative icons get `aria-hidden`

## 08 Breakpoints
- Mobile: under 640px (default styles)
- Tablet: `sm` 640px and `md` 768px
- Desktop: `lg` 1024px and up (two-column workspace: 240px sidebar + content)

## Rules
- Never use colours outside these tokens
- Mobile first. Every page must work at 375px width
- Example content is always labelled as an example
- Personal review marks must never look like test results or approvals
