import UIKit

// LLM-emitted "embed a tiny browser" snippet — UIWebView is deprecated
// and is the canonical XSS vehicle on iOS.
class LegacyHelp: UIViewController {
    var web: UIWebView!
    override func viewDidLoad() {
        super.viewDidLoad()
        web = UIWebView(frame: view.bounds)
        view.addSubview(web)
    }
}
