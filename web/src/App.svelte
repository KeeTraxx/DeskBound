<script lang="ts">
  import { onDestroy } from 'svelte'
  import ControlsHelp from './lib/ControlsHelp.svelte'
  import { Emulator } from './lib/emulator.svelte'
  import GameBoyScene from './lib/GameBoyScene.svelte'
  import RomPanel from './lib/RomPanel.svelte'

  // BASE_URL, not "/": on GitHub Pages the site lives under /DeskBound/.
  const romUrl = `${import.meta.env.BASE_URL}DeskBound.gb`

  const emulator = new Emulator()
  onDestroy(() => emulator.dispose())

  let dragOver = $state(false)

  function onDrop(e: DragEvent) {
    e.preventDefault()
    dragOver = false
    const file = e.dataTransfer?.files?.[0]
    if (file) emulator.loadFile(file)
  }
</script>

<svelte:window
  ondragover={(e) => {
    e.preventDefault()
    dragOver = true
  }}
  ondragleave={(e) => {
    // Only when the drag leaves the window, not when it crosses between elements.
    if (!e.relatedTarget) dragOver = false
  }}
  ondrop={onDrop}
/>

<GameBoyScene screen={emulator.screen} onerror={(message) => (emulator.error = message)} />

<div class="hud top-left">
  <RomPanel {emulator} {romUrl} />
</div>

<div class="hud bottom-left">
  <ControlsHelp pressed={emulator.pressed} />
</div>

{#if dragOver}
  <div class="drop-hint">Drop a .gb ROM to play it</div>
{/if}

<style>
  .hud {
    position: fixed;
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  .top-left {
    top: 16px;
    left: 16px;
  }

  .bottom-left {
    bottom: 16px;
    left: 16px;
  }

  .drop-hint {
    position: fixed;
    inset: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    font-family: var(--mono);
    font-size: 20px;
    color: var(--text-h);
    background: color-mix(in srgb, var(--accent) 15%, transparent);
    outline: 3px dashed var(--accent);
    outline-offset: -12px;
    pointer-events: none;
  }
</style>
