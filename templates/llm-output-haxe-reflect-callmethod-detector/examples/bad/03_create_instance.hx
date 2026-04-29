// Bad: Type.createInstance from a runtime class object.
class Factory {
    public static function build(cls:Class<Dynamic>, args:Array<Dynamic>):Dynamic {
        return Type.createInstance(cls, args);
    }
}
