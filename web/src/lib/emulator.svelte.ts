import { GameKoi, type Button, type ButtonEvent } from 'game-koi'

// Game Boy LCD resolution; GameKoi resizes its canvas to this anyway.
const WIDTH = 160
const HEIGHT = 144

/**
 * Reactive wrapper around a GameKoi instance.
 *
 * Owns the canvas the emulator draws into. That canvas is never put on the page —
 * it exists to be read as a texture (see `GameBoyScene`), so anything else that
 * wants the live picture can take `emulator.screen` too.
 */
export class Emulator {
  readonly screen: HTMLCanvasElement
  romName = $state<string | null>(null)
  error = $state<string | null>(null)
  /** Buttons held right now, from any input — keyboard, gamepad or `press()`. */
  pressed = $state.raw<ReadonlySet<Button>>(new Set())

  private koi: GameKoi | null = null

  constructor() {
    this.screen = document.createElement('canvas')
    this.screen.width = WIDTH
    this.screen.height = HEIGHT
    // An unlit DMG screen is pale green, not black — fill it so the model looks like
    // hardware that is switched on but has no cartridge, rather than a hole.
    const ctx = this.screen.getContext('2d')!
    ctx.fillStyle = '#e0f8d0'
    ctx.fillRect(0, 0, WIDTH, HEIGHT)
  }

  /** Must be reached from a user gesture the first time, for the AudioContext. */
  async loadRom(rom: Uint8Array, name: string) {
    this.error = null
    try {
      if (this.koi) {
        this.koi.loadRom(rom)
      } else {
        this.koi = await GameKoi.create({
          canvas: this.screen,
          rom,
          // The stats panel positions itself from its canvas's bounding rect,
          // which is meaningless for a canvas that is not on the page.
          overlayKey: null,
        })
        // Each edge carries a fresh snapshot, so plain assignment is enough for Svelte.
        const track = (e: ButtonEvent) => (this.pressed = e.pressed)
        this.koi.on('press', track)
        this.koi.on('release', track)
      }
      this.romName = name
    } catch (e) {
      this.fail(e)
    }
  }

  async loadFile(file: File) {
    try {
      await this.loadRom(new Uint8Array(await file.arrayBuffer()), file.name)
    } catch (e) {
      this.fail(e)
    }
  }

  async loadUrl(url: string, name: string) {
    this.error = null
    try {
      const res = await fetch(url)
      if (!res.ok) throw new Error(`${name} not found (HTTP ${res.status})`)
      await this.loadRom(new Uint8Array(await res.arrayBuffer()), name)
    } catch (e) {
      this.fail(e)
    }
  }

  dispose() {
    this.koi?.dispose()
    this.koi = null
    this.pressed = new Set()
  }

  private fail(e: unknown) {
    this.error = e instanceof Error ? e.message : String(e)
  }
}
