// Bad: Reflect.setField writes a caller-named property.
class Setter {
    public static function set(target:Dynamic, name:String, value:Dynamic) {
        Reflect.setField(target, name, value);
    }
}
