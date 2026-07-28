import { Vector3 } from "../math/Vector3";
import { Quaternion } from "../math/Quaternion";
import { EventDispatcher } from "../events/EventDispatcher";
import { Matrix4 } from "../math/Matrix4";
import { ObjectChangedEvent } from "../events/Events";
class Object3D extends EventDispatcher {
    positionChanged = false;
    rotationChanged = false;
    scaleChanged = false;
    _position = new Vector3();
    _rotation = new Quaternion();
    _scale = new Vector3(1, 1, 1);
    _transform = new Matrix4();
    _changeEvent = new ObjectChangedEvent(this);
    update;
    applyPosition;
    applyRotation;
    applyScale;
    raiseChangeEvent;
    constructor() {
        super();
        this.update = () => { };
        this.applyPosition = () => {
            this.position = new Vector3();
        };
        this.applyRotation = () => {
            this.rotation = new Quaternion();
        };
        this.applyScale = () => {
            this.scale = new Vector3(1, 1, 1);
        };
        this.raiseChangeEvent = () => {
            this.dispatchEvent(this._changeEvent);
        };
    }
    _updateMatrix() {
        this._transform = Matrix4.Compose(this._position, this._rotation, this._scale);
    }
    get position() {
        return this._position;
    }
    set position(position) {
        if (!this._position.equals(position)) {
            this._position = position;
            this.positionChanged = true;
            this._updateMatrix();
            this.dispatchEvent(this._changeEvent);
        }
    }
    get rotation() {
        return this._rotation;
    }
    set rotation(rotation) {
        if (!this._rotation.equals(rotation)) {
            this._rotation = rotation;
            this.rotationChanged = true;
            this._updateMatrix();
            this.dispatchEvent(this._changeEvent);
        }
    }
    get scale() {
        return this._scale;
    }
    set scale(scale) {
        if (!this._scale.equals(scale)) {
            this._scale = scale;
            this.scaleChanged = true;
            this._updateMatrix();
            this.dispatchEvent(this._changeEvent);
        }
    }
    get forward() {
        let forward = new Vector3(0, 0, 1);
        forward = this.rotation.apply(forward);
        return forward;
    }
    get transform() {
        return this._transform;
    }
}
export { Object3D };
