/**
 * MeshCollision implementation for remote-view
 * Extracted and adapted from PlayCanvas SuperSplat Collision Mesh architecture.
 */

export interface RayHit {
  x: number;
  y: number;
  z: number;
  t?: number;
}

export interface PushOut {
  x: number;
  y: number;
  z: number;
}

export interface TriangleBounds {
  minX: number;
  minY: number;
  minZ: number;
  maxX: number;
  maxY: number;
  maxZ: number;
}

export interface BVHNode {
  minX: number;
  minY: number;
  minZ: number;
  maxX: number;
  maxY: number;
  maxZ: number;
  left: BVHNode | null;
  right: BVHNode | null;
  triStart: number;
  triCount: number;
}

export interface TriangleSoA {
  v0x: Float32Array;
  v0y: Float32Array;
  v0z: Float32Array;
  v1x: Float32Array;
  v1y: Float32Array;
  v1z: Float32Array;
  v2x: Float32Array;
  v2y: Float32Array;
  v2z: Float32Array;
  nx: Float32Array;
  ny: Float32Array;
  nz: Float32Array;
  indices: Uint32Array;
  count: number;
}

const PENETRATION_EPSILON = 1e-4;
const MAX_RESOLVE_ITERATIONS = 4;
const MAX_LEAF_TRIS = 4;

const _closest = { x: 0, y: 0, z: 0 };
const _push = { x: 0, y: 0, z: 0 };

function computeTriangleBounds(tris: TriangleSoA, idx: number, out: TriangleBounds): void {
  const i = tris.indices[idx];
  out.minX = Math.min(tris.v0x[i], tris.v1x[i], tris.v2x[i]);
  out.minY = Math.min(tris.v0y[i], tris.v1y[i], tris.v2y[i]);
  out.minZ = Math.min(tris.v0z[i], tris.v1z[i], tris.v2z[i]);
  out.maxX = Math.max(tris.v0x[i], tris.v1x[i], tris.v2x[i]);
  out.maxY = Math.max(tris.v0y[i], tris.v1y[i], tris.v2y[i]);
  out.maxZ = Math.max(tris.v0z[i], tris.v1z[i], tris.v2z[i]);
}

function buildBVH(tris: TriangleSoA, start: number, count: number): BVHNode {
  const bounds: TriangleBounds = {
    minX: Infinity,
    minY: Infinity,
    minZ: Infinity,
    maxX: -Infinity,
    maxY: -Infinity,
    maxZ: -Infinity,
  };
  const tb: TriangleBounds = { minX: 0, minY: 0, minZ: 0, maxX: 0, maxY: 0, maxZ: 0 };

  for (let i = start; i < start + count; i++) {
    computeTriangleBounds(tris, i, tb);
    bounds.minX = Math.min(bounds.minX, tb.minX);
    bounds.minY = Math.min(bounds.minY, tb.minY);
    bounds.minZ = Math.min(bounds.minZ, tb.minZ);
    bounds.maxX = Math.max(bounds.maxX, tb.maxX);
    bounds.maxY = Math.max(bounds.maxY, tb.maxY);
    bounds.maxZ = Math.max(bounds.maxZ, tb.maxZ);
  }

  if (count <= MAX_LEAF_TRIS) {
    return {
      ...bounds,
      left: null,
      right: null,
      triStart: start,
      triCount: count,
    };
  }

  const dx = bounds.maxX - bounds.minX;
  const dy = bounds.maxY - bounds.minY;
  const dz = bounds.maxZ - bounds.minZ;
  let axis = 0;
  let mid = (bounds.minX + bounds.maxX) * 0.5;

  if (dy > dx && dy > dz) {
    axis = 1;
    mid = (bounds.minY + bounds.maxY) * 0.5;
  } else if (dz > dx) {
    axis = 2;
    mid = (bounds.minZ + bounds.maxZ) * 0.5;
  }

  let l = start;
  let r = start + count - 1;
  while (l <= r) {
    const ti = tris.indices[l];
    let c = 0;
    if (axis === 0) c = (tris.v0x[ti] + tris.v1x[ti] + tris.v2x[ti]) / 3;
    else if (axis === 1) c = (tris.v0y[ti] + tris.v1y[ti] + tris.v2y[ti]) / 3;
    else c = (tris.v0z[ti] + tris.v1z[ti] + tris.v2z[ti]) / 3;

    if (c < mid) {
      l++;
    } else {
      const temp = tris.indices[l];
      tris.indices[l] = tris.indices[r];
      tris.indices[r] = temp;
      r--;
    }
  }

  let leftCount = l - start;
  if (leftCount === 0 || leftCount === count) {
    leftCount = count >> 1;
  }

  const left = buildBVH(tris, start, leftCount);
  const right = buildBVH(tris, start + leftCount, count - leftCount);

  return {
    ...bounds,
    left,
    right,
    triStart: start,
    triCount: count,
  };
}

function rayAABB(
  ox: number, oy: number, oz: number,
  idx: number, idy: number, idz: number,
  minX: number, minY: number, minZ: number,
  maxX: number, maxY: number, maxZ: number,
  maxDist: number
): number {
  const t1 = (minX - ox) * idx;
  const t2 = (maxX - ox) * idx;
  const t3 = (minY - oy) * idy;
  const t4 = (maxY - oy) * idy;
  const t5 = (minZ - oz) * idz;
  const t6 = (maxZ - oz) * idz;

  const tmin = Math.max(Math.max(Math.min(t1, t2), Math.min(t3, t4)), Math.min(t5, t6));
  const tmax = Math.min(Math.min(Math.max(t1, t2), Math.max(t3, t4)), Math.max(t5, t6));

  if (tmax < 0 || tmin > tmax || tmin > maxDist) return -1;
  return tmin < 0 ? 0 : tmin;
}

function rayTriangle(
  ox: number, oy: number, oz: number,
  dx: number, dy: number, dz: number,
  v0x: number, v0y: number, v0z: number,
  v1x: number, v1y: number, v1z: number,
  v2x: number, v2y: number, v2z: number,
  maxDist: number
): number {
  const e1x = v1x - v0x;
  const e1y = v1y - v0y;
  const e1z = v1z - v0z;
  const e2x = v2x - v0x;
  const e2y = v2y - v0y;
  const e2z = v2z - v0z;

  const pvecX = dy * e2z - dz * e2y;
  const pvecY = dz * e2x - dx * e2z;
  const pvecZ = dx * e2y - dy * e2x;
  const det = e1x * pvecX + e1y * pvecY + e1z * pvecZ;

  if (Math.abs(det) < 1e-10) return -1;
  const invDet = 1.0 / det;

  const tvecX = ox - v0x;
  const tvecY = oy - v0y;
  const tvecZ = oz - v0z;
  const u = (tvecX * pvecX + tvecY * pvecY + tvecZ * pvecZ) * invDet;
  if (u < 0 || u > 1) return -1;

  const qvecX = tvecY * e1z - tvecZ * e1y;
  const qvecY = tvecZ * e1x - tvecX * e1z;
  const qvecZ = tvecX * e1y - tvecY * e1x;
  const v = (dx * qvecX + dy * qvecY + dz * qvecZ) * invDet;
  if (v < 0 || u + v > 1) return -1;

  const t = (e2x * qvecX + e2y * qvecY + e2z * qvecZ) * invDet;
  return t >= 0 && t <= maxDist ? t : -1;
}

function sphereAABBOverlap(
  cx: number, cy: number, cz: number, r: number,
  minX: number, minY: number, minZ: number,
  maxX: number, maxY: number, maxZ: number
): boolean {
  const qx = Math.max(minX, Math.min(cx, maxX));
  const qy = Math.max(minY, Math.min(cy, maxY));
  const qz = Math.max(minZ, Math.min(cz, maxZ));
  const dx = cx - qx;
  const dy = cy - qy;
  const dz = cz - qz;
  return dx * dx + dy * dy + dz * dz <= r * r;
}

function closestPointOnTriangle(
  px: number, py: number, pz: number,
  aX: number, aY: number, aZ: number,
  bX: number, bY: number, bZ: number,
  cX: number, cY: number, cZ: number,
  out: { x: number; y: number; z: number }
): void {
  const abX = bX - aX, abY = bY - aY, abZ = bZ - aZ;
  const acX = cX - aX, acY = cY - aY, acZ = cZ - aZ;
  const apX = px - aX, apY = py - aY, apZ = pz - aZ;

  const d1 = abX * apX + abY * apY + abZ * apZ;
  const d2 = acX * apX + acY * apY + acZ * apZ;
  if (d1 <= 0 && d2 <= 0) {
    out.x = aX; out.y = aY; out.z = aZ;
    return;
  }

  const bpX = px - bX, bpY = py - bY, bpZ = pz - bZ;
  const d3 = abX * bpX + abY * bpY + abZ * bpZ;
  const d4 = acX * bpX + acY * bpY + acZ * bpZ;
  if (d3 >= 0 && d4 <= d3) {
    out.x = bX; out.y = bY; out.z = bZ;
    return;
  }

  const vc = d1 * d4 - d3 * d2;
  if (vc <= 0 && d1 >= 0 && d3 <= 0) {
    const v = d1 / (d1 - d3);
    out.x = aX + v * abX; out.y = aY + v * abY; out.z = aZ + v * abZ;
    return;
  }

  const cpX = px - cX, cpY = py - cY, cpZ = pz - cZ;
  const d5 = abX * cpX + abY * cpY + abZ * cpZ;
  const d6 = acX * cpX + acY * cpY + acZ * cpZ;
  if (d6 >= 0 && d5 <= d6) {
    out.x = cX; out.y = cY; out.z = cZ;
    return;
  }

  const vb = d5 * d2 - d1 * d6;
  if (vb <= 0 && d2 >= 0 && d6 <= 0) {
    const w = d2 / (d2 - d6);
    out.x = aX + w * acX; out.y = aY + w * acY; out.z = aZ + w * acZ;
    return;
  }

  const va = d3 * d6 - d5 * d4;
  if (va <= 0 && (d4 - d3) >= 0 && (d5 - d6) >= 0) {
    const w = (d4 - d3) / ((d4 - d3) + (d5 - d6));
    out.x = bX + w * (cX - bX); out.y = bY + w * (cY - bY); out.z = bZ + w * (cZ - bZ);
    return;
  }

  const denom = 1.0 / (va + vb + vc);
  const v = vb * denom;
  const w = vc * denom;
  out.x = aX + abX * v + acX * w;
  out.y = aY + abY * v + acY * w;
  out.z = aZ + abZ * v + acZ * w;
}

function resolveIterative(
  cx: number, cy: number, cz: number,
  findPenetration: (cx: number, cy: number, cz: number, out: PushOut) => boolean,
  constraintNormals: { x: number; y: number; z: number }[],
  scratch: PushOut,
  out: PushOut
): boolean {
  let resolvedX = cx;
  let resolvedY = cy;
  let resolvedZ = cz;
  let totalPushX = 0;
  let totalPushY = 0;
  let totalPushZ = 0;
  let hadCollision = false;
  let numNormals = 0;

  for (let iter = 0; iter < MAX_RESOLVE_ITERATIONS; iter++) {
    if (!findPenetration(resolvedX, resolvedY, resolvedZ, scratch)) break;
    hadCollision = true;

    let px = scratch.x;
    let py = scratch.y;
    let pz = scratch.z;

    for (let i = 0; i < numNormals; i++) {
      const n = constraintNormals[i];
      const dot = px * n.x + py * n.y + pz * n.z;
      if (dot < 0) {
        px -= dot * n.x;
        py -= dot * n.y;
        pz -= dot * n.z;
      }
    }

    const len = Math.sqrt(px * px + py * py + pz * pz);
    if (len > PENETRATION_EPSILON && numNormals < 3) {
      const invLen = 1.0 / len;
      const n = constraintNormals[numNormals];
      n.x = px * invLen;
      n.y = py * invLen;
      n.z = pz * invLen;
      numNormals++;
    }

    resolvedX += px;
    resolvedY += py;
    resolvedZ += pz;
    totalPushX += px;
    totalPushY += py;
    totalPushZ += pz;
  }

  const totalPushSq = totalPushX * totalPushX + totalPushY * totalPushY + totalPushZ * totalPushZ;
  const hasSignificantPush = hadCollision && totalPushSq > PENETRATION_EPSILON * PENETRATION_EPSILON;
  if (hasSignificantPush) {
    out.x = totalPushX;
    out.y = totalPushY;
    out.z = totalPushZ;
  }
  return hasSignificantPush;
}

export class MeshCollision {
  private _tris: TriangleSoA;
  private _root: BVHNode;
  private _stack: BVHNode[] = [];
  private _constraintNormals = [
    { x: 0, y: 0, z: 0 },
    { x: 0, y: 0, z: 0 },
    { x: 0, y: 0, z: 0 },
  ];
  readonly voxelResolution = 0.05;

  constructor(positions: Float32Array, indices: Uint32Array) {
    const numTris = Math.floor(indices.length / 3);
    const tris: TriangleSoA = {
      v0x: new Float32Array(numTris),
      v0y: new Float32Array(numTris),
      v0z: new Float32Array(numTris),
      v1x: new Float32Array(numTris),
      v1y: new Float32Array(numTris),
      v1z: new Float32Array(numTris),
      v2x: new Float32Array(numTris),
      v2y: new Float32Array(numTris),
      v2z: new Float32Array(numTris),
      nx: new Float32Array(numTris),
      ny: new Float32Array(numTris),
      nz: new Float32Array(numTris),
      indices: new Uint32Array(numTris),
      count: numTris,
    };

    for (let i = 0; i < numTris; i++) {
      const i0 = indices[i * 3] * 3;
      const i1 = indices[i * 3 + 1] * 3;
      const i2 = indices[i * 3 + 2] * 3;

      tris.v0x[i] = positions[i0];
      tris.v0y[i] = positions[i0 + 1];
      tris.v0z[i] = positions[i0 + 2];

      tris.v1x[i] = positions[i1];
      tris.v1y[i] = positions[i1 + 1];
      tris.v1z[i] = positions[i1 + 2];

      tris.v2x[i] = positions[i2];
      tris.v2y[i] = positions[i2 + 1];
      tris.v2z[i] = positions[i2 + 2];

      const e1x = tris.v1x[i] - tris.v0x[i];
      const e1y = tris.v1y[i] - tris.v0y[i];
      const e1z = tris.v1z[i] - tris.v0z[i];

      const e2x = tris.v2x[i] - tris.v0x[i];
      const e2y = tris.v2y[i] - tris.v0y[i];
      const e2z = tris.v2z[i] - tris.v0z[i];

      let fnx = e1y * e2z - e1z * e2y;
      let fny = e1z * e2x - e1x * e2z;
      let fnz = e1x * e2y - e1y * e2x;
      const len = Math.sqrt(fnx * fnx + fny * fny + fnz * fnz);
      if (len > 1e-10) {
        const inv = 1.0 / len;
        fnx *= inv;
        fny *= inv;
        fnz *= inv;
      }
      tris.nx[i] = fnx;
      tris.ny[i] = fny;
      tris.nz[i] = fnz;
      tris.indices[i] = i;
    }

    this._tris = tris;
    this._root = buildBVH(tris, 0, numTris);
  }

  get triangleCount(): number {
    return this._tris.count;
  }

  queryRay(ox: number, oy: number, oz: number, dx: number, dy: number, dz: number, maxDist = 100): RayHit | null {
    const len = Math.sqrt(dx * dx + dy * dy + dz * dz);
    if (len < 1e-10) return null;
    const invLen = 1.0 / len;
    dx *= invLen;
    dy *= invLen;
    dz *= invLen;

    const idx = 1.0 / (Math.abs(dx) > 1e-12 ? dx : dx >= 0 ? 1e-12 : -1e-12);
    const idy = 1.0 / (Math.abs(dy) > 1e-12 ? dy : dy >= 0 ? 1e-12 : -1e-12);
    const idz = 1.0 / (Math.abs(dz) > 1e-12 ? dz : dz >= 0 ? 1e-12 : -1e-12);

    const root = this._root;
    if (rayAABB(ox, oy, oz, idx, idy, idz, root.minX, root.minY, root.minZ, root.maxX, root.maxY, root.maxZ, maxDist) < 0) {
      return null;
    }

    const stack = this._stack;
    let top = 0;
    stack[top++] = root;
    let bestT = maxDist + 1;
    const tris = this._tris;

    while (top > 0) {
      const node = stack[--top];
      if (node.left === null) {
        for (let j = node.triStart; j < node.triStart + node.triCount; j++) {
          const i = tris.indices[j];
          const ht = rayTriangle(
            ox, oy, oz, dx, dy, dz,
            tris.v0x[i], tris.v0y[i], tris.v0z[i],
            tris.v1x[i], tris.v1y[i], tris.v1z[i],
            tris.v2x[i], tris.v2y[i], tris.v2z[i],
            bestT
          );
          if (ht >= 0 && ht < bestT) {
            bestT = ht;
          }
        }
        continue;
      }

      const left = node.left;
      const right = node.right!;
      const tL = rayAABB(ox, oy, oz, idx, idy, idz, left.minX, left.minY, left.minZ, left.maxX, left.maxY, left.maxZ, bestT);
      const tR = rayAABB(ox, oy, oz, idx, idy, idz, right.minX, right.minY, right.minZ, right.maxX, right.maxY, right.maxZ, bestT);

      if (tL >= 0 && tR >= 0) {
        if (tL < tR) {
          stack[top++] = right;
          stack[top++] = left;
        } else {
          stack[top++] = left;
          stack[top++] = right;
        }
      } else if (tL >= 0) {
        stack[top++] = left;
      } else if (tR >= 0) {
        stack[top++] = right;
      }
    }

    if (bestT <= maxDist) {
      return {
        x: ox + dx * bestT,
        y: oy + dy * bestT,
        z: oz + dz * bestT,
        t: bestT,
      };
    }
    return null;
  }

  querySphere(cx: number, cy: number, cz: number, radius: number, out: PushOut): boolean {
    return resolveIterative(
      cx, cy, cz,
      (rx, ry, rz, push) => this._deepestSpherePenetration(rx, ry, rz, radius, push),
      this._constraintNormals,
      _push,
      out
    );
  }

  private _deepestSpherePenetration(cx: number, cy: number, cz: number, radius: number, out: PushOut): boolean {
    let bestPen = PENETRATION_EPSILON;
    let bestPx = 0, bestPy = 0, bestPz = 0;
    let found = false;

    this._sphereBVH(this._root, cx, cy, cz, radius, (triIdx) => {
      const tris = this._tris;
      closestPointOnTriangle(
        cx, cy, cz,
        tris.v0x[triIdx], tris.v0y[triIdx], tris.v0z[triIdx],
        tris.v1x[triIdx], tris.v1y[triIdx], tris.v1z[triIdx],
        tris.v2x[triIdx], tris.v2y[triIdx], tris.v2z[triIdx],
        _closest
      );
      const dx = cx - _closest.x;
      const dy = cy - _closest.y;
      const dz = cz - _closest.z;
      const distSq = dx * dx + dy * dy + dz * dz;
      if (distSq >= radius * radius) return;

      const dist = Math.sqrt(distSq);
      const penetration = radius - dist;
      if (penetration > bestPen) {
        bestPen = penetration;
        if (dist > 1e-10) {
          const inv = 1.0 / dist;
          bestPx = dx * inv * penetration;
          bestPy = dy * inv * penetration;
          bestPz = dz * inv * penetration;
        } else {
          bestPx = tris.nx[triIdx] * penetration;
          bestPy = tris.ny[triIdx] * penetration;
          bestPz = tris.nz[triIdx] * penetration;
        }
        found = true;
      }
    });

    if (found) {
      out.x = bestPx;
      out.y = bestPy;
      out.z = bestPz;
    }
    return found;
  }

  private _sphereBVH(root: BVHNode, cx: number, cy: number, cz: number, radius: number, callback: (triIdx: number) => void): void {
    const stack = this._stack;
    let top = 0;
    stack[top++] = root;

    while (top > 0) {
      const node = stack[--top];
      if (!sphereAABBOverlap(cx, cy, cz, radius, node.minX, node.minY, node.minZ, node.maxX, node.maxY, node.maxZ)) {
        continue;
      }
      if (node.left === null) {
        const tris = this._tris;
        for (let j = node.triStart; j < node.triStart + node.triCount; j++) {
          callback(tris.indices[j]);
        }
        continue;
      }
      stack[top++] = node.right!;
      stack[top++] = node.left;
    }
  }

  static fromGlbBuffer(buffer: ArrayBuffer): MeshCollision {
    const dataView = new DataView(buffer);
    const magic = dataView.getUint32(0, true);
    if (magic !== 0x46546c67) {
      throw new Error("Invalid GLB header magic number.");
    }
    const jsonChunkLength = dataView.getUint32(12, true);
    const jsonBytes = new Uint8Array(buffer, 20, jsonChunkLength);
    const jsonStr = new TextDecoder().decode(jsonBytes);
    const gltf = JSON.parse(jsonStr);

    const binChunkHeaderOffset = 20 + jsonChunkLength;
    const binDataOffset = binChunkHeaderOffset + 8;

    // Accessor 0 is POSITION, Accessor 1 is INDICES
    const posAcc = gltf.accessors[0];
    const posView = gltf.bufferViews[posAcc.bufferView];
    const positions = new Float32Array(
      buffer,
      binDataOffset + (posView.byteOffset || 0) + (posAcc.byteOffset || 0),
      posAcc.count * 3
    );

    const indAcc = gltf.accessors[1];
    const indView = gltf.bufferViews[indAcc.bufferView];
    const byteOffset = binDataOffset + (indView.byteOffset || 0) + (indAcc.byteOffset || 0);

    let indices: Uint32Array;
    if (indAcc.componentType === 5125) {
      indices = new Uint32Array(buffer, byteOffset, indAcc.count);
    } else {
      const u16 = new Uint16Array(buffer, byteOffset, indAcc.count);
      indices = new Uint32Array(u16.length);
      for (let i = 0; i < u16.length; i++) indices[i] = u16[i];
    }

    return new MeshCollision(positions, indices);
  }
}
