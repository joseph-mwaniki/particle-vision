import * as SPLAT from "../gsplat";
export class SplatViewer {
    options;
    scene;
    camera;
    renderer;
    controls;
    navigationMode = "walk";
    renderLoopRunning = false;
    collisionMeshLoaded = false;
    handleKeyboardInput = (e) => {
        if (this.navigationMode !== "orbit")
            return;
        const rotation = SPLAT.Matrix3.RotationFromQuaternion(this.camera.rotation).buffer;
        const forward = new SPLAT.Vector3(-rotation[2], -rotation[5], -rotation[8]).normalize();
        const right = new SPLAT.Vector3(rotation[0], rotation[3], rotation[6]).normalize();
        const up = new SPLAT.Vector3(rotation[1], rotation[4], rotation[7]).normalize();
        const step = 0.4;
        const turnStep = 0.08;
        const euler = this.camera.rotation.toEuler();
        let pitch = euler.x;
        let yaw = euler.y;
        let moved = false;
        let turned = false;
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
            yaw += turnStep;
            turned = true;
        }
        if (e.code === "ArrowRight") {
            yaw -= turnStep;
            turned = true;
        }
        if (e.code === "ArrowUp") {
            pitch += turnStep;
            turned = true;
        }
        if (e.code === "ArrowDown") {
            pitch -= turnStep;
            turned = true;
        }
        if (turned) {
            this.camera.rotation = SPLAT.Quaternion.FromEuler(new SPLAT.Vector3(pitch, yaw, 0));
        }
        if (moved || turned)
            this.controls.update();
    };
    constructor(options) {
        this.options = options;
        this.scene = new SPLAT.Scene();
        this.camera = new SPLAT.Camera();
        this.renderer = new SPLAT.WebGLRenderer(options.canvas);
        this.controls = new SPLAT.FPSControls(this.camera, this.renderer.canvas);
        window.addEventListener("keydown", this.handleKeyboardInput);
        const handleResize = () => {
            this.renderer.setSize(options.canvas.clientWidth, options.canvas.clientHeight);
        };
        handleResize();
        window.addEventListener("resize", handleResize);
    }
    setNavigationMode(mode) {
        if (mode === this.navigationMode)
            return;
        this.controls.dispose();
        this.navigationMode = mode;
        if (mode === "orbit") {
            const euler = this.camera.rotation.toEuler();
            const radius = 5;
            const lookDirection = this.camera.rotation.apply(new SPLAT.Vector3(0, 0, 1)).normalize();
            const target = this.camera.position.add(lookDirection.multiply(radius));
            this.controls = new SPLAT.OrbitControls(this.camera, this.renderer.canvas, -euler.y, -euler.x, radius, false, target);
        }
        else {
            this.controls = new SPLAT.FPSControls(this.camera, this.renderer.canvas);
        }
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
}
