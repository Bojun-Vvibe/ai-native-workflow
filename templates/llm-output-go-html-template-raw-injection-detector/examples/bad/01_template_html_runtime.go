package handlers

import (
	"html/template"
	"net/http"
)

func renderBio(w http.ResponseWriter, userBio string) {
	// Wrapping a request-derived value in template.HTML disables
	// html/template's contextual escaping. XSS.
	tmpl := template.Must(template.New("p").Parse(`<p>{{.}}</p>`))
	tmpl.Execute(w, template.HTML(userBio))
}
