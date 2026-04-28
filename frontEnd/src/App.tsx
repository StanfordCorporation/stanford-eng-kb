import { useEffect, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import AddToKB from './AddToKB'
import { API_BASE, ORGS } from './lib'
import './App.css'

type Source = { n: number; source: string; score: number }
type Stage = 'thinking' | 'rewriting' | 'searching'

type Turn =
  | { role: 'user'; content: string }
  | {
      role: 'assistant'
      content: string
      sources: Source[]
      rewrittenQuery?: string | null
      phase: 'retrieving' | 'streaming' | 'done' | 'error'
      stage?: Stage
      startedAt?: number
      error?: string
    }

type Thread = {
  id: string
  title: string
  turns: Turn[]
  updatedAt: number
}

type StreamEvent =
  | { type: 'status'; stage: Stage }
  | { type: 'sources'; sources: Source[]; rewritten_query?: string | null }
  | { type: 'delta'; text: string }
  | { type: 'done' }
  | { type: 'error'; message: string }

const STORAGE_KEY = 'stanford-kb-threads-v1'
const THEME_KEY = 'stanford-kb-theme'
const ACTIVE_ORG_KEY = 'stanford-kb-active-org'
const ACTIVE_SUB_KEY = 'stanford-kb-active-sub'

type Theme = 'light' | 'dark'
type View = 'chat' | 'add-kb'

function initialActiveOrg(): string {
  const saved = localStorage.getItem(ACTIVE_ORG_KEY)
  if (saved && ORGS.some((o) => o.id === saved)) return saved
  return ORGS[0].id
}

function initialActiveSub(orgId: string): string | null {
  const saved = localStorage.getItem(ACTIVE_SUB_KEY)
  const org = ORGS.find((o) => o.id === orgId)
  if (saved && org?.subs.some((s) => s.id === saved)) return saved
  return null
}

function initialTheme(): Theme {
  const saved = localStorage.getItem(THEME_KEY) as Theme | null
  if (saved === 'light' || saved === 'dark') return saved
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

function newThreadId() {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

function blankThread(): Thread {
  return { id: newThreadId(), title: 'New chat', turns: [], updatedAt: Date.now() }
}

function loadThreads(): Thread[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw) as Thread[]
    // Reset any in-flight assistant turns — a stream that was mid-flight on refresh is lost.
    return parsed.map((t) => ({
      ...t,
      turns: t.turns.map((tn) =>
        tn.role === 'assistant' && (tn.phase === 'retrieving' || tn.phase === 'streaming')
          ? { ...tn, phase: 'error', error: 'Interrupted' }
          : tn,
      ),
    }))
  } catch {
    return []
  }
}

// Human-readable label for the in-flight assistant turn before any tokens stream.
// `stage` comes from the backend's status SSE event; `startedAt` is the local
// timestamp set when the turn was created. The "(Ns)" tail is appended after
// 3 seconds so quick chats don't show a counter for normal latency.
function retrievingLabel(stage: Stage | undefined, startedAt: number | undefined): string {
  const base =
    stage === 'searching'
      ? 'Searching the knowledge base'
      : stage === 'rewriting'
      ? 'Understanding your question'
      : 'Thinking'
  if (!startedAt) return `${base}…`
  const secs = Math.floor((Date.now() - startedAt) / 1000)
  if (secs < 3) return `${base}…`
  if (secs < 20) return `${base}… (${secs}s)`
  return `${base}… (${secs}s — taking longer than usual)`
}

function deriveTitle(turns: Turn[]): string {
  const first = turns.find((t) => t.role === 'user')
  if (!first) return 'New chat'
  const text = first.content.trim().replace(/\s+/g, ' ')
  return text.length > 40 ? text.slice(0, 40) + '…' : text
}

export default function App() {
  const [query, setQuery] = useState('')
  const [threads, setThreads] = useState<Thread[]>(() => {
    const loaded = loadThreads()
    return loaded.length ? loaded : [blankThread()]
  })
  const [activeId, setActiveId] = useState<string>(() => threads[0]?.id ?? '')
  const [theme, setTheme] = useState<Theme>(() => initialTheme())
  const [view, setView] = useState<View>('chat')
  const [activeOrg, setActiveOrg] = useState<string>(() => initialActiveOrg())
  const [activeSub, setActiveSub] = useState<string | null>(() => initialActiveSub(initialActiveOrg()))
  const threadRef = useRef<HTMLDivElement>(null)
  const stickToBottomRef = useRef(true)
  const abortRef = useRef<AbortController | null>(null)
  // Tick once a second while a turn is in flight so the elapsed-time label updates.
  const [, forceTick] = useState(0)

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    localStorage.setItem(THEME_KEY, theme)
  }, [theme])

  useEffect(() => {
    localStorage.setItem(ACTIVE_ORG_KEY, activeOrg)
  }, [activeOrg])

  useEffect(() => {
    if (activeSub) localStorage.setItem(ACTIVE_SUB_KEY, activeSub)
    else localStorage.removeItem(ACTIVE_SUB_KEY)
  }, [activeSub])

  const activeOrgObj = ORGS.find((o) => o.id === activeOrg) ?? ORGS[0]

  const active = threads.find((t) => t.id === activeId) ?? threads[0]
  const turns = active?.turns ?? []
  const lastTurn = turns[turns.length - 1]
  const busy =
    lastTurn?.role === 'assistant' &&
    (lastTurn.phase === 'retrieving' || lastTurn.phase === 'streaming')

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(threads))
  }, [threads])

  // While a turn is in flight, re-render once a second so the "(Ns)" elapsed
  // label keeps moving. Cheap; the rest of the tree memos away.
  useEffect(() => {
    if (!busy) return
    const id = setInterval(() => forceTick((n) => n + 1), 1000)
    return () => clearInterval(id)
  }, [busy])

  useEffect(() => {
    const el = threadRef.current
    if (!el || !stickToBottomRef.current) return
    el.scrollTop = el.scrollHeight
  }, [turns])

  function onThreadScroll() {
    const el = threadRef.current
    if (!el) return
    const distanceFromBottom = el.scrollHeight - el.clientHeight - el.scrollTop
    stickToBottomRef.current = distanceFromBottom < 80
  }

  function updateActive(updater: (turns: Turn[]) => Turn[]) {
    setThreads((prev) =>
      prev.map((t) =>
        t.id === activeId
          ? { ...t, turns: updater(t.turns), updatedAt: Date.now(), title: deriveTitle(updater(t.turns)) }
          : t,
      ),
    )
  }

  function updateAssistant(updater: (t: Turn & { role: 'assistant' }) => Turn) {
    updateActive((prev) => {
      const next = [...prev]
      const i = next.length - 1
      if (i >= 0 && next[i].role === 'assistant') {
        next[i] = updater(next[i] as Turn & { role: 'assistant' })
      }
      return next
    })
  }

  function startNewThread() {
    if (busy) return
    setView('chat')
    const existingEmpty = threads.find((t) => t.turns.length === 0)
    if (existingEmpty) {
      setActiveId(existingEmpty.id)
      return
    }
    const t = blankThread()
    setThreads((prev) => [t, ...prev])
    setActiveId(t.id)
    setQuery('')
    stickToBottomRef.current = true
  }

  function deleteThread(id: string) {
    setThreads((prev) => {
      const remaining = prev.filter((t) => t.id !== id)
      if (remaining.length === 0) {
        const fresh = blankThread()
        setActiveId(fresh.id)
        return [fresh]
      }
      if (id === activeId) setActiveId(remaining[0].id)
      return remaining
    })
  }

  async function submit() {
    const q = query.trim()
    if (!q || busy || !active) return

    const history = active.turns
      .filter((t) => t.role === 'user' || (t.role === 'assistant' && t.phase === 'done'))
      .map((t) => ({ role: t.role, content: t.content }))

    const newMessages = [...history, { role: 'user' as const, content: q }]

    updateActive((prev) => [
      ...prev,
      { role: 'user', content: q },
      {
        role: 'assistant',
        content: '',
        sources: [],
        phase: 'retrieving',
        stage: 'thinking',
        startedAt: Date.now(),
      },
    ])
    setQuery('')
    stickToBottomRef.current = true

    const ac = new AbortController()
    abortRef.current = ac

    try {
      const res = await fetch(`${API_BASE}/api/chat/stream`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({
          messages: newMessages,
          k: 5,
          org_id: activeOrg,
          sub_id: activeSub,
        }),
        signal: ac.signal,
      })
      if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`)

      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let acc = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })

        let sep: number
        while ((sep = buffer.indexOf('\n\n')) !== -1) {
          const frame = buffer.slice(0, sep)
          buffer = buffer.slice(sep + 2)
          if (!frame.startsWith('data: ')) continue

          const event: StreamEvent = JSON.parse(frame.slice(6))
          if (event.type === 'status') {
            updateAssistant((t) => ({ ...t, stage: event.stage }))
          } else if (event.type === 'sources') {
            updateAssistant((t) => ({
              ...t,
              sources: event.sources,
              rewrittenQuery: event.rewritten_query ?? null,
              phase: 'streaming',
              stage: undefined,
            }))
          } else if (event.type === 'delta') {
            acc += event.text
            updateAssistant((t) => ({ ...t, content: acc }))
          } else if (event.type === 'done') {
            updateAssistant((t) => ({ ...t, phase: 'done' }))
          } else if (event.type === 'error') {
            updateAssistant((t) => ({ ...t, phase: 'error', error: event.message }))
          }
        }
      }
    } catch (err) {
      // User-initiated abort: end the turn cleanly without surfacing as an error.
      if (err instanceof DOMException && err.name === 'AbortError') {
        updateAssistant((t) => ({
          ...t,
          phase: t.content ? 'done' : 'error',
          error: t.content ? undefined : 'Stopped',
        }))
      } else {
        updateAssistant((t) => ({
          ...t,
          phase: 'error',
          error: err instanceof Error ? err.message : String(err),
        }))
      }
    } finally {
      abortRef.current = null
    }
  }

  function stopGeneration() {
    abortRef.current?.abort()
  }

  const sortedThreads = [...threads].sort((a, b) => b.updatedAt - a.updatedAt)

  return (
    <div className="layout">
      <aside className="sidebar">
        <div className="sidebar-header">
          <button className="new-chat" onClick={startNewThread} disabled={busy}>
            + New chat
          </button>
          <button
            className={`add-kb-btn ${view === 'add-kb' ? 'active' : ''}`}
            onClick={() => setView('add-kb')}
          >
            + Add to KB
          </button>

          <div className="org-selector">
            <label className="org-selector-label">Active KB</label>
            <select
              className="org-selector-input"
              value={activeOrg}
              onChange={(e) => {
                setActiveOrg(e.target.value)
                setActiveSub(null)
              }}
            >
              {ORGS.map((o) => (
                <option key={o.id} value={o.id}>
                  {o.name}
                </option>
              ))}
            </select>
            {activeOrgObj.subs.length > 0 && (
              <select
                className="org-selector-input"
                value={activeSub ?? ''}
                onChange={(e) => setActiveSub(e.target.value || null)}
              >
                <option value="">All groups</option>
                {activeOrgObj.subs.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name}
                  </option>
                ))}
              </select>
            )}
          </div>
        </div>
        <nav className="thread-list">
          {sortedThreads.map((t) => (
            <div
              key={t.id}
              className={`thread-item ${view === 'chat' && t.id === activeId ? 'active' : ''}`}
              onClick={() => {
                setView('chat')
                setActiveId(t.id)
              }}
            >
              <span className="thread-title">{t.title}</span>
              <button
                className="thread-delete"
                onClick={(e) => {
                  e.stopPropagation()
                  deleteThread(t.id)
                }}
                aria-label="Delete chat"
                title="Delete chat"
              >
                ×
              </button>
            </div>
          ))}
        </nav>
      </aside>

      <main className={`app ${view === 'add-kb' ? 'add-kb' : ''}`}>
        <header>
          <h1>{view === 'add-kb' ? 'Add to Knowledge Base' : 'Stanford Knowledge Base'}</h1>
          <button
            className="theme-toggle"
            onClick={() => setTheme(theme === 'light' ? 'dark' : 'light')}
            aria-label={`Switch to ${theme === 'light' ? 'dark' : 'light'} mode`}
            title={`Switch to ${theme === 'light' ? 'dark' : 'light'} mode`}
          >
            {theme === 'light' ? (
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
              </svg>
            ) : (
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="4" />
                <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41" />
              </svg>
            )}
          </button>
        </header>

        {view === 'add-kb' ? (
          <AddToKB />
        ) : (
        <>
        <div ref={threadRef} className="thread" onScroll={onThreadScroll}>
          {turns.length === 0 && (
            <div className="hint">
              Ask something about your vault. Follow-up questions see prior turns.
            </div>
          )}

          {turns.map((t, i) =>
            t.role === 'user' ? (
              <div key={i} className="turn user">
                <div className="bubble">{t.content}</div>
              </div>
            ) : (
              <div key={i} className="turn assistant">
                <div className={`label ${t.phase === 'retrieving' ? 'pulsing' : ''}`}>
                  {t.phase === 'retrieving' && retrievingLabel(t.stage, t.startedAt)}
                  {t.phase === 'streaming' && 'Claude'}
                  {t.phase === 'done' && 'Claude'}
                  {t.phase === 'error' && 'Error'}
                </div>

                {t.phase === 'error' ? (
                  <div className="error">{t.error}</div>
                ) : (
                  <div className="md">
                    <ReactMarkdown>{t.content}</ReactMarkdown>
                    {t.phase === 'streaming' && <span className="caret" />}
                  </div>
                )}
              </div>
            )
          )}
        </div>

        <form
          className="composer"
          onSubmit={(e) => {
            e.preventDefault()
            submit()
          }}
        >
          <textarea
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={
              turns.length === 0 ? 'Ask something…' : 'Follow up… (⌘/Ctrl + Enter to send)'
            }
            rows={2}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
                e.preventDefault()
                submit()
              }
            }}
          />
          {busy ? (
            <button
              type="button"
              className="stop-btn"
              onClick={stopGeneration}
              title="Stop generating"
            >
              Stop
            </button>
          ) : (
            <button type="submit" disabled={!query.trim()}>
              Send
            </button>
          )}
        </form>
        </>
        )}
      </main>
    </div>
  )
}
