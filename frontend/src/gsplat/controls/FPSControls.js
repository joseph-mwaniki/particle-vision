import { Quaternion } from "../math/Quaternion";
import { Vector3 } from "../math/Vector3";
class FPSControls {
    moveSpeed = 2;
    lookSpeed = 0.0025;
    acceleration = 12;
    friction = 10;
    update;
    dispose;
    constructor(camera, canvas) {
        const keys = {};
        const originalCursor = canvas.style.cursor;
        let pitch = camera.rotation.toEuler().x;
        let yaw = camera.rotation.toEuler().y;
        let velocity = new Vector3();
        let dragging = false;
        let lastX = 0;
        let lastY = 0;
        let lastTime = performance.now();
        const onMouseDown = (e) => {
            if (e.button !== 0)
                return;
            dragging = true;
            lastX = e.clientX;
            lastY = e.clientY;
            canvas.style.cursor = "grabbing";
            window.addEventListener("mousemove", onMouseMove);
            window.addEventListener("mouseup", onMouseUp);
            e.preventDefault();
        };
        const onMouseUp = (e) => {
            if (e.button !== 0)
                return;
            dragging = false;
            canvas.style.cursor = "grab";
            window.removeEventListener("mousemove", onMouseMove);
            window.removeEventListener("mouseup", onMouseUp);
        };
        const onMouseMove = (e) => {
            if (!dragging)
                return;
            yaw += (e.clientX - lastX) * this.lookSpeed;
            pitch -= (e.clientY - lastY) * this.lookSpeed;
            const pitchLimit = Math.PI / 2 - 0.01;
            pitch = Math.max(-pitchLimit, Math.min(pitchLimit, pitch));
            lastX = e.clientX;
            lastY = e.clientY;
        };
        const onKeyDown = (e) => {
            keys[e.code] = true;
            if (e.code === "ArrowUp")
                keys["KeyW"] = true;
            if (e.code === "ArrowDown")
                keys["KeyS"] = true;
            if (e.code === "ArrowLeft")
                keys["KeyA"] = true;
            if (e.code === "ArrowRight")
                keys["KeyD"] = true;
            if (e.code.startsWith("Arrow"))
                e.preventDefault();
        };
        const onKeyUp = (e) => {
            keys[e.code] = false;
            if (e.code === "ArrowUp")
                keys["KeyW"] = false;
            if (e.code === "ArrowDown")
                keys["KeyS"] = false;
            if (e.code === "ArrowLeft")
                keys["KeyA"] = false;
            if (e.code === "ArrowRight")
                keys["KeyD"] = false;
        };
        const onBlur = () => {
            for (const key in keys)
                keys[key] = false;
        };
        const preventDefault = (e) => e.preventDefault();
        this.update = () => {
            const now = performance.now();
            const dt = Math.min((now - lastTime) / 1000, 0.1);
            lastTime = now;
            const forward = new Vector3(Math.sin(yaw), 0, Math.cos(yaw));
            const right = new Vector3(Math.cos(yaw), 0, -Math.sin(yaw));
            let wish = new Vector3();
            if (keys["KeyW"])
                wish = wish.add(forward);
            if (keys["KeyS"])
                wish = wish.subtract(forward);
            if (keys["KeyA"])
                wish = wish.subtract(right);
            if (keys["KeyD"])
                wish = wish.add(right);
            const moving = wish.magnitude() > 0;
            if (moving)
                wish = wish.normalize();
            const targetVelocity = wish.multiply(this.moveSpeed);
            const rate = moving ? this.acceleration : this.friction;
            velocity = velocity.lerp(targetVelocity, Math.min(rate * dt, 1));
            camera.position = camera.position.add(velocity.multiply(dt));
            camera.rotation = Quaternion.FromEuler(new Vector3(pitch, yaw, 0));
        };
        this.dispose = () => {
            canvas.removeEventListener("mousedown", onMouseDown);
            canvas.removeEventListener("contextmenu", preventDefault);
            window.removeEventListener("mousemove", onMouseMove);
            window.removeEventListener("mouseup", onMouseUp);
            window.removeEventListener("keydown", onKeyDown);
            window.removeEventListener("keyup", onKeyUp);
            window.removeEventListener("blur", onBlur);
            canvas.style.cursor = originalCursor;
        };
        canvas.style.cursor = "grab";
        canvas.addEventListener("mousedown", onMouseDown);
        canvas.addEventListener("contextmenu", preventDefault);
        window.addEventListener("keydown", onKeyDown);
        window.addEventListener("keyup", onKeyUp);
        window.addEventListener("blur", onBlur);
    }
}
export { FPSControls };
