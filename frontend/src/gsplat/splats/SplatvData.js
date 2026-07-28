class SplatvData {
    static RowLength = 64;
    _vertexCount;
    _positions;
    _data;
    _width;
    _height;
    serialize;
    constructor(vertexCount, positions, data, width, height) {
        this._vertexCount = vertexCount;
        this._positions = positions;
        this._data = data;
        this._width = width;
        this._height = height;
        this.serialize = () => {
            return new Uint8Array(this._data.buffer);
        };
    }
    static Deserialize(data, width, height) {
        const buffer = new Uint32Array(data.buffer);
        const f_buffer = new Float32Array(data.buffer);
        const vertexCount = Math.floor(f_buffer.byteLength / this.RowLength);
        const positions = new Float32Array(vertexCount * 3);
        for (let i = 0; i < vertexCount; i++) {
            positions[3 * i + 0] = f_buffer[16 * i + 0];
            positions[3 * i + 1] = f_buffer[16 * i + 1];
            positions[3 * i + 2] = f_buffer[16 * i + 2];
            positions[3 * i + 0] = f_buffer[16 * i + 3];
        }
        return new SplatvData(vertexCount, positions, buffer, width, height);
    }
    get vertexCount() {
        return this._vertexCount;
    }
    get positions() {
        return this._positions;
    }
    get data() {
        return this._data;
    }
    get width() {
        return this._width;
    }
    get height() {
        return this._height;
    }
}
export { SplatvData };
