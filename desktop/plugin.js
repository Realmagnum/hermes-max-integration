import {
  Badge,
  Button,
  Codicon,
  EmptyState,
  GlyphSpinner,
  Input,
  PALETTE_AREA,
  ROUTES_AREA,
  SIDEBAR_NAV_AREA,
  compactNumber,
  host
} from '@hermes/plugin-sdk'
import { useEffect, useMemo, useState } from 'react'
import { Fragment, jsx, jsxs } from 'react/jsx-runtime'

const PLUGIN_ID = 'max-sessions'
const PLUGIN_NAME = 'MAX Messenger Sessions'
const PLUGIN_ROUTE = '/max-sessions'

// Форматирование даты и времени с фиксированной шириной и строгим выравниванием
const dateFormatter = new Intl.DateTimeFormat('ru-RU', {
  day: '2-digit',
  month: 'short',
  year: 'numeric'
})

const timeFormatter = new Intl.DateTimeFormat('ru-RU', {
  hour: '2-digit',
  minute: '2-digit'
})

function formatDateTimeParts(ts) {
  if (!ts) return { date: '—', time: '' }
  try {
    const raw = typeof ts === 'number' && ts < 1e12 ? ts * 1000 : Number(ts)
    const d = new Date(raw)
    if (Number.isNaN(d.getTime())) return { date: '—', time: '' }
    return {
      date: dateFormatter.format(d),
      time: timeFormatter.format(d)
    }
  } catch {
    return { date: String(ts), time: '' }
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
      const title = (s.title || '').toLowerCase()
      const snippet = (s.snippet || s.preview || '').toLowerCase()
      return title.includes(q) || snippet.includes(q)
    })
  }, [sessions, search])

  const totalTokensAll = useMemo(() => {
    return sessions.reduce((acc, s) => {
      return acc + (s.input_tokens || 0) + (s.output_tokens || 0)
    }, 0)
  }, [sessions])

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
    className: 'flex h-full w-full flex-col bg-background text-foreground select-none overflow-hidden',
    children: [
      // Top Header Bar в нативном стиле Hermes
      jsxs('div', {
        className: 'flex shrink-0 items-center justify-between border-b border-border px-6 py-4 bg-card/40 backdrop-blur-sm',
        children: [
          jsxs('div', {
            className: 'flex items-center gap-3',
            children: [
              jsx('div', {
                className: 'flex size-9 items-center justify-center rounded-lg bg-primary/10 text-primary border border-primary/20',
                children: jsx(Codicon, { name: 'comment-discussion', className: 'text-lg' })
              }),
              jsxs('div', {
                className: 'flex flex-col',
                children: [
                  jsxs('div', {
                    className: 'flex items-center gap-2',
                    children: [
                      jsx('h1', {
                        className: 'text-base font-semibold tracking-tight text-foreground',
                        children: 'Сессии MAX'
                      }),
                      jsx(Badge, {
                        variant: 'secondary',
                        className: 'font-mono text-xs px-2 py-0.5 rounded-full',
                        children: String(sessions.length)
                      }),
                      totalTokensAll > 0 ? jsx(Badge, {
                        variant: 'outline',
                        className: 'font-mono text-xs px-2 py-0.5 text-muted-foreground border-border/80',
                        children: `${compactNumber(totalTokensAll)} tok`
                      }) : null
                    ]
                  }),
                  jsx('span', {
                    className: 'text-xs text-muted-foreground',
                    children: 'Диалоги и групповые чаты мессенджера MAX (max.ru)'
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
                className: 'h-8 px-3 text-xs gap-1.5 shadow-none border-border hover:bg-muted/60',
                children: jsxs('span', {
                  className: 'flex items-center gap-1.5',
                  children: [
                    loading ? jsx(GlyphSpinner, { className: 'size-3.5' }) : jsx(Codicon, { name: 'refresh', className: 'text-xs' }),
                    'Обновить'
                  ]
                })
              })
            ]
          })
        ]
      }),

      // Filter Toolbar
      jsx('div', {
        className: 'shrink-0 px-6 py-3 border-b border-border/60 bg-background/50',
        children: jsx('div', {
          className: 'relative max-w-md',
          children: jsxs('div', {
            className: 'relative flex items-center',
            children: [
              jsx(Codicon, {
                name: 'search',
                className: 'absolute left-2.5 text-muted-foreground/60 text-sm pointer-events-none'
              }),
              jsx(Input, {
                placeholder: 'Поиск по теме или сообщению...',
                value: search,
                onChange: e => setSearch(e.target.value),
                className: 'h-8 pl-8 pr-3 text-xs bg-muted/30 border-border/80 focus-visible:ring-1 focus-visible:ring-primary rounded-md'
              })
            ]
          })
        })
      }),

      // Sessions List
      jsx('div', {
        className: 'flex-1 overflow-y-auto px-6 py-3',
        children: error
          ? jsx('div', {
              className: 'p-4 text-xs text-destructive bg-destructive/10 border border-destructive/20 rounded-md',
              children: `Ошибка загрузки: ${error}`
            })
          : filtered.length === 0
          ? jsx(EmptyState, {
              title: loading ? 'Загрузка диалогов...' : 'Сессии MAX не найдены',
              description: search ? 'Попробуйте изменить поисковый запрос' : 'Пока нет завершённых или активных сессий от пользователей MAX'
            })
          : jsx('div', {
              className: 'divide-y divide-border/40 border border-border/60 rounded-lg overflow-hidden bg-card/20 shadow-xs',
              children: filtered.map(s => {
                const title = s.title?.trim() || 'Без названия'
                const timestamp = s.last_active || s.last_activity_at || s.started_at
                const { date, time } = formatDateTimeParts(timestamp)
                const totalTokens = (s.input_tokens || 0) + (s.output_tokens || 0)
                const snippet = s.snippet || s.preview || null

                return jsxs('div', {
                  key: s.id,
                  onClick: () => handleOpenSession(s.id),
                  className: 'group flex items-center justify-between gap-4 px-4 py-3 hover:bg-muted/40 cursor-pointer transition-colors',
                  children: [
                    // Left: Icon + Title + Snippet + Profile
                    jsxs('div', {
                      className: 'flex items-start gap-3 min-w-0 flex-1',
                      children: [
                        jsx('div', {
                          className: 'mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-md bg-muted/60 text-muted-foreground group-hover:bg-primary/10 group-hover:text-primary transition-colors',
                          children: jsx(Codicon, { name: 'comment', className: 'text-sm' })
                        }),
                        jsxs('div', {
                          className: 'flex flex-col min-w-0 flex-1 gap-1',
                          children: [
                            jsxs('div', {
                              className: 'flex items-center gap-2 min-w-0',
                              children: [
                                jsx('span', {
                                  className: 'font-medium text-xs text-foreground group-hover:text-primary truncate transition-colors',
                                  children: title
                                }),
                                s.profile && s.profile !== 'default' ? jsx(Badge, {
                                  variant: 'outline',
                                  className: 'text-[10px] px-1.5 py-0 h-4 font-normal text-muted-foreground',
                                  children: s.profile
                                }) : null
                              ]
                            }),
                            snippet ? jsx('p', {
                              className: 'text-[11px] text-muted-foreground/80 line-clamp-1 break-all leading-relaxed',
                              children: snippet
                            }) : null
                          ]
                        })
                      ]
                    }),

                    // Right: Metrics (Tokens, Messages, DateTime) with fixed alignment
                    jsxs('div', {
                      className: 'flex shrink-0 items-center gap-6 text-right tabular-nums',
                      children: [
                        // Tokens & Messages pill group
                        jsxs('div', {
                          className: 'flex items-center gap-2',
                          children: [
                            totalTokens > 0 ? jsxs('div', {
                              className: 'flex items-center gap-1 text-[11px] text-muted-foreground/90 font-mono bg-muted/40 px-2 py-0.5 rounded border border-border/40',
                              title: `Вход: ${s.input_tokens || 0}, Выход: ${s.output_tokens || 0}`,
                              children: [
                                jsx(Codicon, { name: 'symbol-numeric', className: 'text-[10px] text-muted-foreground/60' }),
                                `${compactNumber(totalTokens)} tok`
                              ]
                            }) : null,
                            s.message_count ? jsxs('div', {
                              className: 'flex items-center gap-1 text-[11px] text-muted-foreground/70 font-mono px-1.5 py-0.5',
                              title: 'Количество сообщений',
                              children: [
                                jsx(Codicon, { name: 'mail', className: 'text-[10px] text-muted-foreground/50' }),
                                `${s.message_count} сообщ.`
                              ]
                            }) : null
                          ]
                        }),

                        // Date & Time block with fixed width and clean layout
                        jsxs('div', {
                          className: 'flex flex-col items-end justify-center w-24 text-[11px] leading-tight',
                          children: [
                            jsx('span', {
                              className: 'font-medium text-foreground/80 whitespace-nowrap',
                              children: date
                            }),
                            time ? jsx('span', {
                              className: 'text-[10px] text-muted-foreground/60 font-mono mt-0.5 whitespace-nowrap',
                              children: time
                            }) : null
                          ]
                        }),

                        // Arrow action icon
                        jsx(Codicon, {
                          name: 'chevron-right',
                          className: 'text-muted-foreground/30 text-xs transition-transform group-hover:translate-x-0.5 group-hover:text-foreground/80'
                        })
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
  ctx.register({
    id: 'page',
    area: ROUTES_AREA,
    data: { path: PLUGIN_ROUTE },
    render: () => jsx(MaxSessionsView, { ctx })
  })

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
  version: '1.1.0',
  description: 'Native Hermes-styled view and navigation for MAX messenger sessions',
  register
}
