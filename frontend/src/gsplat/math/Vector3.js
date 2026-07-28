class Vector3 {
    x;
    y;
    z;
    constructor(x = 0, y = 0, z = 0) {
        this.x = x;
        this.y = y;
        this.z = z;
    }
    equals(v) {
        if (this.x !== v.x) {
            return false;
        }
        if (this.y !== v.y) {
            return false;
        }
        if (this.z !== v.z) {
            return false;
        }
        return true;
    }
    add(v) {
        if (typeof v === "number") {
            return new Vector3(this.x + v, this.y + v, this.z + v);
        }
        else {
            return new Vector3(this.x + v.x, this.y + v.y, this.z + v.z);
        }
    }
    subtract(v) {
        if (typeof v === "number") {
            return new Vector3(this.x - v, this.y - v, this.z - v);
        }
        else {
            return new Vector3(this.x - v.x, this.y - v.y, this.z - v.z);
        }
    }
    multiply(v) {
        if (typeof v === "number") {
            return new Vector3(this.x * v, this.y * v, this.z * v);
        }
        else if (v instanceof Vector3) {
            return new Vector3(this.x * v.x, this.y * v.y, this.z * v.z);
        }
        else {
            return new Vector3(this.x * v.buffer[0] + this.y * v.buffer[4] + this.z * v.buffer[8] + v.buffer[12], this.x * v.buffer[1] + this.y * v.buffer[5] + this.z * v.buffer[9] + v.buffer[13], this.x * v.buffer[2] + this.y * v.buffer[6] + this.z * v.buffer[10] + v.buffer[14]);
        }
    }
    divide(v) {
        if (typeof v === "number") {
            return new Vector3(this.x / v, this.y / v, this.z / v);
        }
        else {
            return new Vector3(this.x / v.x, this.y / v.y, this.z / v.z);
        }
    }
    cross(v) {
        const x = this.y * v.z - this.z * v.y;
        const y = this.z * v.x - this.x * v.z;
        const z = this.x * v.y - this.y * v.x;
        return new Vector3(x, y, z);
    }
    dot(v) {
        return this.x * v.x + this.y * v.y + this.z * v.z;
    }
    lerp(v, t) {
        return new Vector3(this.x + (v.x - this.x) * t, this.y + (v.y - this.y) * t, this.z + (v.z - this.z) * t);
    }
    min(v) {
        return new Vector3(Math.min(this.x, v.x), Math.min(this.y, v.y), Math.min(this.z, v.z));
    }
    max(v) {
        return new Vector3(Math.max(this.x, v.x), Math.max(this.y, v.y), Math.max(this.z, v.z));
    }
    getComponent(axis) {
        switch (axis) {
            case 0:
                return this.x;
            case 1:
                return this.y;
            case 2:
                return this.z;
            default:
                throw new Error(`Invalid component index: ${axis}`);
        }
    }
    minComponent() {
        if (this.x < this.y && this.x < this.z) {
            return 0;
        }
        else if (this.y < this.z) {
            return 1;
        }
        else {
            return 2;
        }
    }
    maxComponent() {
        if (this.x > this.y && this.x > this.z) {
            return 0;
        }
        else if (this.y > this.z) {
            return 1;
        }
        else {
            return 2;
        }
    }
    magnitude() {
        return Math.sqrt(this.x * this.x + this.y * this.y + this.z * this.z);
    }
    distanceTo(v) {
        return Math.sqrt((this.x - v.x) ** 2 + (this.y - v.y) ** 2 + (this.z - v.z) ** 2);
    }
    normalize() {
        const length = this.magnitude();
        return new Vector3(this.x / length, this.y / length, this.z / length);
    }
    flat() {
        return [this.x, this.y, this.z];
    }
    clone() {
        return new Vector3(this.x, this.y, this.z);
    }
    toString() {
        return `[${this.flat().join(", ")}]`;
    }
    static One(value = 1) {
        return new Vector3(value, value, value);
    }
}
export { Vector3 };
