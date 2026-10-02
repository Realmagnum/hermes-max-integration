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
  STATUSBAR_AREAS,
  atom,
  compactNumber,
  host,
  useValue
} from '@hermes/plugin-sdk'
import { useEffect, useMemo, useState } from 'react'
import { Fragment, jsx, jsxs } from 'react/jsx-runtime'

const PLUGIN_ID = 'max-sessions-sidebar'
const PLUGIN_NAME = 'MAX Messenger Sessions'
const PLUGIN_ROUTE = '/max-sessions'

let pluginStorage = null
const statusbarVisible = atom(true)

function stored(key, fallback) {
  return pluginStorage ? pluginStorage.get(key, fallback) : fallback
}

function saveSetting(key, value) {
  if (pluginStorage) pluginStorage.set(key, value)
}

function toggleStatusbar() {
  const next = !statusbarVisible.get()
  statusbarVisible.set(next)
  saveSetting('showStatusbar', next)
  if (host.notify) {
    host.notify({
      kind: 'info',
      title: 'MAX Sessions',
      message: next ? 'Иконка MAX включена в статусбаре' : 'Иконка MAX отключена в статусбаре'
    })
  }
}

function MaxStatusbarChip() {
  const visible = useValue(statusbarVisible)
  if (!visible) return null

  return jsxs('button', {
    type: 'button',
    title: 'Открыть сессии MAX',
    onClick: () => host.navigate(PLUGIN_ROUTE),
    style: {
      display: 'inline-flex',
      alignItems: 'center',
      gap: 5,
      height: '100%',
      padding: '0 8px',
      border: 0,
      background: 'transparent',
      color: 'var(--ui-text-secondary)',
      font: 'inherit',
      fontSize: '0.6875rem',
      cursor: 'pointer'
    },
    children: [
      jsx('img', {
        src: 'data:image/png;base64,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',
        alt: '',
        width: 16,
        height: 16,
        draggable: false,
        style: {
          display: 'block',
          width: 16,
          height: 16,
          borderRadius: 4,
          objectFit: 'cover'
        }
      }),
      jsx('span', { children: 'MAX' })
    ]
  })
}

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
  pluginStorage = ctx.storage || null
  statusbarVisible.set(!!stored('showStatusbar', true))

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

  ctx.register({
    id: 'toggle-statusbar',
    area: PALETTE_AREA,
    data: {
      id: `${PLUGIN_ID}.toggleStatusbar`,
      label: 'MAX: Toggle Statusbar Icon',
      keywords: ['max', 'statusbar', 'icon', 'sessions', 'макс', 'статусбар', 'значок'],
      run: toggleStatusbar
    }
  })

  if (STATUSBAR_AREAS && STATUSBAR_AREAS.right) {
    ctx.register({
      id: 'statusbar',
      area: STATUSBAR_AREAS.right,
      order: 135,
      render: () => jsx(MaxStatusbarChip, {})
    })
  }
}

export default {
  id: PLUGIN_ID,
  name: PLUGIN_NAME,
  version: '1.1.0',
  description: 'Native Hermes-styled view and navigation for MAX messenger sessions',
  register
}
