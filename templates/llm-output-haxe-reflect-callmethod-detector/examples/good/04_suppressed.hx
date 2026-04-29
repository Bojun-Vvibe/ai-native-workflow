// Good: a vetted Reflect.callMethod that has been suppressed.
class Admin {
    public static function unsafeRepl(o:Dynamic, m:Dynamic, a:Array<Dynamic>):Dynamic {
        return Reflect.callMethod(o, m, a); // reflect-ok
    }
}
