<script lang="ts">
  import type { Emulator } from './emulator.svelte'

  interface Props {
    emulator: Emulator
    /** URL of the bundled DeskBound ROM. */
    romUrl: string
  }

  let { emulator, romUrl }: Props = $props()

  function onFileInput(e: Event) {
    const input = e.target as HTMLInputElement
    const file = input.files?.[0]
    if (file) emulator.loadFile(file)
    // Allow picking the same file again.
    input.value = ''
  }
</script>

<div class="panel">
  <h1>DeskBound</h1>
  <div class="buttons">
    <button class="picker" onclick={() => emulator.loadUrl(romUrl, 'DeskBound.gb')}>
      Load DeskBound
    </button>
    <label class="picker">
      Load ROM
      <input type="file" accept=".gb" onchange={onFileInput} />
    </label>
    <a class="picker" href={romUrl} download="DeskBound.gb">Download .gb</a>
  </div>
  {#if emulator.error}
    <p class="status error">{emulator.error}</p>
  {:else if emulator.romName}
    <p class="status">running {emulator.romName}</p>
  {:else}
    <p class="status">ready — load a ROM, or drop a .gb file anywhere</p>
  {/if}
</div>

<style>
  h1 {
    margin: 0;
    font-size: 20px;
    font-weight: 500;
    color: var(--text-h);
  }

  .buttons {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }

  .picker {
    font: inherit;
    font-family: var(--mono);
    font-size: 14px;
    padding: 6px 12px;
    border-radius: 6px;
    color: var(--accent);
    background: color-mix(in srgb, var(--accent) 10%, transparent);
    border: 2px solid transparent;
    cursor: pointer;
    text-decoration: none;
  }

  .picker:hover {
    border-color: var(--accent);
  }

  .picker input {
    display: none;
  }

  .status {
    margin: 0;
    font-family: var(--mono);
    font-size: 13px;
  }

  .error {
    color: #e5484d;
  }
</style>
