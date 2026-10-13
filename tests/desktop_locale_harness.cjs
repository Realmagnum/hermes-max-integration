// MS-006 behavior harness: execute the shipped standalone entry, not a duplicate
// view model. SDK/React seams are faked to inspect contribution trees and actions;
// this does not claim a rendered browser or real React subscription smoke test.
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')

const source = fs.readFileSync(process.argv[2] || path.join(__dirname, '../desktop/plugin.js'), 'utf8')
  .replace(/import [\s\S]*? from '[^']+'\r?\n/g, '')
  .replace('export default {', 'globalThis.plugin = {')

function harness(initialLocale, hasLocaleSubscription = true) {
  let locale = initialLocale
  let bundles
  let state = []
  let cursor = 0
  let response = { sessions: [] }
  const notifications = []
  const contributions = new Map()
  const listeners = []
  const effects = []
  const translate = (key, ...args) => {
    const entry = bundles[locale]?.[key] ?? bundles.en[key]
    return typeof entry === 'function' ? entry(...args) : entry
  }
  const element = (type, props) => ({ type, props })
  const atom = value => ({ get: () => value, set: next => { value = next } })
  const context = {
    Intl, Date, Number, console: { error: () => {} },
    Badge: 'Badge', Button: 'Button', Codicon: 'Codicon',
    EmptyState: 'EmptyState', GlyphSpinner: 'GlyphSpinner', Input: 'Input',
    PALETTE_AREA: 'palette', ROUTES_AREA: 'routes', SIDEBAR_NAV_AREA: 'nav',
    STATUSBAR_AREAS: { right: 'statusbar' }, atom,
    compactNumber: String,
    host: {
      request: async () => response instanceof Error ? Promise.reject(response) : response,
      notify: n => notifications.push(n), navigate: () => {},
      onEvent: () => () => {},
      openSession: async () => { throw new Error('session unavailable') }
    },
    useI18n: () => ({ locale }),
    usePluginI18n: id => {
      assert.equal(id, 'max-sessions-sidebar')
      return translate
    },
    useValue: atom => atom.get(),
    useEffect: fn => effects.push(fn),
    useMemo: fn => fn(),
    useState: initial => {
      const slot = cursor++
      if (!(slot in state)) state[slot] = initial
      return [state[slot], value => { state[slot] = value }]
    },
    jsx: element, jsxs: element
  }
  vm.createContext(context)
  vm.runInContext(source, context, { filename: 'desktop/plugin.js' })
  context.plugin.register({
    storage: { get: (_, fallback) => fallback, set: () => {} },
    register: contribution => {
      contributions.set(contribution.id, contribution)
      return () => contributions.delete(contribution.id)
    },
    i18n: {
      register: value => { bundles = value }, t: translate,
      ...(hasLocaleSubscription ? { onLocaleChange: listener => listeners.push(listener) } : {})
    }
  })
  function view() {
    cursor = 0
    const element = contributions.get('page').render()
    return element.type(element.props)
  }
  return {
    view, contributions, notifications, effects,
    response: value => { response = value },
    switchLocale: value => { locale = value; listeners.forEach(fn => fn()) }
  }
}

function nodes(tree) {
  if (tree === null || tree === undefined) return []
  if (Array.isArray(tree)) return tree.flatMap(nodes)
  if (typeof tree !== 'object') return []
  return [tree, ...nodes(tree.props?.children)]
}
function copy(tree) {
  const result = []
  function collect(value) {
    if (typeof value === 'string') result.push(value)
    else if (Array.isArray(value)) value.forEach(collect)
    else if (value?.props) {
      for (const key of ['children', 'title', 'description', 'placeholder']) collect(value.props[key])
    }
  }
  collect(tree)
  return result
}
const timestamp = 1773835200
const cases = [
  { locale: undefined, title: 'MAX Sessions', refresh: 'Refresh', empty: 'No MAX sessions found', loading: 'Loading conversations...', error: 'Could not load sessions: failure', untitled: 'Untitled', count: '2 msgs' },
  { locale: 'en', title: 'MAX Sessions', refresh: 'Refresh', empty: 'No MAX sessions found', loading: 'Loading conversations...', error: 'Could not load sessions: failure', untitled: 'Untitled', count: '2 msgs' },
  { locale: 'ru', title: 'Сессии MAX', refresh: 'Обновить', empty: 'Сессии MAX не найдены', loading: 'Загрузка диалогов...', error: 'Ошибка загрузки: failure', untitled: 'Без названия', count: '2 сообщ.' },
  // Unknown-to-plugin locales retain English strings but their own date format.
  { locale: 'de', title: 'MAX Sessions', refresh: 'Refresh', empty: 'No MAX sessions found', loading: 'Loading conversations...', error: 'Could not load sessions: failure', untitled: 'Untitled', count: '2 msgs' }
]

async function run() {
  for (const expected of cases) {
    const h = harness(expected.locale)
    let tree = h.view()
    assert.ok(copy(tree).includes(expected.title))
    assert.ok(copy(tree).includes(expected.empty))
    assert.ok(copy(tree).includes(expected.refresh))
    const fetch = nodes(tree).find(n => n.type === 'Button').props.onClick
    h.response(new Error('failure'))
    const pending = fetch()
    assert.ok(copy(h.view()).includes(expected.loading))
    await pending
    assert.ok(copy(h.view()).includes(expected.error))
    h.response({ sessions: [
      { id: 'max-1', source: 'max', title: '', started_at: timestamp, input_tokens: 3, message_count: 2 },
      { id: 'telegram-1', source: 'telegram', title: 'Other platform must be hidden' }
    ] })
    await fetch()
    tree = h.view()
    const text = copy(tree)
    assert.ok(text.includes(expected.untitled))
    assert.ok(text.includes(expected.count))
    assert.ok(!text.includes('Other platform must be hidden'))
    const date = new Date(timestamp * 1000)
    assert.ok(text.includes(new Intl.DateTimeFormat(expected.locale || 'en', { day: '2-digit', month: 'short', year: 'numeric' }).format(date)))
    assert.ok(text.includes(new Intl.DateTimeFormat(expected.locale || 'en', { hour: '2-digit', minute: '2-digit' }).format(date)))
    const row = nodes(tree).find(n => n.props.key === 'max-1')
    await row.props.onClick()
    const openNotification = h.notifications.at(-1)
    assert.equal(openNotification.title, expected.title)
    assert.equal(openNotification.message, expected.locale === 'ru' ? 'Не удалось открыть сессию: session unavailable' : 'Could not open session: session unavailable')
    // Search empty state is translated, and invalid timestamps cannot crash rows.
    nodes(tree).find(n => n.type === 'Input').props.onChange({ target: { value: 'no match' } })
    assert.ok(copy(h.view()).includes(expected.locale === 'ru' ? 'Попробуйте изменить поисковый запрос' : 'Try a different search query'))
  }
  const h = harness('en')
  h.view()
  h.switchLocale('ru')
  assert.ok(copy(h.view()).includes('Сессии MAX'))
  assert.equal(h.contributions.get('open').data.label, 'MAX: Открыть список сессий')
  assert.equal(h.contributions.size, 5)
  const chip = h.contributions.get('statusbar').render()
  assert.equal(chip.type(chip.props).props.title, 'Открыть сессии MAX')
  h.contributions.get('toggle-statusbar').data.run()
  assert.equal(h.notifications.at(-1).message, 'Иконка MAX отключена в статусбаре')
  h.response(new Error())
  await nodes(h.view()).find(n => n.type === 'Button').props.onClick()
  assert.ok(copy(h.view()).includes('Ошибка загрузки: Не удалось загрузить сессии'))
  h.switchLocale('de')
  assert.ok(copy(h.view()).includes('MAX Sessions'))
  assert.ok(copy(h.view()).includes('Could not load sessions: Failed to fetch sessions'))
  assert.equal(h.contributions.get('open').data.label, 'MAX: Open Sessions List')
  assert.equal(h.contributions.size, 5)
  const legacy = harness('en', false)
  assert.equal(legacy.contributions.size, 5)
  legacy.switchLocale('ru')
  assert.ok(copy(legacy.view()).includes('Сессии MAX'))
  assert.equal(legacy.contributions.get('open').data.label, 'MAX: Open Sessions List')
  legacy.contributions.get('toggle-statusbar').data.run()
  assert.equal(legacy.notifications.at(-1).message, 'Иконка MAX отключена в статусбаре')
  console.log('MS-006: English default, Russian/unknown locale, view states, dates, locale switch, palette and notifications passed')
}
run().catch(error => { console.error(error); process.exitCode = 1 })
