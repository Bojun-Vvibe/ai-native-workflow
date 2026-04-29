// Good: mentions of Reflect.callMethod and Type.createInstance only
// in comments. We use a closed dispatch map instead.
/*
   Avoid Reflect.callMethod(o, m, a) and Type.createInstance(c, a)
   here — those are the dynamic dispatch paths.
*/
class Dispatcher {
    static var table = ["add" => addFn, "mul" => mulFn];
    static function addFn(args:Array<Int>):Int return args[0] + args[1];
    static function mulFn(args:Array<Int>):Int return args[0] * args[1];
    public static function call(op:String, args:Array<Int>):Int {
        return table.get(op)(args);
    }
}
