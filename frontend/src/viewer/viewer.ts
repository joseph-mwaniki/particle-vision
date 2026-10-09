import * as SPLAT from "../gsplat";
import { MeshCollision } from "./collision";

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
  private controls: SPLAT.FPSControls | SPLAT.OrbitControls;
  private navigationMode: "walk" | "orbit" = "walk";
  private renderLoopRunning = false;
  private collisionMesh: MeshCollision | null = null;
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

  setNavigationMode(mode: "walk" | "orbit"): void {
    if (mode === this.navigationMode) return;

    this.controls.dispose();
    this.navigationMode = mode;

    if (mode === "orbit") {
      const euler = this.camera.rotation.toEuler();
      const radius = 5;
      const lookDirection = this.camera.rotation.apply(new SPLAT.Vector3(0, 0, 1)).normalize();
      const target = this.camera.position.add(lookDirection.multiply(radius));
      this.controls = new SPLAT.OrbitControls(
        this.camera,
        this.renderer.canvas,
        -euler.y,
        -euler.x,
        radius,
        true,
        target,
      );
    } else {
      const fps = new SPLAT.FPSControls(this.camera, this.renderer.canvas);
      if (this.collisionMesh) {
        fps.setCollision(this.collisionMesh);
      }
      this.controls = fps;
    }
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
   * Load collision mesh from GLB (.collision.glb).
   * Enables ground snapping/navigation and collision pushout in walk mode.
   */
  async loadCollisionMesh(url: string): Promise<void> {
    try {
      this.options.onProgress?.("Loading collision data...", 90);
      const res = await fetch(url);
      if (!res.ok) {
        console.warn(`[viewer] Failed to fetch collision mesh: ${res.status}`);
        return;
      }
      const buffer = await res.arrayBuffer();
      this.collisionMesh = MeshCollision.fromGlbBuffer(buffer);
      this.collisionMeshLoaded = true;

      if (this.controls instanceof SPLAT.FPSControls) {
        this.controls.setCollision(this.collisionMesh);
      }
      console.info(
        `[viewer] Collision mesh successfully loaded and active (${this.collisionMesh.triangleCount} triangles).`
      );
    } catch (err) {
      console.warn("[viewer] Could not initialize collision mesh:", err);
    }
  }

  hasCollision(): boolean {
    return this.collisionMeshLoaded;
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
