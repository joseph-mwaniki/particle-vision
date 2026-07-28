import { Splat } from "../splats/Splat";
import { SplatData } from "../splats/SplatData";
import { initiateFetchRequest, loadDataIntoBuffer } from "../utils/LoaderUtils";
class Loader {
    static async LoadAsync(url, scene, onProgress, useCache = false) {
        const res = await initiateFetchRequest(url, useCache);
        const buffer = await loadDataIntoBuffer(res, onProgress);
        return this.LoadFromArrayBuffer(buffer.buffer, scene);
    }
    static async LoadFromFileAsync(file, scene, onProgress) {
        const reader = new FileReader();
        let splat = new Splat();
        reader.onload = (e) => {
            splat = this.LoadFromArrayBuffer(e.target.result, scene);
        };
        reader.onprogress = (e) => {
            onProgress?.(e.loaded / e.total);
        };
        reader.readAsArrayBuffer(file);
        await new Promise((resolve) => {
            reader.onloadend = () => {
                resolve();
            };
        });
        return splat;
    }
    static LoadFromArrayBuffer(arrayBuffer, scene) {
        const buffer = new Uint8Array(arrayBuffer);
        const data = SplatData.Deserialize(buffer);
        const splat = new Splat(data);
        scene.addObject(splat);
        return splat;
    }
}
export { Loader };
