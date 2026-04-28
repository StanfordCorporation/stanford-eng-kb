// Shared constants for the frontend.
//
// API_BASE: empty in dev (Vite proxies /api/* to the local backend); in
// single-Vercel deploys it's also empty (same-origin). Only set VITE_API_URL
// when the backend lives on a different domain.
export const API_BASE = import.meta.env.VITE_API_URL ?? ''

// ─── Auth API helpers ──────────────────────────────────────────────────────
// All auth state lives in an HTTP-only cookie set by the backend. The SPA
// just calls these and reacts to 200 / 401.

export async function checkAuth(): Promise<boolean> {
  const res = await fetch(`${API_BASE}/api/auth/me`, { credentials: 'include' })
  return res.ok
}

export async function login(password: string): Promise<{ ok: true } | { ok: false; message: string }> {
  const res = await fetch(`${API_BASE}/api/auth/login`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify({ password }),
  })
  if (res.ok) return { ok: true }
  let message = `HTTP ${res.status}`
  try {
    const data = await res.json()
    if (data?.detail) message = data.detail
  } catch {
    /* ignore */
  }
  return { ok: false, message }
}

export async function logout(): Promise<void> {
  await fetch(`${API_BASE}/api/auth/logout`, { method: 'POST', credentials: 'include' })
}

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
