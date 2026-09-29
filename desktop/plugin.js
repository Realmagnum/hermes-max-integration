import {
  Badge,
  Button,
  Codicon,
  EmptyState,
  GlyphSpinner,
  Input,
  PALETTE_AREA,
  ROUTES_AREA,
  ScrollArea,
  SearchField,
  Separator,
  SIDEBAR_NAV_AREA,
  host
} from '@hermes/plugin-sdk'
import { useEffect, useMemo, useState } from 'react'
import { Fragment, jsx, jsxs } from 'react/jsx-runtime'

const PLUGIN_ID = 'max-sessions'
const PLUGIN_NAME = 'MAX Messenger Sessions'
const PLUGIN_ROUTE = '/max-sessions'

function formatTimestamp(ts) {
  if (!ts) return ''
  try {
    const d = new Date(typeof ts === 'number' && ts < 1e12 ? ts * 1000 : ts)
    return d.toLocaleString()
  } catch {
    return String(ts)
  }
}

function MaxSessionsView({ ctx }) {
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(false)
  const [sessions, setSessions] = useState([])
  const [error, setError] = useState(null)

  const fetchSessions = async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await host.request('session.list', { limit: 300 })
      const all = Array.isArray(res?.sessions) ? res.sessions : []
      const maxList = all.filter(s => s && (s.source === 'max' || s.origin_platform === 'max'))
      setSessions(maxList)
    } catch (err) {
      console.error('[max-sessions] fetch error:', err)
      setError(err?.message || 'Failed to fetch sessions')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchSessions()
    const unsub = host.onEvent ? host.onEvent('sessions.updated', () => fetchSessions()) : null
    return () => {
      if (typeof unsub === 'function') unsub()
    }
  }, [])

  const filtered = useMemo(() => {
    if (!search.trim()) return sessions
    const q = search.toLowerCase()
    return sessions.filter(s => {
      const title = (s.title || s.id || '').toLowerCase()
      const snippet = (s.snippet || '').toLowerCase()
      return title.includes(q) || snippet.includes(q)
    })
  }, [sessions, search])

  const handleOpenSession = async (sessionId) => {
    try {
      await host.openSession(sessionId)
    } catch (e) {
      console.error('[max-sessions] open error:', e)
      if (host.notify) {
        host.notify({
          kind: 'error',
          title: 'MAX Sessions',
          message: 'Could not open session: ' + (e?.message || String(e))
        })
      }
    }
  }

  return jsxs('div', {
    className: 'flex h-full w-full flex-col bg-(--ui-background) text-foreground p-6 overflow-hidden',
    children: [
      // Header
      jsxs('div', {
        className: 'flex items-center justify-between pb-4 border-b border-(--ui-border)',
        children: [
          jsxs('div', {
            className: 'flex items-center gap-3',
            children: [
              jsx(Codicon, { name: 'comment-discussion', className: 'text-2xl text-(--ui-accent)' }),
              jsxs('div', {
                children: [
                  jsxs('h1', {
                    className: 'text-xl font-semibold flex items-center gap-2',
                    children: [
                      'MAX Messenger Sessions',
                      jsx(Badge, { variant: 'secondary', children: String(sessions.length) })
                    ]
                  }),
                  jsx('p', {
                    className: 'text-xs text-(--ui-text-tertiary)',
                    children: 'Диалоги и групповые чаты из мессенджера MAX (max.ru)'
                  })
                ]
              })
            ]
          }),
          jsxs('div', {
            className: 'flex items-center gap-2',
            children: [
              jsx(Button, {
                variant: 'outline',
                size: 'sm',
                disabled: loading,
                onClick: fetchSessions,
                children: jsxs('span', {
                  className: 'flex items-center gap-1.5',
                  children: [
                    loading ? jsx(GlyphSpinner, {}) : jsx(Codicon, { name: 'refresh' }),
                    'Обновить'
                  ]
                })
              })
            ]
          })
        ]
      }),

      // Filter bar
      jsx('div', {
        className: 'py-4',
        children: jsx(Input, {
          placeholder: 'Поиск по заголовку или сниппету...',
          value: search,
          onChange: e => setSearch(e.target.value)
        })
      }),

      // Main content list
      jsx('div', {
        className: 'flex-1 overflow-y-auto',
        children: error
          ? jsx('div', {
              className: 'p-4 text-sm text-(--ui-destructive) bg-(--ui-destructive-background) rounded',
              children: `Ошибка загрузки: ${error}`
            })
          : filtered.length === 0
          ? jsx(EmptyState, {
              title: loading ? 'Загрузка...' : 'Сессии MAX не найдены',
              description: search ? 'Попробуйте изменить поисковый запрос' : 'Пока нет завершённых или активных сессий от пользователей MAX'
            })
          : jsx('div', {
              className: 'space-y-2 pr-2',
              children: filtered.map(s => {
                const title = s.title || `Сессия ${s.id.slice(0, 8)}...`
                const timeStr = formatTimestamp(s.last_activity_at || s.started_at)
                return jsxs('div', {
                  key: s.id,
                  onClick: () => handleOpenSession(s.id),
                  className: 'group flex flex-col gap-1 p-3.5 rounded-lg border border-(--ui-border) hover:border-(--ui-accent) hover:bg-(--ui-surface-hover) cursor-pointer transition-all',
                  children: [
                    jsxs('div', {
                      className: 'flex items-center justify-between',
                      children: [
                        jsxs('span', {
                          className: 'font-medium text-sm text-foreground group-hover:text-(--ui-accent) flex items-center gap-2',
                          children: [
                            jsx(Codicon, { name: 'comment', className: 'text-(--ui-text-tertiary)' }),
                            title
                          ]
                        }),
                        jsxs('div', {
                          className: 'flex items-center gap-2 text-xs text-(--ui-text-tertiary)',
                          children: [
                            s.message_count ? jsx(Badge, { variant: 'outline', children: `${s.message_count} сообщ.` }) : null,
                            jsx('span', { children: timeStr })
                          ]
                        })
                      ]
                    }),
                    s.snippet ? jsx('p', {
                      className: 'text-xs text-(--ui-text-secondary) line-clamp-2 mt-0.5',
                      children: s.snippet
                    }) : null,
                    jsxs('div', {
                      className: 'flex items-center gap-2 mt-1 text-[11px] text-(--ui-text-tertiary) font-mono',
                      children: [
                        jsx('span', { children: `ID: ${s.id}` }),
                        s.profile ? jsx('span', { children: `• профиль: ${s.profile}` }) : null
                      ]
                    })
                  ]
                })
              })
            })
      })
    ]
  })
}

function register(ctx) {
  // 1. Страница
  ctx.register({
    id: 'page',
    area: ROUTES_AREA,
    data: { path: PLUGIN_ROUTE },
    render: () => jsx(MaxSessionsView, { ctx })
  })

  // 2. Иконка в сайдбаре
  ctx.register({
    id: 'nav',
    area: SIDEBAR_NAV_AREA,
    order: 35,
    data: {
      path: PLUGIN_ROUTE,
      label: 'MAX',
      codicon: 'comment-discussion'
    }
  })

  // 3. Command Palette
  ctx.register({
    id: 'open',
    area: PALETTE_AREA,
    data: {
      id: `${PLUGIN_ID}.open`,
      label: 'MAX: Open Sessions List',
      keywords: ['max', 'messenger', 'sessions', 'chat', 'макс', 'сообщения'],
      run: () => host.navigate(PLUGIN_ROUTE)
    }
  })
}

export default {
  id: PLUGIN_ID,
  name: PLUGIN_NAME,
  version: '1.0.0',
  description: 'Direct view and navigation for MAX messenger sessions',
  register
}
