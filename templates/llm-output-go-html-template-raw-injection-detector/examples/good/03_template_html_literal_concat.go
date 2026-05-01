package handlers

import (
	"html/template"
	"net/http"
)

// All-literal + chain — also static.
func renderIntro(w http.ResponseWriter) {
	t := template.Must(template.New("i").Parse(`<div>{{.}}</div>`))
	t.Execute(w, template.HTML("<p>"+"Hello, world."+"</p>"))
}
