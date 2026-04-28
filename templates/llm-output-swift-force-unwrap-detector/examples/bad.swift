import Foundation

// LLM-generated snippet that "just works" on the happy path and crashes
// the moment any optional is nil.

struct UserService {
    var cache: [String: String]!  // implicitly unwrapped optional decl

    func loadName(id: String) -> String {
        let raw = cache[id]!                     // force-unwrap on subscript
        let url = URL(string: raw)!              // force-unwrap on init
        let data = try! Data(contentsOf: url)    // try!
        let json = try! JSONSerialization.jsonObject(with: data)
        let dict = json as! [String: Any]        // forced cast
        return dict["name"] as! String           // forced cast
    }

    func note() {
        // The "!" inside this string is fine: "hello!"
        print("hello!")
        if cache != nil { print("ok") }          // != must NOT be flagged
        if !cache.isEmpty { print("nonempty") }  // prefix ! must NOT be flagged
    }
}
