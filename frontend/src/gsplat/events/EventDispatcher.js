class EventDispatcher {
    addEventListener;
    removeEventListener;
    hasEventListener;
    dispatchEvent;
    constructor() {
        const listeners = new Map();
        this.addEventListener = (type, listener) => {
            if (!listeners.has(type)) {
                listeners.set(type, new Set());
            }
            listeners.get(type).add(listener);
        };
        this.removeEventListener = (type, listener) => {
            if (!listeners.has(type)) {
                return;
            }
            listeners.get(type).delete(listener);
        };
        this.hasEventListener = (type, listener) => {
            if (!listeners.has(type)) {
                return false;
            }
            return listeners.get(type).has(listener);
        };
        this.dispatchEvent = (event) => {
            if (!listeners.has(event.type)) {
                return;
            }
            for (const listener of listeners.get(event.type)) {
                listener(event);
            }
        };
    }
}
export { EventDispatcher };
