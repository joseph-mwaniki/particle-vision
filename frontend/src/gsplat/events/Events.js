class ObjectAddedEvent extends Event {
    object;
    constructor(object) {
        super("objectAdded");
        this.object = object;
    }
}
class ObjectRemovedEvent extends Event {
    object;
    constructor(object) {
        super("objectRemoved");
        this.object = object;
    }
}
class ObjectChangedEvent extends Event {
    object;
    constructor(object) {
        super("objectChanged");
        this.object = object;
    }
}
export { ObjectAddedEvent, ObjectRemovedEvent, ObjectChangedEvent };
