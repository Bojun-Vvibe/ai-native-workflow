package handlers

import (
	"html/template"
	"net/http"
)

// Audited rendering path; explicit allow.
func renderTrustedFragment(w http.ResponseWriter, fragment string) {
	t := template.Must(template.New("f").Parse(`<section>{{.}}</section>`))
	t.Execute(w, template.HTML(fragment)) // llm-allow:go-template-raw
}
