<script lang="ts">
  import type { Button } from 'game-koi'

  interface Props {
    /** Buttons held right now; their keys are highlighted. */
    pressed: ReadonlySet<Button>
  }

  let { pressed }: Props = $props()

  // game-koi's default keymap (bound by KeyboardEvent.code, i.e. physical position).
  const rows: { label: string; keys: { button: Button; key: string; title: string }[] }[] = [
    {
      label: 'D-pad',
      keys: [
        { button: 'up', key: '↑', title: 'Up' },
        { button: 'down', key: '↓', title: 'Down' },
        { button: 'left', key: '←', title: 'Left' },
        { button: 'right', key: '→', title: 'Right' },
      ],
    },
    {
      label: 'A / B',
      keys: [
        { button: 'a', key: 'Z', title: 'A' },
        { button: 'b', key: 'X', title: 'B' },
      ],
    },
    {
      label: 'Start / Select',
      keys: [
        { button: 'start', key: 'Enter', title: 'Start' },
        { button: 'select', key: 'Right Shift', title: 'Select' },
      ],
    },
  ]
</script>

<details class="panel" open>
  <summary>Controls</summary>
  <dl>
    {#each rows as row (row.label)}
      <dt>{row.label}</dt>
      <dd>
        {#each row.keys as { button, key, title } (button)}
          <kbd class:active={pressed.has(button)} title={title}>{key}</kbd>
        {/each}
      </dd>
    {/each}

    <dt>Camera</dt>
    <dd>drag to orbit, scroll to zoom</dd>
  </dl>
  <p class="note">
    Keys are bound by position, not by label — on a non-QWERTY layout, A and B are
    wherever <kbd>Z</kbd> and <kbd>X</kbd> sit on a US keyboard.
  </p>

  <h3>🎮 Gamepad</h3>
  <p class="note">
    Any standard gamepad works, no setup needed — press a button on it once so the
    browser shows it to the page. D-pad or left stick to move, the right and bottom
    face buttons for A and B, Start and Back for Start and Select. Held buttons light
    up above too.
  </p>
</details>

<style>
  details {
    max-width: 340px;
    font-size: 14px;
    /* The panel's flex gap would also pad the hidden content while closed. */
    gap: 0;
  }

  summary {
    cursor: pointer;
    font-weight: 500;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--text-h);
  }

  dl {
    display: grid;
    grid-template-columns: auto 1fr;
    gap: 8px 16px;
    margin: 12px 0 0;
    align-items: baseline;
  }

  dt {
    color: var(--text-h);
  }

  dd {
    margin: 0;
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
  }

  kbd {
    font-family: var(--mono);
    font-size: 12px;
    line-height: 1;
    padding: 4px 6px;
    border: 1px solid var(--border);
    border-bottom-width: 2px;
    border-radius: 5px;
    color: var(--text-h);
    background: color-mix(in srgb, var(--text) 7%, transparent);
    white-space: nowrap;
    transition:
      background-color 60ms,
      border-color 60ms,
      transform 60ms;
  }

  /* Held: pushed down into its border, and lit in the accent colour. */
  kbd.active {
    color: var(--bg);
    background: var(--accent);
    border-color: var(--accent);
    transform: translateY(1px);
  }

  h3 {
    margin: 14px 0 0;
    font-size: 14px;
    font-weight: 500;
    color: var(--text-h);
  }

  .note {
    margin: 8px 0 0;
    line-height: 155%;
  }
</style>
