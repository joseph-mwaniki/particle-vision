import { FadeInPass } from "./webgl/passes/FadeInPass";
import { Color32 } from "../math/Color32";
import { RenderProgram } from "./webgl/programs/RenderProgram";
export class WebGLRenderer {
    _canvas;
    _gl;
    _backgroundColor = new Color32();
    _renderProgram;
    addProgram;
    removeProgram;
    resize;
    setSize;
    render;
    dispose;
    constructor(optionalCanvas = null, optionalRenderPasses = null) {
        const canvas = optionalCanvas || document.createElement("canvas");
        if (!optionalCanvas) {
            canvas.style.display = "block";
            canvas.style.boxSizing = "border-box";
            canvas.style.width = "100%";
            canvas.style.height = "100%";
            canvas.style.margin = "0";
            canvas.style.padding = "0";
            document.body.appendChild(canvas);
        }
        canvas.style.background = this._backgroundColor.toHexString();
        this._canvas = canvas;
        this._gl = canvas.getContext("webgl2", { antialias: false });
        const renderPasses = optionalRenderPasses || [];
        if (!optionalRenderPasses) {
            renderPasses.push(new FadeInPass());
        }
        this._renderProgram = new RenderProgram(this, renderPasses);
        const programs = [this._renderProgram];
        this.resize = () => {
            const width = canvas.clientWidth;
            const height = canvas.clientHeight;
            if (canvas.width !== width || canvas.height !== height) {
                this.setSize(width, height);
            }
        };
        this.setSize = (width, height) => {
            canvas.width = width;
            canvas.height = height;
            this._gl.viewport(0, 0, canvas.width, canvas.height);
            for (const program of programs) {
                program.resize();
            }
        };
        this.render = (scene, camera) => {
            for (const program of programs) {
                program.render(scene, camera);
            }
        };
        this.dispose = () => {
            for (const program of programs) {
                program.dispose();
            }
        };
        this.addProgram = (program) => {
            programs.push(program);
        };
        this.removeProgram = (program) => {
            const index = programs.indexOf(program);
            if (index < 0) {
                throw new Error("Program not found");
            }
            programs.splice(index, 1);
        };
        this.resize();
    }
    get canvas() {
        return this._canvas;
    }
    get gl() {
        return this._gl;
    }
    get renderProgram() {
        return this._renderProgram;
    }
    get backgroundColor() {
        return this._backgroundColor;
    }
    set backgroundColor(value) {
        this._backgroundColor = value;
        this._canvas.style.background = value.toHexString();
    }
}
