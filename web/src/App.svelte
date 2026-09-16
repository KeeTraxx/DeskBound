<script lang="ts">
  import { GameKoi } from 'game-koi'

  let canvas: HTMLCanvasElement
  let koi: GameKoi | null = null
  let romName = $state<string | null>(null)
  let error = $state<string | null>(null)
  let dragOver = $state(false)

  async function loadRom(rom: Uint8Array, name: string) {
    if (koi) {
      koi.loadRom(rom)
    } else {
      koi = await GameKoi.create({ canvas, rom })
    }
    romName = name
  }

  async function loadRomFile(file: File) {
    error = null
    try {
      await loadRom(new Uint8Array(await file.arrayBuffer()), file.name)
    } catch (e) {
      error = e instanceof Error ? e.message : String(e)
    }
  }

  async function loadDeskBound() {
    error = null
    try {
      // BASE_URL, not "/": on GitHub Pages the site lives under /DeskBound/.
      const res = await fetch(`${import.meta.env.BASE_URL}DeskBound.gb`)
      if (!res.ok) {
        throw new Error("DeskBound.gb not found — run `just rom` to build it first")
      }
      await loadRom(new Uint8Array(await res.arrayBuffer()), 'DeskBound.gb')
    } catch (e) {
      error = e instanceof Error ? e.message : String(e)
    }
  }

  function onFileInput(e: Event) {
    const file = (e.target as HTMLInputElement).files?.[0]
    if (file) loadRomFile(file)
  }

  function onDrop(e: DragEvent) {
    e.preventDefault()
    dragOver = false
    const file = e.dataTransfer?.files?.[0]
    if (file) loadRomFile(file)
  }
</script>

<main>
  <h1>DeskBound</h1>

  <div
    class="screen"
    role="region"
    aria-label="Game screen, drop a ROM here"
    class:drag-over={dragOver}
    ondragover={(e) => {
      e.preventDefault()
      dragOver = true
    }}
    ondragleave={() => (dragOver = false)}
    ondrop={onDrop}
  >
    <canvas bind:this={canvas} width="160" height="144"></canvas>
    {#if !romName}
      <p class="hint">Drop a .gb ROM here, or choose a file below</p>
    {/if}
  </div>

  <div class="controls">
    <button class="picker" onclick={loadDeskBound}>Load DeskBound</button>
    <label class="picker">
      Load ROM
      <input type="file" accept=".gb" onchange={onFileInput} />
    </label>
  </div>

  {#if romName}
    <p class="rom-name">{romName}</p>
  {/if}
  {#if error}
    <p class="error">{error}</p>
  {/if}
</main>
