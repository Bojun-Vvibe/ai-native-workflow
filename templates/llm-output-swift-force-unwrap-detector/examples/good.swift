import Foundation

// Same intent, no force-unwraps. Errors are surfaced; nils are handled.

struct UserService {
    var cache: [String: String] = [:]

    enum LoadError: Error { case missing, badURL, badJSON, badShape }

    func loadName(id: String) throws -> String {
        guard let raw = cache[id] else { throw LoadError.missing }
        guard let url = URL(string: raw) else { throw LoadError.badURL }
        let data = try Data(contentsOf: url)
        let json = try JSONSerialization.jsonObject(with: data)
        guard let dict = json as? [String: Any] else { throw LoadError.badJSON }
        guard let name = dict["name"] as? String else { throw LoadError.badShape }
        return name
    }

    func note() {
        print("hello!")              // ! inside string literal is fine
        if cache != nil { print("ok") }
        if !cache.isEmpty { print("nonempty") }
    }
}
