// Shared constants for the frontend.
//
// API_BASE: empty in dev (Vite proxies /api/* to the local backend); in prod,
// set VITE_API_URL on Vercel to the Railway backend URL (no trailing slash).
export const API_BASE = import.meta.env.VITE_API_URL ?? ''

// Bearer token sent with /api/ingest/upload calls. The Railway backend rejects
// requests without it. NOTE: this is bundled into the SPA, so anyone who can
// load the page can read it. That's acceptable behind Vercel password
// protection for soft launch; replace with a server-side proxy when you add
// real per-user auth.
export const INGEST_TOKEN = import.meta.env.VITE_INGEST_TOKEN ?? ''

export type SubGroup = { id: string; name: string }
export type Org = {
  id: string
  name: string
  description: string
  subs: SubGroup[]
}

// Single source of truth for the org/sub-group taxonomy. Used by the
// "Add to KB" flow and the chat sidebar's active-org selector.
export const ORGS: Org[] = [
  {
    id: 'stanford-legal',
    name: 'Stanford Legal',
    description: 'Legal practice covering property, family, and estate matters.',
    subs: [
      { id: 'property-law', name: 'Property Law Firm' },
      { id: 'family-law', name: 'Family Law' },
      { id: 'wills-estate', name: 'Wills & Estate Law' },
    ],
  },
  {
    id: 'stanford-finance',
    name: 'Stanford Finance',
    description: 'Financial services across mortgage and broking.',
    subs: [{ id: 'mortgage-broking', name: 'Mortgage & Broking Firm' }],
  },
  {
    id: 'stanford-innovations',
    name: 'Stanford Innovations',
    description: 'Internal R&D — technology and marketing.',
    subs: [
      { id: 'technology', name: 'Technology' },
      { id: 'marketing', name: 'Marketing' },
    ],
  },
]
