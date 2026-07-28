class ShaderProgram {
    _renderer;
    _program;
    _passes;
    _scene = null;
    _camera = null;
    _started = false;
    _initialized = false;
    initialize;
    resize;
    render;
    dispose;
    constructor(renderer, passes) {
        this._renderer = renderer;
        const gl = renderer.gl;
        this._program = gl.createProgram();
        this._passes = passes || [];
        const vertexShader = gl.createShader(gl.VERTEX_SHADER);
        gl.shaderSource(vertexShader, this._getVertexSource());
        gl.compileShader(vertexShader);
        if (!gl.getShaderParameter(vertexShader, gl.COMPILE_STATUS)) {
            console.error(gl.getShaderInfoLog(vertexShader));
        }
        const fragmentShader = gl.createShader(gl.FRAGMENT_SHADER);
        gl.shaderSource(fragmentShader, this._getFragmentSource());
        gl.compileShader(fragmentShader);
        if (!gl.getShaderParameter(fragmentShader, gl.COMPILE_STATUS)) {
            console.error(gl.getShaderInfoLog(fragmentShader));
        }
        gl.attachShader(this.program, vertexShader);
        gl.attachShader(this.program, fragmentShader);
        gl.linkProgram(this.program);
        if (!gl.getProgramParameter(this.program, gl.LINK_STATUS)) {
            console.error(gl.getProgramInfoLog(this.program));
        }
        this.resize = () => {
            gl.useProgram(this._program);
            this._resize();
        };
        this.initialize = () => {
            console.assert(!this._initialized, "ShaderProgram already initialized");
            gl.useProgram(this._program);
            this._initialize();
            for (const pass of this.passes) {
                pass.initialize(this);
            }
            this._initialized = true;
            this._started = true;
        };
        this.render = (scene, camera) => {
            gl.useProgram(this._program);
            if (this._scene !== scene || this._camera !== camera) {
                this.dispose();
                this._scene = scene;
                this._camera = camera;
                this.initialize();
            }
            for (const pass of this.passes) {
                pass.render();
            }
            this._render();
        };
        this.dispose = () => {
            if (!this._initialized)
                return;
            gl.useProgram(this._program);
            for (const pass of this.passes) {
                pass.dispose();
            }
            this._dispose();
            this._scene = null;
            this._camera = null;
            this._initialized = false;
        };
    }
    get renderer() {
        return this._renderer;
    }
    get scene() {
        return this._scene;
    }
    get camera() {
        return this._camera;
    }
    get program() {
        return this._program;
    }
    get passes() {
        return this._passes;
    }
    get started() {
        return this._started;
    }
}
export { ShaderProgram };
