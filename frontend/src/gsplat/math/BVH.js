class BVHNode {
    bounds;
    boxes;
    left = null;
    right = null;
    pointIndices = [];
    constructor(bounds, boxes, pointIndices) {
        this.bounds = bounds;
        this.boxes = boxes;
        if (pointIndices.length > 1) {
            this.split(bounds, boxes, pointIndices);
        }
        else if (pointIndices.length > 0) {
            this.pointIndices = pointIndices;
        }
    }
    split(bounds, boxes, pointIndices) {
        const axis = bounds.size().maxComponent();
        pointIndices.sort((a, b) => boxes[a].center().getComponent(axis) - boxes[b].center().getComponent(axis));
        const mid = Math.floor(pointIndices.length / 2);
        const leftIndices = pointIndices.slice(0, mid);
        const rightIndices = pointIndices.slice(mid);
        this.left = new BVHNode(bounds, boxes, leftIndices);
        this.right = new BVHNode(bounds, boxes, rightIndices);
    }
    queryRange(range) {
        if (!this.bounds.intersects(range)) {
            return [];
        }
        else if (this.left !== null && this.right !== null) {
            return this.left.queryRange(range).concat(this.right.queryRange(range));
        }
        else {
            return this.pointIndices.filter((index) => range.intersects(this.boxes[index]));
        }
    }
}
class BVH {
    root;
    constructor(bounds, boxes) {
        const pointIndices = boxes.map((_, index) => index);
        this.root = new BVHNode(bounds, boxes, pointIndices);
    }
    queryRange(range) {
        return this.root.queryRange(range);
    }
}
export { BVH };
