import { Object3D } from "../core/Object3D";
class Splatv extends Object3D {
    _data;
    constructor(splat) {
        super();
        this._data = splat;
    }
    get data() {
        return this._data;
    }
}
export { Splatv };
