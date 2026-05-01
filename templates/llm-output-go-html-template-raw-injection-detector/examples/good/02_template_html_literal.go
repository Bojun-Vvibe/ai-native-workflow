package handlers

import (
	"html/template"
	"net/http"
)

// Static literal HTML chunk — by definition trusted, since it's in
// the source. Detector lets this pass.
func renderHeader(w http.ResponseWriter) {
	t := template.Must(template.New("h").Parse(`<header>{{.}}</header>`))
	t.Execute(w, template.HTML("<b>Welcome</b>"))
}
