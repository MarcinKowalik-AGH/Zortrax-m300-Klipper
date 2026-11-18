// Marcin Kowalik <mkowalik@agh.edu.pl>
// m300-sidebar.ts - Otwiera wybraną stronę Fluidd po błędzie pobierania jej modułu.
import { isNavigationFailure, type default as VueRouter } from 'vue-router'
import { consola } from 'consola'

let latestSelection = 0

function reloadAtRoute (path: string) {
  // Fluidd uses hash routing. Keep the selected printer and deployment path.
  const url = new URL(window.location.href)
  url.hash = path
  window.history.pushState(null, '', url)
  window.location.reload()
}

export async function navigateM300Sidebar (router: VueRouter, name: string, reload = reloadAtRoute) {
  const selection = ++latestSelection
  const from = router.currentRoute
  const target = { name }
  try {
    await router.push(target)
  } catch (error) {
    if (isNavigationFailure(error) || selection !== latestSelection || router.currentRoute !== from) return
    const message = error instanceof Error ? error.message : String(error)
    if (/dynamically imported module|importing a module script failed|unable to preload css|loading (?:css )?chunk|error loading imported module/i.test(message)) {
      reload(router.resolve(target).route.fullPath)
    } else {
      consola.error('[M300] Sidebar navigation failed', error)
    }
  }
}
