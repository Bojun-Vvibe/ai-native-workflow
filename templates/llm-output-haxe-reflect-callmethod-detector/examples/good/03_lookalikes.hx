// Good: lookalike identifiers that contain "Reflect" or "Type" but
// are NOT the real built-ins.
class MyReflect {
    public function callMethod(name:String):Void {}
}
class TypeRegistry {
    public static function createInstance(name:String):Dynamic return null;
}
class User {
    public static function go():Void {
        var r = new MyReflect();
        r.callMethod("noop");
        var x = TypeRegistry.createInstance("User");
        trace(x);
    }
}
