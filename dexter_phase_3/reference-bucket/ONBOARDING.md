# Engineering Onboarding Guide
## Teamleiter Live-Statistik (Call Center Performance Dashboard)

Welcome to the team! This document will help you get up to speed with our real-time agent statistics platform.

---

## 📋 Table of Contents

1. [Project Overview](#project-overview)
2. [Technology Stack](#technology-stack)
3. [Project Structure](#project-structure)
4. [Getting Started](#getting-started)
5. [Development Workflow](#development-workflow)
6. [Architecture Overview](#architecture-overview)
7. [Key Features](#key-features)
8. [Database Schema](#database-schema)
9. [API Endpoints](#api-endpoints)
10. [Frontend Components](#frontend-components)
11. [Code Patterns & Conventions](#code-patterns--conventions)
12. [Testing & Debugging](#testing--debugging)
13. [Common Tasks](#common-tasks)
14. [Troubleshooting](#troubleshooting)

---

## 🎯 Project Overview

This is a **real-time call center performance monitoring platform** designed for team leaders. It provides live tracking of agents, call statistics, and detailed reporting capabilities.

**Core Purpose:**
- Monitor agent status in real-time (in conversation, post-processing, preparing, waiting)
- Track call outcomes and success rates across multiple projects
- Provide detailed analytics with flexible filtering by date, time, agent, and project
- Enable drill-down into individual call details with recording access

**Target Users:** Team leaders and managers in call center operations

---

## 🛠 Technology Stack

### Frontend
- **Framework:** React 18 with TypeScript
- **Build Tool:** Vite 5
- **UI Components:** Shadcn/ui (built on Radix UI primitives)
- **Styling:** Tailwind CSS 3
- **State Management:** TanStack Query v5 (React Query)
- **Routing:** Wouter 3
- **Forms:** React Hook Form + Zod validation
- **Icons:** Lucide React + React Icons

### Backend
- **Runtime:** Node.js with TypeScript
- **Framework:** Express.js 4
- **Database ORM:** Drizzle ORM
- **Database:** PostgreSQL (Neon Serverless)
- **External DB:** Direct PostgreSQL connection for read-only operations
- **Validation:** Zod schemas

### Development Tools
- **TypeScript Execution:** tsx
- **Build:** esbuild (production)
- **Database Migrations:** Drizzle Kit
- **Package Manager:** npm

---

## 📁 Project Structure

```
.
├── client/                 # Frontend application
│   ├── src/
│   │   ├── components/    # React components
│   │   │   ├── ui/       # Shadcn/ui components
│   │   │   └── ...       # Custom components
│   │   ├── hooks/        # Custom React hooks
│   │   ├── lib/          # Utility functions
│   │   ├── pages/        # Page components
│   │   ├── App.tsx       # Main app component
│   │   ├── main.tsx      # Entry point
│   │   └── index.css     # Global styles
│   └── index.html        # HTML template
│
├── server/                # Backend application
│   ├── index.ts          # Server entry point
│   ├── routes.ts         # API route definitions
│   ├── storage.ts        # Storage interface & implementations
│   ├── external-storage.ts  # External DB storage implementation
│   ├── external-db.ts    # External DB connection & queries
│   ├── db.ts             # Drizzle ORM setup
│   ├── transcription-service.ts  # Audio transcription integration
│   └── vite.ts           # Vite dev server integration
│
├── shared/               # Shared code between frontend & backend
│   └── schema.ts        # Database schema & types
│
├── package.json         # Dependencies & scripts
├── vite.config.ts       # Vite configuration
├── tailwind.config.ts   # Tailwind configuration
├── drizzle.config.ts    # Database migration config
└── tsconfig.json        # TypeScript configuration
```

### Important Path Aliases
- `@/` → `client/src/`
- `@shared/` → `shared/`
- `@assets/` → `attached_assets/`

---

## 🚀 Getting Started

### Prerequisites
- Node.js (version specified in package.json)
- PostgreSQL database access
- External database credentials (for production data)

### Environment Variables

You'll need to set up the following environment variables:

```bash
# Main Database (Neon)
DATABASE_URL=postgresql://user:pass@host/database

# External Database (Read-only)
EXTERNAL_DB_HOST=your_host
EXTERNAL_DB_DATABASE=your_database
EXTERNAL_DB_USER=your_user
EXTERNAL_DB_PASSWORD=your_password

# Dialfire API (for campaign mapping)
DIALFIRE_API_TOKEN=your_token

# Server Port (optional, defaults to 5000)
PORT=5000
```

### Installation Steps

1. **Clone and Install:**
   ```bash
   npm install
   ```

2. **Set Up Environment Variables:**
   - Configure all required environment variables listed above
   - The Replit environment automatically provisions `DATABASE_URL`

3. **Database Setup:**
   ```bash
   # Push schema changes to database
   npm run db:push
   
   # If you get data-loss warnings:
   npm run db:push --force
   ```

4. **Start Development Server:**
   ```bash
   npm run dev
   ```
   - Backend: Express server with API routes
   - Frontend: Vite dev server with HMR
   - Both served on `http://localhost:5000`

5. **Production Build:**
   ```bash
   npm run build    # Build frontend + backend
   npm start        # Run production server
   ```

---

## 💻 Development Workflow

### Available Scripts

| Command | Description |
|---------|-------------|
| `npm run dev` | Start development server (port 5000) |
| `npm run build` | Build for production |
| `npm start` | Run production build |
| `npm run check` | TypeScript type checking |
| `npm run db:push` | Push schema changes to database |

### Development Server
- **Single Port:** Everything runs on port 5000 (API + frontend)
- **Hot Reload:** Vite provides instant HMR for frontend changes
- **Auto-restart:** Server automatically restarts on backend changes

### Making Changes

1. **Frontend Changes:**
   - Edit files in `client/src/`
   - Changes reflect immediately via HMR
   - No manual refresh needed

2. **Backend Changes:**
   - Edit files in `server/`
   - Server auto-restarts
   - Check console for logs

3. **Schema Changes:**
   - Edit `shared/schema.ts`
   - Run `npm run db:push` to sync with database
   - **Never change primary key types** (serial ↔ varchar breaks migrations)

---

## 🏗 Architecture Overview

### High-Level Architecture

```
┌─────────────┐     HTTP/REST      ┌─────────────┐
│   Client    │ ◄─────────────────► │   Server    │
│  (React)    │                     │  (Express)  │
└─────────────┘                     └─────────────┘
                                           │
                                           │
                        ┌──────────────────┴──────────────────┐
                        │                                      │
                        ▼                                      ▼
                 ┌─────────────┐                      ┌─────────────┐
                 │  Internal   │                      │  External   │
                 │  Database   │                      │  Database   │
                 │  (Neon PG)  │                      │  (Read-Only)│
                 └─────────────┘                      └─────────────┘
```

### Frontend Architecture

**State Management:**
- TanStack Query for server state (caching, refetching, mutations)
- React hooks for local state
- Polling for real-time updates (no WebSockets)

**Component Structure:**
- Atomic design with Shadcn/ui components
- Custom components in `client/src/components/`
- Page components in `client/src/pages/`

**Data Flow:**
1. Components use custom hooks (`use-statistics.ts`, `use-cyprus-time.ts`)
2. Hooks use TanStack Query for API calls
3. Query client handles caching and refetching
4. Components render based on query state (loading, error, success)

### Backend Architecture

**API Layer:**
- RESTful endpoints in `server/routes.ts`
- Express middleware for JSON parsing and logging
- Error handling middleware

**Data Layer:**
- `IStorage` interface for abstraction
- `ExternalStorage` implementation (active)
- Connects to external PostgreSQL database
- Drizzle ORM for type-safe queries

**Real-time Updates:**
- Polling-based (no WebSockets)
- Agent status: 60-second intervals
- Statistics: Manual refresh via dashboard
- Database status: 30-second intervals
- Dialfire API status: 60-second intervals

---

## ⭐ Key Features

### 1. Agent Management
- Track agent status: `im_gespraech`, `nachbearbeitung`, `vorbereitung`, `wartet`
- Real-time status updates
- Agent selection for filtered views

### 2. Live Statistics Dashboard
- Filterable by date range, time range, agents, and projects
- Metrics include:
  - Total calls attempted (`anzahl`)
  - Completed calls (`abgeschlossen`)
  - Successful calls (`erfolgreich`)
  - Time tracking (wait, talk, post-processing, preparation)
  - Success per hour (`erfolg_pro_stunde`)
  - Outcome breakdowns by category (positive/negative/open)

### 3. Project-Based Reporting
- Multi-project support
- Campaign ID resolution (cryptic IDs → readable names via Dialfire API)
- Project-specific targets and tracking
- Aggregated statistics per project

### 4. Call Details & Analytics
- Drill-down to individual call records
- Call grouping by contact
- Recording access via URLs
- Transcription integration
- Time-based filtering (specific hours)

### 5. Notifications
- Real-time toast notifications for:
  - New calls
  - Positive outcomes
  - Database connection issues
  - Dialfire API issues

### 6. User Preferences
- Sidebar collapse state saved via cookies
- Keyboard shortcuts (sidebar toggle)
- Mobile-responsive design

---

## 🗄 Database Schema

### Core Tables

#### `agents`
```typescript
{
  id: varchar (UUID, primary key)
  name: text
  isActive: boolean
  currentStatus: 'im_gespraech' | 'nachbearbeitung' | 'vorbereitung' | 'wartet'
  createdAt: timestamp
}
```

#### `projects`
```typescript
{
  id: varchar (UUID, primary key)
  name: text
  isActive: boolean
  createdAt: timestamp
}
```

#### `callOutcomes`
```typescript
{
  id: varchar (UUID, primary key)
  name: text
  category: 'positive' | 'negative' | 'offen'
  displayOrder: integer
}
```

#### `agentStatistics`
```typescript
{
  id: varchar (UUID, primary key)
  agentId: varchar (foreign key)
  projectId: varchar (foreign key)
  date: timestamp
  anzahl: integer              // Total calls
  abgeschlossen: integer       // Completed calls
  erfolgreich: integer         // Successful calls
  wartezeit: integer           // Wait time (minutes)
  gespraechszeit: integer      // Talk time (minutes)
  nachbearbeitungszeit: integer // Post-processing (minutes)
  vorbereitungszeit: integer   // Preparation (minutes)
  erfolgProStunde: integer     // Success per hour
  arbeitszeit: integer         // Total work time (minutes)
  outcomes: jsonb              // Outcome breakdown
  createdAt: timestamp
  updatedAt: timestamp
}
```

#### `callDetails`
```typescript
{
  id: varchar (UUID, primary key)
  agentId: varchar (foreign key)
  projectId: varchar (foreign key)
  contactName: text
  contactPerson: text
  contactNumber: text
  callStart: timestamp
  callEnd: timestamp
  duration: integer            // Seconds
  outcome: text
  outcomeCategory: 'positive' | 'negative' | 'offen'
  recordingUrl: text
  notes: text
  // Additional fields for external data mapping
  contactsId: text
  contactsCampaignId: text
  groupId: text               // For grouping related calls
  createdAt: timestamp
}
```

#### `projectTargets`
```typescript
{
  id: varchar (UUID, primary key)
  projectId: varchar (foreign key)
  targetValue: integer
  createdAt: timestamp
  updatedAt: timestamp
}
```

### External Database Views

The application connects to an external PostgreSQL database with read-only access to the `agent_data` view:

```typescript
interface AgentData {
  transaction_id: string
  transactions_fired_date: string
  recordings_start_time: string
  connections_duration: number
  transactions_user_login: string      // Agent login name
  transactions_status: string          // success/declined/open
  transactions_status_detail: string   // Detailed outcome
  recordings_started: string
  recordings_stopped: string
  recordings_location: string          // Recording URL
  connections_phone: string
  contacts_campaign_id: string         // Project/campaign ID
  contacts_id: string
  contacts_firma: string               // Company name
  contacts_notiz: string               // Notes
  contacts_full_name: string           // Contact person
  // Time metrics
  transactions_wrapup_time_sec: number
  transactions_wait_time_sec: number
  transactions_edit_time_sec: number
  transactions_pause_time_sec: number
}
```

---

## 🔌 API Endpoints

### Agent Endpoints
- `GET /api/agents` - Get all agents
- `PATCH /api/agents/:id/status` - Update agent status

### Project Endpoints
- `GET /api/projects` - Get all projects (with campaign name resolution)
- `POST /api/projects-for-agents` - Get projects for specific agents

### Statistics Endpoints
- `POST /api/statistics` - Get agent statistics (filtered)
  ```typescript
  Body: {
    agentIds?: string[]
    projectIds?: string[]
    dateFrom?: string
    dateTo?: string
    timeFrom?: string  // HH:MM format
    timeTo?: string    // HH:MM format
  }
  ```

### Call Details Endpoints
- `POST /api/call-details` - Get detailed call records
- `POST /api/call-details-grouped` - Get grouped call records

### Call Outcomes
- `GET /api/call-outcomes` - Get all call outcomes

### Project Targets
- `GET /api/project-targets` - Get all project targets
- `POST /api/project-targets` - Save project targets

### Utility Endpoints
- `GET /api/cyprus-time` - Get current time in Cyprus timezone
- `GET /api/database-status` - Check database connection status
- `GET /api/dialfire-status` - Check Dialfire API status

### Transcription Endpoints
- `POST /api/transcribe` - Submit audio for transcription
  ```typescript
  Body: { audioUrl: string }
  ```
- `GET /api/transcription-status/:id` - Check transcription status

### Debug Endpoints
- `POST /api/debug/agent-data` - Query raw agent data
- `POST /api/debug/contacts_name` - Query contact name data

---

## 🎨 Frontend Components

### UI Component Library (Shadcn/ui)

Location: `client/src/components/ui/`

Core components include:
- `Button`, `Input`, `Select`, `Checkbox`, `Switch`
- `Dialog`, `Sheet`, `Popover`, `DropdownMenu`
- `Table`, `Card`, `Badge`, `Separator`
- `Toast`, `Alert`, `Skeleton`
- `Sidebar`, `Accordion`, `Tabs`
- `Form` (with React Hook Form integration)

### Custom Components

Location: `client/src/components/`

Key components:
- **`filter-sidebar.tsx`** - Main filtering interface
- **`agent-statistics-table.tsx`** - Statistics display table
- **`project-data-table.tsx`** - Project-specific statistics
- **`expandable-details.tsx`** - Call details drill-down
- **`call-notification.tsx`** - Real-time notifications
- **`app-footer.tsx`** - Footer with system status
- **`agent-selection-popup.tsx`** - Agent multi-select
- **`settings-dialog.tsx`** - Project target settings

### Custom Hooks

Location: `client/src/hooks/`

- **`use-statistics.ts`** - Fetch and manage statistics data
- **`use-cyprus-time.ts`** - Get current Cyprus time
- **`use-mobile.tsx`** - Detect mobile viewport
- **`use-toast.ts`** - Toast notification system
- **`use-campaign-categories.ts`** - Campaign category data

### Pages

Location: `client/src/pages/`

- **`dashboard.tsx`** - Main dashboard page
- **`not-found.tsx`** - 404 page

---

## 📝 Code Patterns & Conventions

### TypeScript Patterns

1. **Shared Types:** All database types defined in `shared/schema.ts`
   ```typescript
   export type Agent = typeof agents.$inferSelect;
   export type InsertAgent = z.infer<typeof insertAgentSchema>;
   ```

2. **Zod Validation:** Use for both API validation and form validation
   ```typescript
   const schema = insertAgentSchema.extend({
     // Add custom validation
   });
   ```

3. **Type Safety:** Drizzle ORM provides full type safety
   ```typescript
   const result = await db.select().from(agents).where(eq(agents.id, id));
   ```

### React Patterns

1. **Data Fetching with TanStack Query:**
   ```typescript
   const { data, isLoading, error } = useQuery({
     queryKey: ['/api/agents'],
     refetchInterval: 60000,  // Optional polling
   });
   ```

2. **Mutations:**
   ```typescript
   const mutation = useMutation({
     mutationFn: async (data) => {
       return apiRequest('POST', '/api/endpoint', data);
     },
     onSuccess: () => {
       queryClient.invalidateQueries({ queryKey: ['/api/agents'] });
     },
   });
   ```

3. **Forms with React Hook Form:**
   ```typescript
   const form = useForm({
     resolver: zodResolver(schema),
     defaultValues: { /* ... */ },
   });
   ```

4. **Hierarchical Query Keys:** Use arrays for cache invalidation
   ```typescript
   queryKey: ['/api/projects', projectId]  // ✅ Good
   queryKey: [`/api/projects/${projectId}`] // ❌ Bad (can't invalidate parent)
   ```

### CSS/Styling Patterns

1. **Tailwind Utility Classes:**
   ```tsx
   <div className="flex items-center justify-between p-4 bg-white dark:bg-gray-900">
   ```

2. **Conditional Classes with `cn` utility:**
   ```typescript
   import { cn } from "@/lib/utils";
   
   <div className={cn(
     "base-classes",
     isActive && "active-classes",
     "more-classes"
   )} />
   ```

3. **Component Variants (CVA):**
   ```typescript
   const buttonVariants = cva("base-classes", {
     variants: {
       variant: { default: "...", destructive: "..." },
       size: { default: "...", sm: "...", lg: "..." },
     },
   });
   ```

### Backend Patterns

1. **Storage Interface:** Always use the `IStorage` interface
   ```typescript
   const agents = await storage.getAllAgents();
   ```

2. **Error Handling:**
   ```typescript
   try {
     const result = await storage.getData();
     res.json(result);
   } catch (error) {
     res.status(500).json({ message: "Error message" });
   }
   ```

3. **Request Validation:**
   ```typescript
   const validated = statisticsFilterSchema.parse(req.body);
   ```

### Important Conventions

1. **No Explicit React Import:** JSX transformer handles it automatically
   ```typescript
   // ✅ Correct
   function Component() { return <div>...</div>; }
   
   // ❌ Not needed
   import React from 'react';
   ```

2. **Environment Variables:**
   - Backend: `process.env.VAR_NAME`
   - Frontend: `import.meta.env.VITE_VAR_NAME` (must have `VITE_` prefix)

3. **Data Test IDs:** Add to all interactive/display elements
   ```tsx
   <button data-testid="button-submit">Submit</button>
   <div data-testid="text-username">{username}</div>
   <div data-testid={`card-product-${productId}`}>...</div>
   ```

4. **Never Modify:**
   - `vite.config.ts` (already configured)
   - `package.json` scripts (use packager tool)
   - `drizzle.config.ts`

---

## 🧪 Testing & Debugging

### Logging Conventions

The codebase uses emoji prefixes for log categorization:

- `🔍` - Debug/investigation logs
- `✅` - Success operations
- `❌` - Errors
- `🚀` - Performance/optimization logs
- `📊` - Data/statistics logs
- `🎙️` - Transcription-related logs
- `🗓️` - Date/time related logs

Example:
```typescript
console.log('🔍 Searching for agent:', agentId);
console.log('✅ Agent found:', agent);
console.error('❌ Error loading agents:', error);
```

### Debugging Tools

1. **Browser DevTools:**
   - React DevTools for component inspection
   - Network tab for API calls
   - TanStack Query DevTools (if enabled)

2. **Server Logs:**
   - Express logs API requests with timing
   - Database query logs from Drizzle
   - External DB query logs with performance metrics

3. **Vite Dev Server:**
   - Hot module replacement for instant updates
   - Error overlay for runtime errors
   - Build analysis

### Common Debugging Scenarios

**API Not Returning Data:**
1. Check server logs for SQL queries
2. Verify external database connection
3. Check date/time filtering logic
4. Inspect request body validation

**Statistics Not Updating:**
1. Check refetch interval settings
2. Verify query key invalidation
3. Check storage implementation
4. Review external DB query filters

**UI Not Rendering:**
1. Check loading/error states
2. Verify data structure matches types
3. Inspect Tailwind classes (PurgeCSS issues)
4. Check conditional rendering logic

---

## ✅ Common Tasks

### Adding a New API Endpoint

1. **Update Storage Interface:**
   ```typescript
   // server/storage.ts
   export interface IStorage {
     newMethod(): Promise<YourType[]>;
   }
   ```

2. **Implement in Storage Class:**
   ```typescript
   // server/external-storage.ts
   async newMethod(): Promise<YourType[]> {
     // Implementation
   }
   ```

3. **Add Route:**
   ```typescript
   // server/routes.ts
   app.get('/api/new-endpoint', async (req, res) => {
     try {
       const data = await storage.newMethod();
       res.json(data);
     } catch (error) {
       res.status(500).json({ message: "Error" });
     }
   });
   ```

4. **Create Frontend Hook (optional):**
   ```typescript
   // client/src/hooks/use-new-data.ts
   export function useNewData() {
     return useQuery({
       queryKey: ['/api/new-endpoint'],
     });
   }
   ```

### Adding a Database Table

1. **Define Schema:**
   ```typescript
   // shared/schema.ts
   export const newTable = pgTable("new_table", {
     id: varchar("id").primaryKey().default(sql`gen_random_uuid()`),
     // ... columns
   });
   
   export const insertNewSchema = createInsertSchema(newTable).omit({
     id: true,
   });
   
   export type NewItem = typeof newTable.$inferSelect;
   export type InsertNewItem = z.infer<typeof insertNewSchema>;
   ```

2. **Push to Database:**
   ```bash
   npm run db:push
   ```

3. **Update Storage Interface:**
   ```typescript
   export interface IStorage {
     getNewItems(): Promise<NewItem[]>;
     createNewItem(item: InsertNewItem): Promise<NewItem>;
   }
   ```

### Adding a UI Component

1. **Create Component File:**
   ```typescript
   // client/src/components/new-component.tsx
   export function NewComponent({ prop }: Props) {
     return <div>...</div>;
   }
   ```

2. **Use Shadcn Components:**
   ```typescript
   import { Button } from "@/components/ui/button";
   import { Card } from "@/components/ui/card";
   ```

3. **Add Data Fetching if Needed:**
   ```typescript
   const { data, isLoading } = useQuery({
     queryKey: ['/api/data'],
   });
   
   if (isLoading) return <Skeleton />;
   ```

4. **Style with Tailwind:**
   ```tsx
   <div className="flex items-center gap-4 p-4 bg-white dark:bg-gray-900">
   ```

### Modifying External Data Queries

1. **Update External DB Function:**
   ```typescript
   // server/external-db.ts
   export async function getNewData(): Promise<AgentData[]> {
     const client = await externalPool.connect();
     try {
       const query = `SELECT ... FROM agent_data WHERE ...`;
       const result = await client.query(query);
       return result.rows;
     } finally {
       client.release();
     }
   }
   ```

2. **Use in Storage Implementation:**
   ```typescript
   // server/external-storage.ts
   const externalData = await getNewData();
   ```

---

## 🔧 Troubleshooting

### Database Connection Issues

**Problem:** "DATABASE_URL must be set" error

**Solution:**
1. Ensure `DATABASE_URL` environment variable is set
2. Check Neon database is provisioned
3. Verify connection string format: `postgresql://user:pass@host/database`

**Problem:** External database timeout

**Solution:**
1. Check `EXTERNAL_DB_*` environment variables
2. Verify network connectivity to external host
3. Check query timeout settings (currently 5 minutes)
4. Review query complexity and add indexes if needed

### Build/Runtime Errors

**Problem:** "Cannot find module '@/...'"

**Solution:**
1. Verify path aliases in `vite.config.ts`
2. Restart TypeScript server in IDE
3. Clear `.vite` cache and rebuild

**Problem:** Tailwind classes not working

**Solution:**
1. Check class names are correct (no typos)
2. Verify `tailwind.config.ts` includes all content paths
3. Check dark mode prefix if styling for dark theme
4. Restart dev server to regenerate styles

**Problem:** TypeScript errors in schema

**Solution:**
1. Never change primary key types
2. Keep existing ID formats (serial vs varchar/UUID)
3. Run `npm run check` for type checking
4. Use `npm run db:push --force` if safe to override

### Data Issues

**Problem:** Statistics showing incorrect data

**Solution:**
1. Check date range filters (timezone issues)
2. Verify external DB query filters
3. Review outcome normalization logic
4. Check agent/project name mapping

**Problem:** Campaign names showing as IDs

**Solution:**
1. Verify `DIALFIRE_API_TOKEN` is set
2. Check Dialfire API status endpoint
3. Review campaign mapping cache (60-minute TTL)
4. Check network connectivity to Dialfire API

**Problem:** Call details not loading

**Solution:**
1. Check agent and project IDs are valid
2. Verify date range is reasonable (not too large)
3. Review external DB query performance
4. Check time filtering logic (HH:MM format)

### Performance Issues

**Problem:** Slow API responses

**Solution:**
1. Review database query execution plans
2. Add indexes to frequently queried columns
3. Optimize date range queries
4. Consider query result caching
5. Check external DB connection pool settings

**Problem:** Frontend lag

**Solution:**
1. Review refetch intervals (reduce if too frequent)
2. Check for unnecessary re-renders
3. Use React.memo for expensive components
4. Optimize TanStack Query cache settings

---

## 📚 Additional Resources

### External Documentation
- [React Documentation](https://react.dev/)
- [TypeScript Handbook](https://www.typescriptlang.org/docs/)
- [TanStack Query](https://tanstack.com/query/latest)
- [Drizzle ORM](https://orm.drizzle.team/)
- [Shadcn/ui](https://ui.shadcn.com/)
- [Tailwind CSS](https://tailwindcss.com/)
- [Wouter Router](https://github.com/molefrog/wouter)
- [Zod Validation](https://zod.dev/)

### Project Documentation
- `replit.md` - Project overview and recent changes
- `shared/schema.ts` - Database schema reference
- `server/routes.ts` - API endpoint reference
- Component files - Inline documentation

### Getting Help

1. **Check Logs:** Server console and browser DevTools
2. **Review Code:** Look at similar implementations
3. **Read Documentation:** Check external library docs
4. **Ask Team:** Reach out to other engineers

---

## 🎉 You're Ready!

You should now have a solid understanding of the project. Here's a quick checklist:

- [ ] Environment variables configured
- [ ] Dependencies installed
- [ ] Dev server running successfully
- [ ] Database connection working
- [ ] Familiar with project structure
- [ ] Understand data flow
- [ ] Know where to find components/hooks
- [ ] Understand API endpoints
- [ ] Can run database migrations
- [ ] Know debugging approaches

Welcome aboard! 🚀
