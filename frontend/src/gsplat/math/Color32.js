class Color32 {
    r;
    g;
    b;
    a;
    constructor(r = 0, g = 0, b = 0, a = 255) {
        this.r = r;
        this.g = g;
        this.b = b;
        this.a = a;
    }
    flat() {
        return [this.r, this.g, this.b, this.a];
    }
    flatNorm() {
        return [this.r / 255, this.g / 255, this.b / 255, this.a / 255];
    }
    toHexString() {
        return ("#" +
            this.flat()
                .map((x) => x.toString(16).padStart(2, "0"))
                .join(""));
    }
    toString() {
        return `[${this.flat().join(", ")}]`;
    }
}
export { Color32 };
