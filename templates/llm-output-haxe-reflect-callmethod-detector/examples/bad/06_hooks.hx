// Bad: nested call chain — Reflect.callMethod inside a higher-order helper.
class Hooks {
    public static function fire(target:Dynamic, hookName:String):Void {
        try {
            Reflect.callMethod(target, Reflect.field(target, hookName), []);
        } catch (e:Dynamic) {
            trace(e);
        }
    }
}
