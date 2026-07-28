class Plane {
    normal;
    point;
    constructor(normal, point) {
        this.normal = normal;
        this.point = point;
    }
    intersect(origin, direction) {
        const denominator = this.normal.dot(direction);
        if (Math.abs(denominator) < 0.0001) {
            return null;
        }
        const t = this.normal.dot(this.point.subtract(origin)) / denominator;
        if (t < 0) {
            return null;
        }
        return origin.add(direction.multiply(t));
    }
}
export { Plane };
