import { SplatData } from "../splats/SplatData";
import { Splat } from "../splats/Splat";
import { EventDispatcher } from "../events/EventDispatcher";
import { ObjectAddedEvent, ObjectRemovedEvent } from "../events/Events";
import { Converter } from "../utils/Converter";
class Scene extends EventDispatcher {
    _objects = [];
    addObject;
    removeObject;
    findObject;
    findObjectOfType;
    reset;
    constructor() {
        super();
        this.addObject = (object) => {
            this.objects.push(object);
            this.dispatchEvent(new ObjectAddedEvent(object));
        };
        this.removeObject = (object) => {
            const index = this.objects.indexOf(object);
            if (index < 0) {
                throw new Error("Object not found in scene");
            }
            this.objects.splice(index, 1);
            this.dispatchEvent(new ObjectRemovedEvent(object));
        };
        this.findObject = (predicate) => {
            for (const object of this.objects) {
                if (predicate(object)) {
                    return object;
                }
            }
            return undefined;
        };
        this.findObjectOfType = (type) => {
            for (const object of this.objects) {
                if (object instanceof type) {
                    return object;
                }
            }
            return undefined;
        };
        this.reset = () => {
            const objectsToRemove = this.objects.slice();
            for (const object of objectsToRemove) {
                this.removeObject(object);
            }
        };
        this.reset();
    }
    getMergedSceneDataBuffer(format = "splat") {
        const buffers = [];
        let vertexCount = 0;
        for (const object of this.objects) {
            if (object instanceof Splat) {
                const splatClone = object.clone();
                splatClone.applyRotation();
                splatClone.applyScale();
                splatClone.applyPosition();
                const buffer = splatClone.data.serialize();
                buffers.push(buffer);
                vertexCount += splatClone.data.vertexCount;
            }
        }
        const mergedSplatData = new Uint8Array(vertexCount * SplatData.RowLength);
        let offset = 0;
        for (const buffer of buffers) {
            mergedSplatData.set(buffer, offset);
            offset += buffer.length;
        }
        if (format === "ply") {
            return Converter.SplatToPLY(mergedSplatData.buffer, vertexCount);
        }
        return mergedSplatData.buffer;
    }
    saveToFile(name = null, format = "splat") {
        if (!document)
            return;
        if (!name) {
            const now = new Date();
            name = `scene-${now.getFullYear()}-${now.getMonth() + 1}-${now.getDate()}.${format}`;
        }
        const mergedData = this.getMergedSceneDataBuffer(format);
        const blob = new Blob([mergedData], { type: "application/octet-stream" });
        const link = document.createElement("a");
        link.download = name;
        link.href = URL.createObjectURL(blob);
        link.click();
    }
    get objects() {
        return this._objects;
    }
}
export { Scene };
