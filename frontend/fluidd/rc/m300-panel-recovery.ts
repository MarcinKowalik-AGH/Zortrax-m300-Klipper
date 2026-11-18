// Marcin Kowalik <mkowalik@agh.edu.pl>
// m300-panel-recovery.ts - Odświeża widok po odzyskaniu połączenia z tą samą drukarką i ogranicza częstość przeładowań.
type Link = 'socket' | 'klippy'

export class M300PanelRecovery {
  private lost = new Map<Link, string>()
  private reload: () => void

  constructor (reload = () => window.location.reload()) {
    this.reload = reload
  }

  observe (link: Link, url: string, ready: boolean, previouslyReady: boolean) {
    if (!ready) {
      if (url && previouslyReady) this.lost.set(link, url)
      return
    }
    const lostUrl = this.lost.get(link)
    this.lost.delete(link)
    if (!url || url !== lostUrl) return

    try {
      const key = 'm300-panel-reload:' + url
      const now = Date.now()
      const previous = Number(window.sessionStorage.getItem(key))
      if (now - previous < 120_000 && previous <= now) return
      window.sessionStorage.setItem(key, String(now))
    } catch {
      // The socket resubscribes even when the embedded browser disables storage.
      return
    }
    this.reload()
  }
}
