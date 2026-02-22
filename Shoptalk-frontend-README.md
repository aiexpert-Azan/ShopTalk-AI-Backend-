# ShopTalk AI - Frontend

A comprehensive WhatsApp-integrated AI-powered storefront management dashboard built for Pakistani small businesses. This Next.js 16 application provides shopkeepers with a complete digital business management suite -- from onboarding and product catalog management to AI-assisted customer conversations, order processing, billing, and weekly analytics.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Framework | Next.js 16 (App Router, Turbopack) |
| Language | TypeScript 5.7 |
| UI Library | React 19.2 |
| Styling | Tailwind CSS 4 + shadcn/ui (Radix UI primitives) |
| Forms | React Hook Form + Zod validation |
| Charts | Recharts 2.15 |
| Icons | Lucide React |
| Toasts | Sonner |
| Analytics | Vercel Analytics |

---

## Project Structure

```
app/                              # Next.js App Router pages
  page.tsx                        # Landing page (public)
  login/page.tsx                  # Login page
  signup/page.tsx                 # Sign-up page
  onboarding/
    shop-profile/page.tsx         # Step 1: Shop name, category, location, languages
    business-hours/page.tsx       # Step 2: Weekly schedule configuration
    delivery-payment/page.tsx     # Step 3: Delivery toggle, fee, payment methods
    ai-config/page.tsx            # Step 4: AI reply mode, escalation rules
  dashboard/
    page.tsx                      # Main dashboard (stats, conversations, quick actions)
    orders/page.tsx               # Order management with filters and actions
    products/page.tsx             # Product catalog with add/edit/delete
    customers/page.tsx            # Customer directory with search
    insights/page.tsx             # Weekly AI-generated analytics
    billing/page.tsx              # Subscription plans, payment method, invoices
    settings/page.tsx             # Profile, shop details, hours, delivery, AI config

components/
  auth/
    login-form.tsx                # Login form with phone + password
    signup-form.tsx               # Sign-up form with name, phone, email, password
  billing/
    billing-content.tsx           # Plans grid, usage meter, payment method dialog, invoice history
  customers/
    customers-content.tsx         # Searchable customer table with stats and actions
  dashboard/
    dashboard-content.tsx         # Greeting, stat cards, conversations table, quick actions
    stat-cards.tsx                # Messages handled, orders received, time saved
    conversations-table.tsx       # Live WhatsApp conversations with AI/human badges
    quick-actions.tsx             # Add product, view orders, manage catalog, emergency AI toggle
  insights/
    insights-content.tsx          # Report header with Save/WhatsApp export, insight cards
    ai-insight-banner.tsx         # AI-generated weekly summary banner
    top-questions-card.tsx        # Most-asked customer questions chart
    busiest-hours-card.tsx        # Hourly message volume bar chart
    popular-products-card.tsx     # Top products by inquiry count
    recent-sales-table.tsx        # Recent AI-initiated sales table
  landing/
    hero-section.tsx              # Landing page hero with headline and CTA
    features-section.tsx          # Feature cards grid
    cta-section.tsx               # Bottom call-to-action section
  layout/
    dashboard-shell.tsx           # Sidebar navigation, header (AI status, notifications, profile)
    logo.tsx                      # ShopTalk AI branding logo
    onboarding-layout.tsx         # Step indicator layout for onboarding flow
    public-header.tsx             # Public page header with nav links
    public-footer.tsx             # Public page footer
  onboarding/
    shop-profile-form.tsx         # Shop name, category, location, language selection
    business-hours-form.tsx       # Per-day open/close time pickers with bulk toggle
    delivery-payment-form.tsx     # Delivery toggle, fee input, payment method grid
    ai-config-form.tsx            # AI reply mode radios, escalation rule toggles
  orders/
    orders-content.tsx            # Filter tabs, order list, message dialog, print receipt
    order-card.tsx                # Individual order card with status, items, action buttons
    order-filters.tsx             # Status filter tabs (All, New, Accepted, etc.)
  products/
    products-content.tsx          # Product grid, add/edit dialog, CSV export, pagination
    product-card.tsx              # Product card with image, price, stock toggle, edit/delete
    product-filters.tsx           # Category filter, sort dropdown, search
    product-dialog.tsx            # Add/Edit product dialog with image upload
    add-product-card.tsx          # Dashed "+" card to trigger new product creation
  settings/
    settings-content.tsx          # Tabbed settings: profile, shop, hours, delivery, AI

lib/
  api.ts                          # Mock API functions (auth, products, orders, insights, etc.)
  constants.ts                    # App constants (categories, languages, payment methods, etc.)
  types.ts                        # Full TypeScript interface/type definitions
  user-context.tsx                # React Context for current user session and AI status
  utils.ts                        # Utility functions (cn class merger)
```

---

## Pages & Features

### Public Pages

| Route | Description |
|---|---|
| `/` | Landing page with hero, features grid, and CTA |
| `/login` | Phone number + password login with Zod validation |
| `/signup` | Account registration (name, phone, email, password) |

### Onboarding Flow (4 Steps)

| Route | Step | What It Does |
|---|---|---|
| `/onboarding/shop-profile` | 1 | Shop name, business category, city/area, AI response languages (Urdu, English, Punjabi, Roman Urdu) |
| `/onboarding/business-hours` | 2 | Per-day open/close time configuration with "same time for all" bulk toggle |
| `/onboarding/delivery-payment` | 3 | Delivery on/off, delivery fee, payment methods (COD, EasyPaisa, JazzCash, Bank Transfer) |
| `/onboarding/ai-config` | 4 | AI reply mode (Always / Outside Hours / Common Questions Only), escalation rules |

### Dashboard

| Route | Description |
|---|---|
| `/dashboard` | Overview with stat cards (messages handled, orders received, time saved), live conversations table, and quick action buttons including Emergency Manual Mode (Turn AI Off/On) |
| `/dashboard/orders` | Order management with status filter tabs, per-order cards showing items/totals, Print Receipt (opens browser print), Message Customer (WhatsApp dialog with quick-reply chips) |
| `/dashboard/products` | Product catalog grid with category/sort filters, Add New Product dialog (image upload, name, description, price, category, stock), inline edit/delete, CSV export, Load More pagination |
| `/dashboard/customers` | Searchable customer directory table with total/active/new stats, per-customer message and call actions |
| `/dashboard/insights` | AI-generated weekly analytics: top questions chart, busiest hours bar chart, popular products ranking, recent automated sales. Save Report (downloads .txt) and Send to WhatsApp (opens wa.me) |
| `/dashboard/billing` | Current plan usage meter, 4-tier plan comparison (Starter Rs. 9,999 / Growth Rs. 19,999 / Business Rs. 39,999 / Enterprise Custom), Update Payment Method dialog (EasyPaisa, JazzCash, Bank Transfer, Card), billing history with downloadable invoices |
| `/dashboard/settings` | 5-tab settings: My Profile (name, email, password reset), Shop Details (name, category, location, description), Business Hours (weekly summary), Delivery & Payment (toggle, fee, methods), AI Assistant (status, reply mode, custom greeting) |

---

## Key Interactive Features

- **Emergency Manual Mode**: Dashboard quick action to instantly toggle AI on/off with confirmation dialog. The header AI status badge updates in real-time between "AI Online" (green) and "AI Offline" (red).
- **Notifications Popover**: Bell icon opens a popover with unread badge, per-notification routing, mark-all-read, and clear-all.
- **Profile Dropdown**: Avatar opens a dropdown with user name/phone, links to Profile, Shop Settings, Billing, and Log Out.
- **Print Receipt**: Generates a styled receipt in a new browser window and triggers the native print dialog.
- **Message Customer**: Opens a dialog with customer info, pre-built quick-reply chips, and a custom message textarea that opens WhatsApp via `wa.me`.
- **Save Report / Send to WhatsApp**: Insights page buttons that generate a formatted report as a downloadable text file or open WhatsApp with a pre-composed message.
- **Product Management**: Full CRUD via a dialog with drag-and-drop image upload, inline stock toggle, and CSV export of the entire catalog.
- **Payment Method Update**: Billing page dialog supporting EasyPaisa, JazzCash, Bank Transfer, and Credit/Debit Card with field-specific inputs.

---

## Input Validation

All forms use **Zod** schemas with **React Hook Form** for real-time validation:

| Field | Constraint |
|---|---|
| Owner Name | 2-30 characters, `maxLength=30` on input |
| Shop Name | 2-30 characters, `maxLength=30` on input |
| Phone Number | Exactly 11 digits, `maxLength=11`, `inputMode="numeric"` |
| Email | Valid email format (optional) |
| Password | Minimum 8 characters |

---

## User Context

The app uses a lightweight React Context (`lib/user-context.tsx`) that stores:
- **Current user**: name, phone, email (used for greeting, avatar initials, profile dropdown)
- **AI active status**: global toggle shared between the dashboard quick actions and the header status badge

The context is provided at the root layout level and consumed by `DashboardShell`, `DashboardContent`, and `QuickActions`.

---

## Mock API Layer

All data is served from `lib/api.ts` using simulated async functions with realistic delays. This allows the entire frontend to function independently without a backend. The mock API covers:

- `login()` / `signUp()` -- Authentication
- `saveShopProfile()` / `saveBusinessHours()` / `saveDeliverySettings()` / `saveAIConfig()` -- Onboarding
- `getDashboardStats()` / `getLiveConversations()` -- Dashboard
- `getProducts()` / `getOrders()` -- Product & order data
- `getWeeklyInsights()` -- Analytics data
- `getPlanInfo()` -- Billing/subscription data

---

## Getting Started

```bash
# Install dependencies
pnpm install

# Start development server
pnpm dev

# Build for production
pnpm build

# Start production server
pnpm start
```

The app runs on `http://localhost:3000` by default.

---

## Deployment

This project is optimized for **Vercel** deployment. Click "Publish" in the v0 UI or connect a GitHub repository and deploy via the Vercel dashboard. No environment variables are required since the app uses a mock API layer.

---

## Design System

- **Primary color**: Green (`--primary`) -- used for AI status, CTAs, and active states
- **Neutral palette**: Background, card, muted, and foreground tokens defined in `globals.css`
- **Typography**: Inter font family via `next/font/google`
- **Components**: shadcn/ui (Radix UI) for all interactive primitives (Dialog, Popover, DropdownMenu, Select, Switch, etc.)
- **Icons**: Lucide React icon set throughout
- **Responsive**: Mobile-first design with `sm:` / `md:` / `lg:` breakpoints
