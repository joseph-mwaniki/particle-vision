import * as SPLAT from "../gsplat";

export interface ViewerOptions {
  canvas: HTMLCanvasElement;
  onProgress?: (message: string, progress: number) => void;
  onReady?: () => void;
  onError?: (message: string) => void;
}

export class SplatViewer {
  private scene: SPLAT.Scene;
  private camera: SPLAT.Camera;
  private renderer: SPLAT.WebGLRenderer;
  private controls: SPLAT.FPSControls;
  private renderLoopRunning = false;
  private collisionMeshLoaded = false;

  constructor(private options: ViewerOptions) {
    this.scene = new SPLAT.Scene();
    this.camera = new SPLAT.Camera();
    this.renderer = new SPLAT.WebGLRenderer(options.canvas);
    this.controls = new SPLAT.FPSControls(this.camera, this.renderer.canvas);

    const handleResize = () => {
      this.renderer.setSize(options.canvas.clientWidth, options.canvas.clientHeight);
    };
    handleResize();
    window.addEventListener("resize", handleResize);
  }

  async loadSplat(url: string): Promise<void> {
    this.scene.reset();
    this.options.onProgress?.("Loading 3D splat scene...", 0);

    await SPLAT.Loader.LoadAsync(url, this.scene, (progress: number) => {
      this.options.onProgress?.(`Loading scene: ${(progress * 100).toFixed(0)}%`, progress * 100);
    });

    this.options.onReady?.();
    this.startRenderLoop();
  }

  /**
   * Load collision mesh for future physics/navigation.
   * The mesh is invisible — intended for raycasting and collision detection only.
   * Not yet implemented: requires a GLB loader (e.g. three.js GLTFLoader).
   */
  async loadCollisionMesh(url: string): Promise<void> {
    // Architecture placeholder: collision.glb will be loaded here invisibly
    console.info("[viewer] Collision mesh ready to load (not yet implemented):", url);
    this.collisionMeshLoaded = true;
  }

  captureScreenshot(filename: string): void {
    const dataUrl = this.options.canvas.toDataURL("image/png");
    const link = document.createElement("a");
    link.download = filename;
    link.href = dataUrl;
    link.click();
  }

  private startRenderLoop(): void {
    if (this.renderLoopRunning) return;
    this.renderLoopRunning = true;

    const frame = () => {
      if (!this.renderLoopRunning) return;
      this.controls.update();
      this.renderer.render(this.scene, this.camera);
      requestAnimationFrame(frame);
    };
    requestAnimationFrame(frame);
  }

}
