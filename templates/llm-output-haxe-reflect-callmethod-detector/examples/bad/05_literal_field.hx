// Bad: even a literal-name Reflect.field is worth review;
// model probably should have used a typed accessor.
class Probe {
    public static function getName(o:Dynamic):String {
        return Reflect.field(o, "name");
    }
}
