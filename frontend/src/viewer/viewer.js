import * as SPLAT from "../gsplat";
export class SplatViewer {
    options;
    scene;
    camera;
    renderer;
    controls;
    renderLoopRunning = false;
    collisionMeshLoaded = false;
    constructor(options) {
        this.options = options;
        this.scene = new SPLAT.Scene();
        this.camera = new SPLAT.Camera();
        this.renderer = new SPLAT.WebGLRenderer(options.canvas);
        this.controls = new SPLAT.OrbitControls(this.camera, this.renderer.canvas, 0.5, 0.5, 5, false);
        const handleResize = () => {
            this.renderer.setSize(options.canvas.clientWidth, options.canvas.clientHeight);
        };
        handleResize();
        window.addEventListener("resize", handleResize);
        this.setupKeyboardControls();
    }
    async loadSplat(url) {
        this.scene.reset();
        this.options.onProgress?.("Loading 3D splat scene...", 0);
        await SPLAT.Loader.LoadAsync(url, this.scene, (progress) => {
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
    async loadCollisionMesh(url) {
        // Architecture placeholder: collision.glb will be loaded here invisibly
        console.info("[viewer] Collision mesh ready to load (not yet implemented):", url);
        this.collisionMeshLoaded = true;
    }
    captureScreenshot(filename) {
        const dataUrl = this.options.canvas.toDataURL("image/png");
        const link = document.createElement("a");
        link.download = filename;
        link.href = dataUrl;
        link.click();
    }
    startRenderLoop() {
        if (this.renderLoopRunning)
            return;
        this.renderLoopRunning = true;
        const frame = () => {
            if (!this.renderLoopRunning)
                return;
            this.controls.update();
            this.renderer.render(this.scene, this.camera);
            requestAnimationFrame(frame);
        };
        requestAnimationFrame(frame);
    }
    setupKeyboardControls() {
        window.addEventListener("keydown", (e) => {
            const R = SPLAT.Matrix3.RotationFromQuaternion(this.camera.rotation).buffer;
            const forward = normalize(new SPLAT.Vector3(-R[2], -R[5], -R[8]));
            const right = normalize(new SPLAT.Vector3(R[0], R[3], R[6]));
            const up = normalize(new SPLAT.Vector3(R[1], R[4], R[7]));
            const step = 0.4;
            const rotStep = 0.08;
            let moved = false;
            let rotated = false;
            const euler = this.camera.rotation.toEuler();
            let pitch = euler.x;
            let yaw = euler.y;
            if (e.code === "KeyW") {
                this.camera.position = this.camera.position.subtract(forward.multiply(step));
                moved = true;
            }
            if (e.code === "KeyS") {
                this.camera.position = this.camera.position.add(forward.multiply(step));
                moved = true;
            }
            if (e.code === "KeyA") {
                this.camera.position = this.camera.position.subtract(right.multiply(step));
                moved = true;
            }
            if (e.code === "KeyD") {
                this.camera.position = this.camera.position.add(right.multiply(step));
                moved = true;
            }
            if (e.code === "KeyQ") {
                this.camera.position = this.camera.position.add(up.multiply(step));
                moved = true;
            }
            if (e.code === "KeyE") {
                this.camera.position = this.camera.position.subtract(up.multiply(step));
                moved = true;
            }
            if (e.code === "ArrowLeft") {
                yaw += rotStep;
                rotated = true;
            }
            if (e.code === "ArrowRight") {
                yaw -= rotStep;
                rotated = true;
            }
            if (e.code === "ArrowUp") {
                pitch += rotStep;
                rotated = true;
            }
            if (e.code === "ArrowDown") {
                pitch -= rotStep;
                rotated = true;
            }
            if (rotated) {
                this.camera.rotation = SPLAT.Quaternion.FromEuler(new SPLAT.Vector3(pitch, yaw, 0));
            }
            if (moved || rotated) {
                this.controls.update();
            }
        });
    }
}
function normalize(v) {
    const mag = Math.sqrt(v.x * v.x + v.y * v.y + v.z * v.z);
    if (mag === 0)
        return v;
    return new SPLAT.Vector3(v.x / mag, v.y / mag, v.z / mag);
}
