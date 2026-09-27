<script lang="ts">
  import { onMount } from 'svelte'
  import { GameBoyScene } from './gameboy-scene'

  interface Props {
    /** Canvas whose contents appear on the Game Boy's screen. */
    screen: HTMLCanvasElement
    onerror?: (message: string) => void
  }

  let { screen, onerror }: Props = $props()

  let canvas: HTMLCanvasElement

  onMount(() => {
    const scene = new GameBoyScene(canvas, screen, (message) =>
      onerror ? onerror(message) : console.error(message),
    )
    return () => scene.dispose()
  })
</script>

<canvas bind:this={canvas}></canvas>

<style>
  canvas {
    position: fixed;
    inset: 0;
    display: block;
    width: 100vw;
    height: 100dvh;
    /* OrbitControls handles touch drags itself; don't let the page scroll/zoom. */
    touch-action: none;
  }
</style>
