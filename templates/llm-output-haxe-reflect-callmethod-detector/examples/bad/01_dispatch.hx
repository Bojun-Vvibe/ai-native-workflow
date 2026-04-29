// Bad: classic Reflect.callMethod with a runtime-chosen method name.
class Rpc {
    public static function dispatch(target:Dynamic, name:String, args:Array<Dynamic>) {
        var m = Reflect.field(target, name);
        return Reflect.callMethod(target, m, args);
    }
}
