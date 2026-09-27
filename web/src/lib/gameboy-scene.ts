import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js'
// `?url` has Vite copy the model into the build and hand back its final URL, base
// path included — so it resolves under GitHub Pages' /DeskBound/ prefix.
import modelUrl from '../assets/gb_model.glb?url'

/**
 * A Game Boy model whose screen shows a live canvas.
 *
 * Adapted from game-koi's Three.js example. Framework-agnostic: the Svelte wrapper
 * (`GameBoyScene.svelte`) only creates and disposes it.
 */
export class GameBoyScene {
  readonly scene = new THREE.Scene()
  readonly camera = new THREE.PerspectiveCamera(45, 4 / 3, 0.1, 100)
  readonly renderer: THREE.WebGLRenderer
  readonly controls: OrbitControls

  private readonly screenTexture: THREE.CanvasTexture
  private readonly screenMaterial: THREE.ShaderMaterial
  private readonly resizeObserver: ResizeObserver

  constructor(
    private readonly canvas: HTMLCanvasElement,
    screen: HTMLCanvasElement,
    onError: (message: string) => void = console.error,
  ) {
    // The whole trick: a texture backed by the canvas the emulator draws into.
    this.screenTexture = new THREE.CanvasTexture(screen)
    // Linear filtering plus mipmaps, which on their own would blur the pixels into
    // mush — the screen material's shader below is what keeps them sharp. Plain
    // NearestFilter shimmers as the view moves, because the screen usually covers
    // fewer device pixels than its 160 texels.
    this.screenTexture.magFilter = THREE.LinearFilter
    this.screenTexture.minFilter = THREE.LinearMipmapLinearFilter
    this.screenTexture.generateMipmaps = true
    this.screenTexture.colorSpace = THREE.SRGBColorSpace
    // GLTFLoader sets flipY = false on every texture it loads; this one does not come
    // from the loader, and with three's default of true the game plays upside down.
    this.screenTexture.flipY = false

    this.scene.background = new THREE.Color(0x14181c)
    this.camera.position.set(0, 0.6, 4.2)

    this.renderer = new THREE.WebGLRenderer({ canvas, antialias: true })
    this.renderer.setPixelRatio(Math.min(devicePixelRatio, 2))
    // Sharper sampling when the screen is seen at an angle, e.g. while orbiting.
    this.screenTexture.anisotropy = this.renderer.capabilities.getMaxAnisotropy()

    this.scene.add(new THREE.AmbientLight(0xffffff, 1.2))
    const key = new THREE.DirectionalLight(0xffffff, 2)
    key.position.set(2, 3, 4)
    this.scene.add(key)
    // A weaker light from behind, so the back has some shape instead of flat ambient.
    const fill = new THREE.DirectionalLight(0xffffff, 0.8)
    fill.position.set(-2, 1, -4)
    this.scene.add(fill)

    this.screenMaterial = createScreenMaterial(this.screenTexture, screen)
    this.loadModel(onError)

    this.controls = new OrbitControls(this.camera, canvas)
    this.controls.enableDamping = true
    this.controls.minDistance = 2.5
    this.controls.maxDistance = 8

    this.resizeObserver = new ResizeObserver(() => this.resize())
    this.resizeObserver.observe(canvas)
    this.resize()

    this.renderer.setAnimationLoop(() => this.render())
  }

  dispose() {
    this.renderer.setAnimationLoop(null)
    this.resizeObserver.disconnect()
    this.controls.dispose()
    this.screenMaterial.dispose()
    this.screenTexture.dispose()
    this.renderer.dispose()
  }

  private loadModel(onError: (message: string) => void) {
    new GLTFLoader().load(
      modelUrl,
      (gltf) => {
        const model = gltf.scene
        // Only the "Display" quad is swapped for the live screen. Its UVs span 0..1
        // over the one face, so the whole 160x144 frame lands on it.
        const display = model.getObjectByName('Display')
        if (!(display instanceof THREE.Mesh)) {
          onError('model has no "Display" mesh')
          return
        }
        display.material = this.screenMaterial

        // Modelled lying on its back; a quarter turn about X stands it up facing the
        // camera, with the cartridge slot on top.
        model.rotation.x = Math.PI / 2

        // The model is life-size in metres; scale to about two units tall and centre
        // on the origin, which is what OrbitControls circles.
        const box = new THREE.Box3().setFromObject(model)
        const size = box.getSize(new THREE.Vector3())
        model.scale.setScalar(2.2 / size.y)
        box.setFromObject(model)
        model.position.sub(box.getCenter(new THREE.Vector3()))

        this.scene.add(model)
      },
      undefined,
      (err) => onError(`error loading model: ${err}`),
    )
  }

  private resize() {
    const { clientWidth: w, clientHeight: h } = this.canvas
    if (w === 0 || h === 0) return
    this.renderer.setSize(w, h, false)
    this.camera.aspect = w / h
    this.camera.updateProjectionMatrix()
  }

  private render() {
    // GameKoi repaints its canvas on its own requestAnimationFrame schedule, so there
    // is no callback to hook — re-upload every frame. At 160x144 the cost is noise.
    this.screenTexture.needsUpdate = true
    this.controls.update()
    this.renderer.render(this.scene, this.camera)
  }
}

/**
 * "Sharp bilinear" sampling: pixel art that stays crisp up close and antialiased
 * everywhere. Inside a texel the lookup snaps to the texel centre, like NearestFilter;
 * only across a texel boundary does it blend, over the width of one screen pixel.
 * When the screen is small that width exceeds a texel and it degrades into ordinary
 * linear + mipmap filtering. `textureGrad` gets the *unsnapped* UV derivatives, since
 * the snapped coordinate is flat inside a texel and would fool it into choosing mip 0.
 *
 * Like MeshBasicMaterial it ignores lights, keeping the emulator's colours intact.
 */
function createScreenMaterial(texture: THREE.Texture, screen: HTMLCanvasElement) {
  return new THREE.ShaderMaterial({
    uniforms: {
      map: { value: texture },
      texSize: { value: new THREE.Vector2(screen.width, screen.height) },
    },
    vertexShader: /* glsl */ `
      varying vec2 vUv;
      void main() {
        vUv = uv;
        gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
      }
    `,
    fragmentShader: /* glsl */ `
      uniform sampler2D map;
      uniform vec2 texSize;
      varying vec2 vUv;
      void main() {
        vec2 texel = vUv * texSize;
        vec2 seam = floor(texel + 0.5);
        vec2 pixelInTexels = max(fwidth(texel), vec2(1e-5));
        texel = seam + clamp((texel - seam) / pixelInTexels, -0.5, 0.5);
        gl_FragColor = textureGrad(map, texel / texSize, dFdx(vUv), dFdy(vUv));
        // The texture is sRGB, so the sample came back linear; convert to the
        // renderer's output space, which MeshBasicMaterial would do for us.
        #include <colorspace_fragment>
      }
    `,
  })
}
