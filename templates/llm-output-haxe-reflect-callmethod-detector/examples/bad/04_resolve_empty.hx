// Bad: resolveClass + createEmptyInstance bypasses constructor entirely.
class Loader {
    public static function load(name:String):Dynamic {
        var c = Type.resolveClass(name);
        return Type.createEmptyInstance(c);
    }
}
